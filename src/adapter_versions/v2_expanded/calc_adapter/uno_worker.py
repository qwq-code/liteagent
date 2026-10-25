from __future__ import annotations

import json
import hashlib
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .errors import AdapterError, error_payload
from .pivot_semantics import resolve_stacked_aggregate_fields
from .schema import explicit_format_ranges, normalize_pivot_data_field, orient_typed_values, validate_action_params
from .semantic_tables import (
    SemanticTableError,
    contiguous_table_row_count,
    plan_append_summary_rows,
    plan_ratio_column,
    plan_summary_row_charts,
    next_content_row,
    resolve_sheet_range_reference,
    stacked_destination_row,
)
from .text_composition import (
    FIELD_SEPARATOR_STYLES,
    LABEL_SEPARATOR_STYLES,
    resolve_text_separator,
)
from .year_over_year import (
    YearOverYearError,
    destination_a1,
    plan_year_over_year_summary,
)


def _uno_modules():
    try:
        import uno
        from com.sun.star.beans import PropertyValue
    except ImportError as exc:
        raise AdapterError(
            "UNO_CONNECT_FAILED",
            "python3-uno is not available in the worker interpreter",
            str(exc),
            503,
        ) from exc
    return uno, PropertyValue


def _property(name: str, value: Any):
    _, PropertyValue = _uno_modules()
    prop = PropertyValue()
    prop.Name = name
    prop.Value = value
    return prop


def _file_url(path_or_url: str) -> str:
    uno, _ = _uno_modules()
    if path_or_url.startswith("file://"):
        return path_or_url
    return uno.systemPathToFileUrl(str(Path(path_or_url).expanduser().resolve()))


def _url_path(url: str) -> Path | None:
    if not url or not url.startswith("file://"):
        return None
    return Path(unquote(urlparse(url).path))


def _saved_sheet_view(doc: Any, sheet_name: str) -> dict[str, Any]:
    path = _url_path(str(doc.URL))
    if not path or not path.is_file() or path.suffix.lower() != ".xlsx":
        raise AdapterError(
            "VERIFICATION_FAILED",
            "persisted sheet view verification requires a saved XLSX workbook",
        )
    if doc.isModified():
        raise AdapterError(
            "VERIFICATION_FAILED",
            "persisted sheet view verification requires workbook.save first",
        )
    spreadsheet_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    document_rel_ns = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(path) as package:
        workbook = ET.fromstring(package.read("xl/workbook.xml"))
        relationships = ET.fromstring(package.read("xl/_rels/workbook.xml.rels"))
        targets = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships.findall(
                f"{{{package_rel_ns}}}Relationship"
            )
        }
        target = None
        for sheet in workbook.findall(f".//{{{spreadsheet_ns}}}sheet"):
            if sheet.attrib.get("name") == sheet_name:
                target = targets[sheet.attrib[f"{{{document_rel_ns}}}id"]]
                break
        if target is None:
            raise AdapterError(
                "SHEET_NOT_FOUND", f"sheet not found in saved XLSX: {sheet_name}"
            )
        normalized = "xl/" + target.removeprefix("/").removeprefix("xl/")
        worksheet = ET.fromstring(package.read(normalized))
    sheet_view = worksheet.find(f".//{{{spreadsheet_ns}}}sheetView")
    pane = worksheet.find(f".//{{{spreadsheet_ns}}}pane")
    return {
        "zoom": int(float(sheet_view.attrib.get("zoomScale", "100")))
        if sheet_view is not None
        else 100,
        "columns": int(float(pane.attrib.get("xSplit", "0")))
        if pane is not None
        else 0,
        "rows": int(float(pane.attrib.get("ySplit", "0"))) if pane is not None else 0,
        "frozen": pane is not None
        and pane.attrib.get("state", "").lower() in {"frozen", "frozensplit"},
        "top_left_cell": pane.attrib.get("topLeftCell") if pane is not None else None,
    }


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _reopen_xlsx(path: Path) -> dict[str, Any]:
    observed: dict[str, Any] = {
        "exists": path.is_file(),
        "size": path.stat().st_size if path.is_file() else 0,
        "valid_xlsx": path.is_file() and zipfile.is_zipfile(path),
        "opened": False,
    }
    if not observed["valid_xlsx"]:
        return observed

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return {**observed, "reopen_error": "LibreOffice executable was not found"}

    uno, _ = _uno_modules()
    with tempfile.TemporaryDirectory(prefix="osworld-calc-reopen-") as temp_dir:
        temp_root = Path(temp_dir)
        workbook_copy = temp_root / path.name
        profile_dir = temp_root / "profile"
        shutil.copy2(path, workbook_copy)
        port = _unused_loopback_port()
        process = subprocess.Popen(
            [
                soffice,
                "--headless",
                "--nologo",
                "--nodefault",
                "--norestore",
                "--nofirststartwizard",
                f"-env:UserInstallation={_file_url(str(profile_dir))}",
                f"--accept=socket,host=127.0.0.1,port={port};urp;",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        desktop = None
        reopened = None
        try:
            local_context = uno.getComponentContext()
            resolver = local_context.ServiceManager.createInstanceWithContext(
                "com.sun.star.bridge.UnoUrlResolver", local_context
            )
            deadline = time.monotonic() + 10
            context = None
            last_error: Exception | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    context = resolver.resolve(
                        f"uno:socket,host=127.0.0.1,port={port};urp;"
                        "StarOffice.ComponentContext"
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(0.1)
            if context is None:
                message = "isolated LibreOffice did not expose its UNO listener"
                if last_error:
                    message = f"{message}: {last_error}"
                return {**observed, "reopen_error": message}

            service_manager = context.ServiceManager
            desktop = service_manager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", context
            )
            reopened = desktop.loadComponentFromURL(
                _file_url(str(workbook_copy)),
                "_blank",
                0,
                (_property("Hidden", True), _property("ReadOnly", True)),
            )
            if reopened is None or not reopened.supportsService(
                "com.sun.star.sheet.SpreadsheetDocument"
            ):
                return {
                    **observed,
                    "reopen_error": "file did not reopen as a Calc workbook",
                }
            sheet_names = _sheet_names(reopened)
            used_ranges = {
                name: _used_range(reopened.getSheets().getByName(name))
                for name in sheet_names
            }
            return {
                **observed,
                "opened": True,
                "sheet_names": sheet_names,
                "used_ranges": used_ranges,
            }
        except Exception as exc:
            return {**observed, "reopen_error": str(exc)}
        finally:
            if reopened is not None:
                try:
                    reopened.close(True)
                except Exception:
                    try:
                        reopened.dispose()
                    except Exception:
                        pass
            if desktop is not None:
                try:
                    desktop.terminate()
                except Exception:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return str(value)


def _enum_name(value: Any) -> str:
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value).lower()
    text = str(value)
    return text.rsplit(".", 1)[-1].lower()


def _color(value: Any) -> int:
    if isinstance(value, bool):
        raise AdapterError("INVALID_REQUEST", "colors cannot be booleans")
    if isinstance(value, int) and 0 <= value <= 0xFFFFFF:
        return value
    if isinstance(value, str):
        raw = value.removeprefix("#")
        if len(raw) == 6:
            try:
                return int(raw, 16)
            except ValueError:
                pass
    raise AdapterError("INVALID_REQUEST", "color must be #RRGGBB or an RGB integer")


class CalcSession:
    def __init__(
        self, selector: dict[str, Any], *, allow_no_document: bool = False
    ) -> None:
        uno, _ = _uno_modules()
        local_context = uno.getComponentContext()
        resolver = local_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local_context
        )
        try:
            self.context = resolver.resolve(
                "uno:socket,host=127.0.0.1,port=2002;urp;StarOffice.ComponentContext"
            )
        except Exception as exc:
            raise AdapterError(
                "UNO_CONNECT_FAILED",
                "failed to connect to LibreOffice UNO",
                str(exc),
                503,
            ) from exc
        self.service_manager = self.context.ServiceManager
        self.desktop = self.service_manager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", self.context
        )
        self.doc = self._select_document(selector, allow_none=allow_no_document)

    def _documents(self) -> list[Any]:
        documents = []
        components = self.desktop.getComponents().createEnumeration()
        while components.hasMoreElements():
            component = components.nextElement()
            try:
                if component.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
                    documents.append(component)
            except Exception:
                continue
        return documents

    def _identity(self, doc: Any) -> dict[str, str]:
        url = str(getattr(doc, "URL", "") or "")
        title = str(getattr(doc, "Title", "") or "")
        if not title:
            path = _url_path(url)
            title = path.name if path else ""
        return {"url": url, "title": title}

    def _select_document(
        self, selector: dict[str, Any], *, allow_none: bool = False
    ) -> Any:
        if allow_none and not selector:
            return None
        documents = self._documents()
        requested_url = selector.get("url")
        requested_title = selector.get("title")
        if requested_url:
            requested_url = _file_url(str(requested_url))
        matches = []
        for doc in documents:
            identity = self._identity(doc)
            if requested_url and identity["url"] != requested_url:
                continue
            if requested_title and identity["title"] != requested_title:
                continue
            matches.append(doc)
        if requested_url and not matches:
            try:
                loaded = self.desktop.loadComponentFromURL(
                    requested_url, "_blank", 0, ()
                )
            except Exception as exc:
                raise AdapterError(
                    "DOCUMENT_OPEN_FAILED",
                    "failed to open requested Calc document",
                    {"url": requested_url, "error": str(exc)},
                    422,
                ) from exc
            if loaded is None or not loaded.supportsService(
                "com.sun.star.sheet.SpreadsheetDocument"
            ):
                if loaded is not None:
                    try:
                        loaded.close(True)
                    except Exception:
                        loaded.dispose()
                raise AdapterError(
                    "DOCUMENT_OPEN_FAILED",
                    "requested file did not open as a Calc document",
                    {"url": requested_url},
                    422,
                )
            loaded_identity = self._identity(loaded)
            if requested_title and loaded_identity["title"] != requested_title:
                try:
                    loaded.close(True)
                except Exception:
                    loaded.dispose()
                raise AdapterError(
                    "DOCUMENT_MISMATCH",
                    "opened Calc document does not match the requested title",
                    {"selector": selector, "opened_document": loaded_identity},
                    404,
                )
            return loaded
        if not documents and allow_none and not selector:
            return None
        if not documents:
            raise AdapterError(
                "NO_CALC_DOCUMENT", "no open Calc document was found", http_status=404
            )
        if requested_url or requested_title:
            if not matches:
                raise AdapterError(
                    "DOCUMENT_MISMATCH",
                    "no open Calc document matches the selector",
                    {
                        "selector": selector,
                        "open_documents": [self._identity(doc) for doc in documents],
                    },
                    404,
                )
        else:
            matches = documents
        if len(matches) != 1:
            raise AdapterError(
                "DOCUMENT_AMBIGUOUS",
                "document selector is required when multiple Calc documents are open",
                {"open_documents": [self._identity(doc) for doc in matches]},
                409,
            )
        return matches[0]

    def sheet(self, name: str) -> Any:
        sheets = self.doc.getSheets()
        if not sheets.hasByName(name):
            raise AdapterError(
                "SHEET_NOT_FOUND", f"sheet not found: {name}", http_status=404
            )
        return sheets.getByName(name)

    def activate_sheet(self, name: str) -> Any:
        sheet = self.sheet(name)
        controller = self.doc.getCurrentController()
        controller.setActiveSheet(sheet)
        return controller


def _sheet_names(doc: Any) -> list[str]:
    return list(doc.getSheets().getElementNames())


def _column_label(index: int) -> str:
    label = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def _chart_diagram_type(diagram: Any) -> str | None:
    try:
        diagram_type = str(diagram.getDiagramType()).casefold()
        if "linediagram" in diagram_type:
            return "line"
        if "bardiagram" in diagram_type:
            return "bar" if bool(diagram.Vertical) else "column"
    except Exception:
        pass
    try:
        if diagram.supportsService("com.sun.star.chart.LineDiagram"):
            return "line"
        if diagram.supportsService("com.sun.star.chart.BarDiagram"):
            return "bar" if bool(diagram.Vertical) else "column"
    except Exception:
        return None
    return None


def _chart_diagram_details(diagram: Any) -> dict[str, Any]:
    try:
        diagram_type = str(diagram.getDiagramType())
    except Exception:
        diagram_type = None
    try:
        services = [str(value) for value in diagram.getSupportedServiceNames()]
    except Exception:
        services = []
    return {
        "diagram": str(diagram.getImplementationName()),
        "diagram_type": diagram_type,
        "supported_services": services,
        "type": _chart_diagram_type(diagram),
    }


def _chart_series_details(chart: Any) -> dict[str, Any]:
    """Read plotted series and primary category axes from the native chart model."""
    series = []
    category_axes = []
    for index, coordinate in enumerate(chart.getFirstDiagram().getCoordinateSystems()):
        for chart_type in coordinate.getChartTypes():
            for data_series in chart_type.getDataSeries():
                labels = []
                source_ranges = []
                for sequence in data_series.getDataSequences():
                    label = sequence.getLabel()
                    if label is not None:
                        labels.extend(_json_value(value) for value in label.getData())
                    values = sequence.getValues()
                    if values is not None:
                        source_ranges.append(str(values.getSourceRangeRepresentation()))
                series.append(
                    {
                        "coordinate_system": index,
                        "labels": labels,
                        "source_ranges": source_ranges,
                    }
                )
        axis = coordinate.getAxisByDimension(0, 0)
        if axis is None:
            continue
        categories = axis.getScaleData().Categories
        values = categories.getValues() if categories is not None else None
        if values is not None:
            labels = [_json_value(value) for value in values.getData()]
            category_axes.append(
                {
                    "coordinate_system": index,
                    "source_range": str(values.getSourceRangeRepresentation()),
                    "labels": labels,
                    "count": len(labels),
                }
            )
    return {
        "data_series_count": len(series),
        "data_series": series,
        "category_axes": category_axes,
    }


def _used_range(sheet: Any) -> dict[str, Any]:
    cursor = sheet.createCursor()
    cursor.gotoEndOfUsedArea(True)
    address = cursor.getRangeAddress()
    return {
        "start_column": address.StartColumn,
        "start_row": address.StartRow,
        "end_column": address.EndColumn,
        "end_row": address.EndRow,
        "rows": address.EndRow - address.StartRow + 1,
        "columns": address.EndColumn - address.StartColumn + 1,
    }


def _hidden_rows_in_used_range(sheet: Any, used_range: dict[str, Any]) -> list[int]:
    rows = sheet.getRows()
    return [
        row_index + 1
        for row_index in range(used_range["start_row"], used_range["end_row"] + 1)
        if not bool(rows.getByIndex(row_index).IsVisible)
    ]


def _cell_kind(cell: Any) -> str:
    cell_type = _enum_name(cell.getType())
    if cell_type == "formula":
        return "formula"
    if cell_type == "empty":
        return "blank"
    if cell_type == "text":
        return "string"
    return "number"


def _number_format_details(doc: Any, key: int) -> dict[str, Any]:
    try:
        properties = doc.getNumberFormats().getByKey(key)
        locale = properties.Locale
        locale_name = "-".join(
            part for part in (str(locale.Language), str(locale.Country)) if part
        )
        details = {
            "id": key,
            "code": str(properties.FormatString),
            "locale": locale_name,
        }
        try:
            details["type"] = int(properties.Type)
        except Exception:
            pass
        return details
    except Exception:
        return {"id": key, "code": None, "locale": None}


def _document_null_date(doc: Any) -> date | None:
    """Read the document's serial-zero date without assuming an epoch."""
    try:
        null_date = doc.NullDate
    except Exception:
        try:
            null_date = doc.getNumberFormatSettings().getPropertyValue("NullDate")
        except Exception:
            return None
    try:
        return date(int(null_date.Year), int(null_date.Month), int(null_date.Day))
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _native_date_observation(
    cell: Any,
    kind: str,
    value: Any,
    number_format: dict[str, Any],
    null_date: date | None,
) -> dict[str, str] | None:
    # com.sun.star.util.NumberFormat.DATE = 2; DATETIME includes this bit.
    format_type = number_format.get("type")
    if (
        null_date is None
        or kind not in {"number", "formula"}
        or not isinstance(format_type, int)
        or not format_type & 2
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        return None
    if kind == "formula":
        try:
            # Numeric formula results only: text/error formulas must not turn
            # getValue()'s zero into a date at the document's origin.
            if cell.getError() or _enum_name(cell.FormulaResultType) not in {"value", "1"}:
                return None
        except Exception:
            return None
    try:
        if not math.isfinite(value):
            return None
        observed_date = null_date + timedelta(days=math.floor(value))
    except (ValueError, OverflowError):
        return None
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    return {"date": observed_date.isoformat(), "weekday": weekdays[observed_date.weekday()]}


def _range_snapshot(cell_range: Any, doc: Any | None = None) -> dict[str, Any]:
    address = cell_range.getRangeAddress()
    cell_addresses = [
        [
            f"{_column_label(address.StartColumn + column_index)}"
            f"{address.StartRow + row_index + 1}"
            for column_index in range(address.EndColumn - address.StartColumn + 1)
        ]
        for row_index in range(address.EndRow - address.StartRow + 1)
    ]
    values: list[list[Any]] = []
    formulas: list[list[str]] = []
    display: list[list[str]] = []
    kinds: list[list[str]] = []
    formats: list[list[int]] = []
    styles: list[list[dict[str, Any]]] = []
    number_formats: list[list[dict[str, Any]]] = []
    background_cells: dict[str, str] = {}
    date_cells: dict[str, dict[str, str]] = {}
    null_date = _document_null_date(doc) if doc is not None else None
    for row_index in range(address.EndRow - address.StartRow + 1):
        value_row = []
        formula_row = []
        display_row = []
        kind_row = []
        format_row = []
        style_row = []
        number_format_row = []
        for column_index in range(address.EndColumn - address.StartColumn + 1):
            cell = cell_range.getCellByPosition(column_index, row_index)
            kind = _cell_kind(cell)
            value = (
                cell.getValue() if kind in {"number", "formula"} else cell.getString()
            )
            if kind == "blank":
                value = None
            value_row.append(_json_value(value))
            formula_row.append(str(cell.getFormula()) if kind == "formula" else "")
            display_row.append(str(cell.getString()))
            kind_row.append(kind)
            format_row.append(int(cell.NumberFormat))
            style_row.append(
                {
                    "background_color": f"#{int(cell.CellBackColor) & 0xFFFFFF:06x}",
                    "font_color": f"#{int(cell.CharColor) & 0xFFFFFF:06x}",
                    "bold": float(cell.CharWeight) >= 150,
                    "number_format_id": int(cell.NumberFormat),
                }
            )
            background = int(cell.CellBackColor) & 0xFFFFFF
            if background != 0xFFFFFF:
                background_cells[
                    f"{_column_label(address.StartColumn + column_index)}"
                    f"{address.StartRow + row_index + 1}"
                ] = f"#{background:06x}"
            if doc is not None:
                number_format = _number_format_details(doc, int(cell.NumberFormat))
                number_format_row.append(number_format)
                date_observation = _native_date_observation(
                    cell, kind, value, number_format, null_date
                )
                if date_observation is not None:
                    date_cells[cell_addresses[row_index][column_index]] = date_observation
        values.append(value_row)
        formulas.append(formula_row)
        display.append(display_row)
        kinds.append(kind_row)
        formats.append(format_row)
        styles.append(style_row)
        if doc is not None:
            number_formats.append(number_format_row)
    snapshot = {
        "values": values,
        "formulas": formulas,
        "display_text": display,
        "kinds": kinds,
        "cell_addresses": cell_addresses,
        "number_format_ids": formats,
        "styles": styles,
        "background_cells": background_cells,
    }
    if doc is not None:
        snapshot["number_formats"] = number_formats
        snapshot["date_cells"] = date_cells
    return snapshot


def _inspect(session: CalcSession, _: dict[str, Any]) -> dict[str, Any]:
    doc = session.doc
    controller = doc.getCurrentController()
    active = controller.getActiveSheet().getName()
    sheets = []
    for name in _sheet_names(doc):
        sheet = session.sheet(name)
        used_range = _used_range(sheet)
        chart_snapshots = []
        charts = sheet.getCharts()
        for chart_name in charts.getElementNames():
            try:
                table_chart = charts.getByName(chart_name)
                embedded = table_chart.getEmbeddedObject()
                diagram = embedded.getDiagram()
                source_ranges = []
                source_sheets = []
                for address in table_chart.getRanges():
                    source_name = doc.getSheets().getByIndex(address.Sheet).getName()
                    source_sheets.append(source_name)
                    start = (
                        f"{_column_label(address.StartColumn)}{address.StartRow + 1}"
                    )
                    end = f"{_column_label(address.EndColumn)}{address.EndRow + 1}"
                    source_ranges.append(start if start == end else f"{start}:{end}")
                chart_snapshot = {
                    "name": str(chart_name),
                    "title": str(embedded.Title.String)
                    if embedded.HasMainTitle
                    else "",
                    **_chart_diagram_details(diagram),
                    "source_sheet": source_sheets[0]
                    if source_sheets and len(set(source_sheets)) == 1
                    else None,
                    "source_ranges": source_ranges,
                    "column_headers": bool(table_chart.getHasColumnHeaders()),
                    "row_headers": bool(table_chart.getHasRowHeaders()),
                }
                try:
                    chart_snapshot.update(_chart_series_details(embedded))
                except Exception as exc:
                    chart_snapshot["data_series_inspect_error"] = str(exc)
                chart_snapshots.append(chart_snapshot)
            except Exception as exc:
                chart_snapshots.append(
                    {"name": str(chart_name), "inspect_error": str(exc)}
                )
        sheet_snapshot = {
            "name": name,
            "used_range": used_range,
            "hidden_rows": _hidden_rows_in_used_range(sheet, used_range),
            "charts": chart_snapshots,
            "pivot_tables": [],
        }
        try:
            tables = sheet.getDataPilotTables()
            for pivot_name in tables.getElementNames():
                pivot_snapshot = {"name": str(pivot_name)}
                try:
                    output = tables.getByName(pivot_name).getOutputRange()
                    pivot_snapshot["output_range"] = _range_a1(output)
                except Exception as exc:
                    pivot_snapshot["inspect_error"] = str(exc)
                sheet_snapshot["pivot_tables"].append(pivot_snapshot)
        except Exception as exc:
            sheet_snapshot["pivot_tables_inspect_error"] = str(exc)
        sheets.append(sheet_snapshot)
    identity = session._identity(doc)
    return {
        **identity,
        "active_sheet": active,
        "sheets": sheets,
        "modified": bool(doc.isModified()),
    }


def _read(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    cell_range = session.sheet(params["sheet"]).getCellRangeByName(params["range"])
    return {
        "sheet": params["sheet"],
        "range": params["range"],
        **_range_snapshot(cell_range, session.doc),
    }


def _date_serial(doc: Any, value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(value), datetime.min.time())
        except ValueError as exc:
            raise AdapterError("INVALID_REQUEST", f"invalid ISO date: {value}") from exc
    null_date = doc.NullDate
    base = datetime(null_date.Year, null_date.Month, null_date.Day)
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return (parsed - base).total_seconds() / 86400


def _formula_string_literal(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _formatted_text_formula(value: dict[str, Any]) -> str:
    expressions = []
    for part in value["parts"]:
        if "text" in part:
            expressions.append(_formula_string_literal(str(part["text"])))
            continue
        reference = str(part["cell"]).strip()
        if "decimal_places" in part:
            expressions.append(f"FIXED({reference};{int(part['decimal_places'])};1)")
        else:
            expressions.append(reference)
    return "=" + "&".join(expressions)


def _set_cell(doc: Any, cell: Any, spec: dict[str, Any]) -> None:
    kind = spec["kind"]
    value = spec.get("value")
    if kind == "blank":
        cell.setString("")
    elif kind == "string":
        if not isinstance(value, str):
            raise AdapterError("INVALID_REQUEST", "string cell values must be strings")
        cell.setString(value)
    elif kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AdapterError("INVALID_REQUEST", "number cell values must be numeric")
        cell.setValue(float(value))
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise AdapterError(
                "INVALID_REQUEST", "boolean cell values must be booleans"
            )
        cell.setFormula("=TRUE()" if value else "=FALSE()")
    elif kind == "date":
        if not isinstance(value, str):
            raise AdapterError(
                "INVALID_REQUEST", "date cell values must be ISO strings"
            )
        cell.setValue(_date_serial(doc, value))
    elif kind == "formula":
        if not isinstance(value, str) or not value.startswith("="):
            raise AdapterError(
                "INVALID_REQUEST", "formula cell values must start with '='"
            )
        cell.setFormula(value)
    elif kind == "formatted_text":
        if not isinstance(value, dict):
            raise AdapterError(
                "INVALID_REQUEST", "formatted_text cell values must be objects"
            )
        cell.setFormula(_formatted_text_formula(value))
    if "number_format" in spec:
        _apply_number_format(doc, cell, str(spec["number_format"]), spec.get("locale"))


def _formula_error_recovery(error_cells: list[dict[str, Any]], fallback: str) -> str:
    if any(cell.get("error_code") == 522 for cell in error_cells):
        return (
            "522: circular reference. Unqualified cells use the destination sheet; "
            "qualify source references."
        )
    return fallback


def _write(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    cell_range = session.sheet(params["sheet"]).getCellRangeByName(params["range"])
    address = cell_range.getRangeAddress()
    rows = address.EndRow - address.StartRow + 1
    columns = address.EndColumn - address.StartColumn + 1
    raw_values = params["values"]
    # range.write owns the explicitly selected rectangle. Similar values in
    # other rows are not evidence of an invalid write (or a unique record key).
    # Deduplication and append planning belong to the caller, not this primitive.
    values = orient_typed_values(
        raw_values, target_rows=rows, target_columns=columns
    )
    raw_rows = raw_values if isinstance(raw_values[0], list) else [raw_values]
    literal_cells = sum(
        not isinstance(cell, Mapping) for row in raw_rows for cell in row
    )
    conversion = (
        {
            "contract": "calc.range.write.literal_cells.v1",
            "literal_cells": literal_cells,
            "target_rows": rows,
            "target_columns": columns,
            "canonical_matrix_sha256": hashlib.sha256(
                json.dumps(
                    values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
            "canonical_encoding": "json:ensure_ascii=false,sort_keys=true,separators=(comma,colon)",
        }
        if literal_cells
        else None
    )
    try:
        result = _write_values(session, params, cell_range, values)
    except Exception as exc:
        if conversion is None:
            raise
        if isinstance(exc, AdapterError):
            details = (
                dict(exc.details)
                if isinstance(exc.details, dict)
                else {"write_error": exc.details}
            )
            details["argument_conversion"] = conversion
            raise AdapterError(exc.code, exc.message, details, exc.http_status) from exc
        raise AdapterError(
            "WRITE_FAILED",
            "range.write failed during writing or read-back; inspect the target before retrying",
            {"error": str(exc), "argument_conversion": conversion},
            500,
        ) from exc
    if conversion is not None:
        result["argument_conversion"] = conversion
    return result


def _write_values(
    session: CalcSession,
    params: dict[str, Any],
    cell_range: Any,
    values: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    """Write the owning Adapter's canonical cells with existing rollback semantics."""
    address = cell_range.getRangeAddress()
    rows, columns = len(values), len(values[0])
    formula_cells = [
        (row_index, column_index, spec["kind"])
        for row_index, row in enumerate(values)
        for column_index, spec in enumerate(row)
        if spec["kind"] in {"formula", "formatted_text"}
    ]
    before = (
        [
            [
                _cell_state(cell_range.getCellByPosition(column_index, row_index))
                for column_index in range(columns)
            ]
            for row_index in range(rows)
        ]
        if formula_cells
        else None
    )
    try:
        for row_index, row in enumerate(values):
            for column_index, spec in enumerate(row):
                _set_cell(
                    session.doc,
                    cell_range.getCellByPosition(column_index, row_index),
                    spec,
                )
        session.doc.calculateAll()
        error_cells = []
        for row_index, column_index, kind in formula_cells:
            cell = cell_range.getCellByPosition(column_index, row_index)
            error_code = int(cell.getError())
            if error_code:
                error_cells.append(
                    {
                        "cell": (
                            f"{_column_label(address.StartColumn + column_index)}"
                            f"{address.StartRow + row_index + 1}"
                        ),
                        "kind": kind,
                        "error_code": error_code,
                    }
                )
        if error_cells:
            raise AdapterError(
                "FORMULA_ERROR",
                (
                    "one or more submitted formulas produced spreadsheet errors; the entire "
                    "target range was restored"
                ),
                {
                    "sheet": params["sheet"],
                    "range": params["range"],
                    "cells": error_cells,
                    "recovery": _formula_error_recovery(
                        error_cells,
                        "Inspect the referenced cells and correct the formatted_text "
                        "parts. decimal_places requires a numeric value; omit "
                        "decimal_places for text references. Check cell addresses "
                        "and existing cell errors before retrying; formatted_text "
                        "already uses the Adapter's formula syntax."
                        if any(cell["kind"] == "formatted_text" for cell in error_cells)
                        else "retry with a locale-compatible formula or the formatted_text "
                        "typed-cell representation"
                    ),
                },
                422,
            )
        readback = _read(session, params)
    except Exception as exc:
        if before is None:
            raise
        try:
            for row_index, row in enumerate(before):
                for column_index, state in enumerate(row):
                    _restore_cell_state(
                        cell_range.getCellByPosition(column_index, row_index),
                        state,
                        content=True,
                        style=True,
                        strict_style=True,
                    )
            session.doc.calculateAll()
        except Exception as restore_exc:
            raise AdapterError(
                "ROLLBACK_FAILED",
                "range.write failed and the target range could not be fully restored",
                {
                    "sheet": params["sheet"],
                    "range": params["range"],
                    "write_error": str(exc),
                    "rollback_error": str(restore_exc),
                },
                500,
            ) from restore_exc
        if isinstance(exc, AdapterError):
            raise
        raise AdapterError(
            "WRITE_FAILED",
            "range.write failed; the entire target range was restored",
            {
                "sheet": params["sheet"],
                "range": params["range"],
                "error": str(exc),
            },
            500,
        ) from exc
    return {"written_cells": rows * columns, **readback}


def _set_formulas(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    resolved = [
        (write, sheet.getCellRangeByName(write["cell"])) for write in params["writes"]
    ]
    before = [_cell_state(cell) for _, cell in resolved]
    try:
        for write, cell in resolved:
            cell.setFormula(write["formula"])
        session.doc.calculateAll()
        error_cells = []
        for write, cell in resolved:
            error_code = int(cell.getError())
            if error_code:
                error_cells.append(
                    {
                        "cell": write["cell"],
                        "kind": "formula",
                        "error_code": error_code,
                    }
                )
        if error_cells:
            raise AdapterError(
                "FORMULA_ERROR",
                (
                    "one or more submitted formulas produced spreadsheet errors; "
                    "all target cells were restored"
                ),
                {
                    "sheet": params["sheet"],
                    "cells": error_cells,
                    "recovery": _formula_error_recovery(
                        error_cells,
                        "Calc uses semicolons between function arguments, for example "
                        "=ROUND(C4;3). Change the separator inside the function's "
                        "parentheses, not punctuation inside quoted text: quoted "
                        "commas stay literal commas. Inspect the referenced cells "
                        "and retry with a native Calc formula. For joining text and "
                        "formatted cell values, range.write supports kind=formatted_text "
                        "with explicit parts. Read back the result "
                        "before submitting another formula batch. For a Total or "
                        "Subtotal row, fill each blank numeric period cell and then "
                        "the final total cell."
                    ),
                },
                422,
            )
    except Exception as exc:
        try:
            for (_, cell), state in zip(resolved, before, strict=True):
                _restore_cell_state(
                    cell,
                    state,
                    content=True,
                    style=True,
                    strict_style=True,
                )
            session.doc.calculateAll()
        except Exception as restore_exc:
            raise AdapterError(
                "ROLLBACK_FAILED",
                "formula batch failed and the target cells could not be fully restored",
                {
                    "sheet": params["sheet"],
                    "write_error": str(exc),
                    "rollback_error": str(restore_exc),
                },
                500,
            ) from restore_exc
        if isinstance(exc, AdapterError):
            raise
        raise AdapterError(
            "WRITE_FAILED",
            "failed to set the explicit formula batch; all target cells were restored",
            str(exc),
        ) from exc
    return {
        "sheet": params["sheet"],
        "written_cells": len(resolved),
        "cells": [
            {
                "cell": write["cell"],
                "formula": str(cell.getFormula()),
                "display_text": str(cell.getString()),
                "value": cell.getValue(),
                "kind": _cell_kind(cell),
            }
            for write, cell in resolved
        ],
    }


def _spreadsheet_package_format(path: Path) -> str | None:
    """Identify supported spreadsheet packages from their internal signatures."""
    if not path.is_file() or not zipfile.is_zipfile(path):
        return None
    try:
        with zipfile.ZipFile(path) as package:
            names = set(package.namelist())
            if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
                return "xlsx"
            if "mimetype" in names:
                mimetype = package.read("mimetype").decode("ascii", errors="replace")
                if mimetype == "application/vnd.oasis.opendocument.spreadsheet":
                    return "ods"
            if "content.xml" in names and "META-INF/manifest.xml" in names:
                return "ods"
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    return None


def _save(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    validate_action_params("workbook.save", params)
    doc = session.doc
    doc.calculateAll()
    target = params.get("url")
    try:
        if target:
            url = _file_url(target)
            path = _url_path(url)
            suffix = path.suffix.lower() if path is not None else ""
            inferred_filter = _NEW_WORKBOOK_FILTERS.get(suffix)
            requested_filter = params.get("filter_name")
            if (
                inferred_filter is not None
                and requested_filter is not None
                and requested_filter != inferred_filter
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.filter_name conflicts with the selected output extension",
                    {
                        "extension": suffix,
                        "selected_filter": requested_filter,
                        "required_filter": inferred_filter,
                    },
                )
            filter_name = requested_filter or inferred_filter
            properties = [_property("Overwrite", True)]
            if filter_name:
                properties.insert(0, _property("FilterName", filter_name))
            doc.storeAsURL(url, tuple(properties))
        else:
            if not doc.URL:
                raise AdapterError(
                    "SAVE_FAILED", "unsaved documents require params.url"
                )
            doc.store()
            url = doc.URL
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "SAVE_FAILED", "LibreOffice failed to save the workbook", str(exc), 500
        ) from exc
    path = _url_path(url)
    if not path or not path.is_file() or path.stat().st_size == 0:
        raise AdapterError(
            "SAVE_FAILED", "saved workbook is missing or empty", {"url": url}, 500
        )
    expected_format = path.suffix.lower().removeprefix(".")
    package_format = (
        _spreadsheet_package_format(path)
        if expected_format in _NEW_WORKBOOK_FILTERS_FORMATS
        else None
    )
    if (
        expected_format in _NEW_WORKBOOK_FILTERS_FORMATS
        and package_format != expected_format
    ):
        raise AdapterError(
            "SAVE_FAILED",
            "saved workbook package does not match the selected output extension",
            {
                "path": str(path),
                "expected_format": expected_format,
                "observed_format": package_format,
            },
            500,
        )
    return {
        "url": url,
        "path": str(path),
        "size": path.stat().st_size,
        "mtime_ns": path.stat().st_mtime_ns,
        "format": expected_format,
        "package_format": package_format,
    }


_NEW_WORKBOOK_FILTERS = {
    ".ods": "calc8",
    ".xlsx": "Calc MS Excel 2007 XML",
}
_NEW_WORKBOOK_FILTERS_FORMATS = frozenset(
    suffix.removeprefix(".") for suffix in _NEW_WORKBOOK_FILTERS
)


def _plain_cell_spec(value: Any) -> dict[str, Any]:
    if value is None:
        return {"kind": "blank"}
    if isinstance(value, bool):
        return {"kind": "boolean", "value": value}
    if isinstance(value, (int, float)):
        return {"kind": "number", "value": value}
    return {"kind": "string", "value": str(value)}


def _create_new(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    output_url = _file_url(params["output_path"])
    output_path = _url_path(output_url)
    if output_path is None:
        raise AdapterError(
            "INVALID_REQUEST", "workbook.create_new supports local files only"
        )
    output_path = output_path.resolve()
    filter_name = _NEW_WORKBOOK_FILTERS.get(output_path.suffix.lower())
    if filter_name is None:
        raise AdapterError("INVALID_REQUEST", "new workbook format must be ODS or XLSX")
    if output_path.exists() and not params.get("overwrite", False):
        raise AdapterError(
            "CONFLICT",
            "destination workbook already exists; set overwrite=true to replace it",
            {"output_path": str(output_path)},
            409,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    previous_doc = session.doc
    previous_doc_closed = False
    previous_file_existed = output_path.is_file()
    stage_fd, stage_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.create-",
        suffix=output_path.suffix,
        dir=output_path.parent,
    )
    os.close(stage_fd)
    stage_path = Path(stage_name)
    stage_path.unlink()
    stage_url = _file_url(str(stage_path))
    backup_path: Path | None = None
    commit_started = False
    doc = None
    try:
        doc = session.desktop.loadComponentFromURL(
            "private:factory/scalc", "_blank", 0, ()
        )
        if doc is None or not doc.supportsService(
            "com.sun.star.sheet.SpreadsheetDocument"
        ):
            raise AdapterError(
                "DOCUMENT_CREATE_FAILED",
                "LibreOffice did not create a Calc workbook",
                http_status=500,
            )
        sheets = doc.getSheets()
        sheet = sheets.getByIndex(0)
        sheet_name = params.get("sheet_name")
        if sheet_name and sheet.getName() != sheet_name:
            if sheets.hasByName(sheet_name):
                raise AdapterError(
                    "CONFLICT", f"sheet already exists: {sheet_name}", http_status=409
                )
            sheet.setName(sheet_name)
        sheet_name = sheet.getName()

        headers = params.get("headers")
        rows_supplied = "rows" in params
        rows = params.get("rows")
        matrix = [headers, *(rows or [])] if headers is not None else []
        for row_index, row in enumerate(matrix):
            for column_index, value in enumerate(row):
                _set_cell(
                    doc,
                    sheet.getCellByPosition(column_index, row_index),
                    _plain_cell_spec(value),
                )
        doc.calculateAll()
        doc.storeAsURL(
            stage_url,
            (
                _property("FilterName", filter_name),
                _property("Overwrite", True),
            ),
        )
        if (
            not stage_path.is_file()
            or stage_path.stat().st_size == 0
            or not zipfile.is_zipfile(stage_path)
        ):
            raise AdapterError(
                "DOCUMENT_CREATE_FAILED",
                "staged workbook package is missing, empty, or invalid",
                {"staged_path": str(stage_path)},
                500,
            )

        if previous_file_existed:
            backup_fd, backup_name = tempfile.mkstemp(
                prefix=f".{output_path.stem}.backup-",
                suffix=output_path.suffix,
                dir=output_path.parent,
            )
            os.close(backup_fd)
            backup_path = Path(backup_name)
            shutil.copy2(output_path, backup_path)

        if params.get("overwrite", False) and (
            str(getattr(previous_doc, "URL", "") or "") != output_url
        ):
            previous_doc = next(
                (
                    candidate
                    for candidate in session._documents()
                    if str(getattr(candidate, "URL", "") or "") == output_url
                ),
                previous_doc,
            )
        previous_url = str(getattr(previous_doc, "URL", "") or "")
        if (
            previous_doc is not None
            and previous_doc is not doc
            and previous_url == output_url
        ):
            _close_document(previous_doc)
            previous_doc_closed = True

        commit_started = True
        doc.storeAsURL(
            output_url,
            (
                _property("FilterName", filter_name),
                _property("Overwrite", True),
            ),
        )
        if (
            not output_path.is_file()
            or output_path.stat().st_size == 0
            or not zipfile.is_zipfile(output_path)
        ):
            raise AdapterError(
                "DOCUMENT_CREATE_FAILED",
                "created workbook package is missing, empty, or invalid",
                {"output_path": str(output_path)},
                500,
            )
        session.doc = doc
    except AdapterError:
        if doc is not None:
            _close_document(doc)
        if commit_started:
            if backup_path is not None and backup_path.is_file():
                os.replace(backup_path, output_path)
            elif not previous_file_existed:
                output_path.unlink(missing_ok=True)
        if previous_doc_closed and output_path.is_file():
            try:
                session.doc = session.desktop.loadComponentFromURL(
                    output_url, "_blank", 0, ()
                )
            except Exception:
                session.doc = None
        else:
            session.doc = previous_doc
        raise
    except Exception as exc:
        if doc is not None:
            _close_document(doc)
        if commit_started:
            if backup_path is not None and backup_path.is_file():
                os.replace(backup_path, output_path)
            elif not previous_file_existed:
                output_path.unlink(missing_ok=True)
        if previous_doc_closed and output_path.is_file():
            try:
                session.doc = session.desktop.loadComponentFromURL(
                    output_url, "_blank", 0, ()
                )
            except Exception:
                session.doc = None
        else:
            session.doc = previous_doc
        raise AdapterError(
            "DOCUMENT_CREATE_FAILED",
            "LibreOffice failed to create the workbook",
            {"output_path": str(output_path), "error": str(exc)},
            500,
        ) from exc
    finally:
        stage_path.unlink(missing_ok=True)
        if backup_path is not None:
            backup_path.unlink(missing_ok=True)

    width = len(headers) if isinstance(headers, list) else 0
    height = 1 + len(rows or []) if headers is not None else 0
    table_state = (
        "header_only"
        if headers is not None and not rows_supplied
        else "complete_table"
        if headers is not None
        else "blank_workbook"
    )
    return {
        "url": output_url,
        "path": str(output_path),
        "format": output_path.suffix.lower().removeprefix("."),
        "size": output_path.stat().st_size,
        "sheet": sheet_name,
        "sheet_names": _sheet_names(doc),
        "header_count": width,
        "row_count": len(rows) if isinstance(rows, list) else 0,
        "written_cells": width * height,
        "table_state": table_state,
        "data_range": f"A1:{_column_label(width - 1)}{height}"
        if width and height
        else None,
        "saved": True,
    }


def _create_sheet(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheets = session.doc.getSheets()
    if sheets.hasByName(params["name"]):
        raise AdapterError(
            "CONFLICT", f"sheet already exists: {params['name']}", http_status=409
        )
    index = params.get("index", sheets.getCount())
    if index > sheets.getCount():
        raise AdapterError("INVALID_REQUEST", "sheet index is out of bounds")
    sheets.insertNewByName(params["name"], index)
    return {
        "sheet_names": _sheet_names(session.doc),
        "created": params["name"],
        "index": index,
    }


def _rename_sheet(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheets = session.doc.getSheets()
    if sheets.hasByName(params["new_name"]):
        raise AdapterError(
            "CONFLICT", f"sheet already exists: {params['new_name']}", http_status=409
        )
    session.sheet(params["sheet"]).setName(params["new_name"])
    return {"sheet_names": _sheet_names(session.doc), "renamed": params["new_name"]}


def _copy_sheet(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheets = session.doc.getSheets()
    session.sheet(params["sheet"])
    if sheets.hasByName(params["new_name"]):
        raise AdapterError(
            "CONFLICT", f"sheet already exists: {params['new_name']}", http_status=409
        )
    index = params.get("index", sheets.getCount())
    sheets.copyByName(params["sheet"], params["new_name"], index)
    return {
        "sheet_names": _sheet_names(session.doc),
        "copied": params["new_name"],
        "index": index,
    }


def _move_sheet(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheets = session.doc.getSheets()
    session.sheet(params["sheet"])
    target_index = params["index"]
    if target_index >= sheets.getCount():
        raise AdapterError("INVALID_REQUEST", "sheet index is out of bounds")
    current_names = _sheet_names(session.doc)
    current_index = current_names.index(params["sheet"])
    uno_index = target_index + 1 if target_index > current_index else target_index
    sheets.moveByName(params["sheet"], uno_index)
    final_names = _sheet_names(session.doc)
    final_index = final_names.index(params["sheet"])
    if final_index != target_index:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "LibreOffice did not move the sheet to the requested final index",
            {
                "sheet": params["sheet"],
                "requested_index": target_index,
                "observed_index": final_index,
                "sheet_names": final_names,
            },
            500,
        )
    return {"sheet_names": final_names, "index": final_index}


STYLE_PROPERTIES = (
    "CellBackColor",
    "CharColor",
    "CharWeight",
    "NumberFormat",
    "HoriJustify",
    "VertJustify",
)


def _copy_cell(source: Any, destination: Any, preserve_format: bool) -> None:
    formula = str(source.getFormula())
    if formula.startswith("="):
        destination.setFormula(formula)
    elif _cell_kind(source) == "number":
        destination.setValue(source.getValue())
    else:
        destination.setString(source.getString())
    if preserve_format:
        for prop in STYLE_PROPERTIES:
            try:
                setattr(destination, prop, getattr(source, prop))
            except Exception:
                continue


def _cell_state(cell: Any) -> dict[str, Any]:
    return {
        "formula": str(cell.getFormula()),
        "kind": _cell_kind(cell),
        "value": cell.getValue(),
        "string": cell.getString(),
        "style": {prop: getattr(cell, prop) for prop in STYLE_PROPERTIES},
    }


def _restore_cell_state(
    cell: Any,
    state: dict[str, Any],
    *,
    content: bool,
    style: bool,
    strict_style: bool = False,
) -> None:
    if content:
        if state["kind"] == "formula":
            cell.setFormula(state["formula"])
        elif state["kind"] == "number":
            cell.setValue(state["value"])
        else:
            cell.setString(state["string"])
    if style:
        for prop, value in state["style"].items():
            try:
                setattr(cell, prop, value)
            except Exception:
                if strict_style:
                    raise
                continue


def _fill_auto_to_bottom(cell_range: Any, source_rows: int) -> None:
    uno, _ = _uno_modules()
    try:
        cell_range.fillAuto(
            uno.Enum("com.sun.star.sheet.FillDirection", "TO_BOTTOM"),
            source_rows,
        )
    except Exception as exc:
        raise AdapterError(
            "FILL_FAILED",
            "LibreOffice failed to fill the selected range downward",
            str(exc),
            500,
        ) from exc


def _fill_down(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    mode = params["mode"]
    only_blank = bool(params.get("only_blank", True))
    preserve_format = bool(params.get("preserve_format", False))
    source_rows = int(params.get("source_rows", 1))
    a1_range = params["range"]
    target = sheet.getCellRangeByName(a1_range)
    address = target.getRangeAddress()
    rows = address.EndRow - address.StartRow + 1
    columns = address.EndColumn - address.StartColumn + 1
    if rows <= source_rows:
        raise AdapterError(
            "RANGE_INVALID",
            "fill range must contain source row(s) and at least one target row",
            {"range": a1_range, "rows": rows, "source_rows": source_rows},
        )

    filled = 0
    if mode == "previous_nonblank":
        for column in range(address.StartColumn, address.EndColumn + 1):
            for row in range(address.StartRow + 1, address.EndRow + 1):
                destination = sheet.getCellByPosition(column, row)
                if only_blank and _cell_kind(destination) != "blank":
                    continue
                source = sheet.getCellByPosition(column, row - 1)
                if _cell_kind(source) == "blank":
                    continue
                destination_state = _cell_state(destination)
                pair = sheet.getCellRangeByPosition(column, row - 1, column, row)
                _fill_auto_to_bottom(pair, 1)
                if not preserve_format:
                    _restore_cell_state(
                        destination, destination_state, content=False, style=True
                    )
                filled += 1
    else:
        source_has_formula = False
        for row in range(source_rows):
            for column in range(columns):
                if _cell_kind(target.getCellByPosition(column, row)) == "formula":
                    source_has_formula = True
                    break
            if source_has_formula:
                break
        if not source_has_formula:
            raise AdapterError(
                "INVALID_REQUEST",
                "formula_pattern requires at least one formula in the top source row(s)",
                {"range": a1_range, "source_rows": source_rows},
            )
        target_states: dict[tuple[int, int], dict[str, Any]] = {}
        for row in range(source_rows, rows):
            for column in range(columns):
                target_states[(column, row)] = _cell_state(
                    target.getCellByPosition(column, row)
                )
        _fill_auto_to_bottom(target, source_rows)
        for (column, row), state in target_states.items():
            cell = target.getCellByPosition(column, row)
            originally_blank = state["kind"] == "blank"
            if only_blank and not originally_blank:
                _restore_cell_state(cell, state, content=True, style=True)
                continue
            if not preserve_format:
                _restore_cell_state(cell, state, content=False, style=True)
            filled += 1

    session.doc.calculateAll()
    return {
        "sheet": params["sheet"],
        "range": a1_range,
        "mode": mode,
        "filled_cells": filled,
        "readback": _range_snapshot(target, session.doc),
    }


def _transform_text_value(value: str, operations: list[str]) -> str:
    transformed = value
    for operation in operations:
        if operation == "trim":
            transformed = transformed.strip()
        elif operation == "collapse_whitespace":
            transformed = re.sub(r"\s+", " ", transformed.strip())
        elif operation == "title_case":
            transformed = transformed.title()
        elif operation == "lowercase":
            transformed = transformed.lower()
        elif operation == "uppercase":
            transformed = transformed.upper()
    return transformed


def _text_properties(values: list[str]) -> dict[str, Any]:
    """Describe observed text, without claiming that a task is complete."""
    nonempty = [value for value in values if value]
    operations = ("trim", "collapse_whitespace", "title_case", "lowercase", "uppercase")
    return {
        "nonempty_cells": len(nonempty),
        "satisfied": {
            operation: bool(nonempty) and all(
                _transform_text_value(value, [operation]) == value for value in nonempty
            )
            for operation in operations
        },
    }


def _text_transform(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    source_sheet = session.sheet(params["source_sheet"])
    destination_sheet = session.sheet(params["destination_sheet"])
    source = source_sheet.getCellRangeByName(params["source_range"])
    destination_anchor = destination_sheet.getCellRangeByName(params["destination"])
    source_address = source.getRangeAddress()
    destination_address = destination_anchor.getRangeAddress()
    rows = source_address.EndRow - source_address.StartRow + 1
    columns = source_address.EndColumn - source_address.StartColumn + 1
    if (
        destination_address.StartRow + rows > 1_048_576
        or destination_address.StartColumn + columns > 16_384
    ):
        raise AdapterError("RANGE_INVALID", "destination range exceeds Calc limits")

    source_values: list[list[tuple[str, str]]] = []
    for row in range(rows):
        value_row = []
        for column in range(columns):
            cell = source.getCellByPosition(column, row)
            kind = _cell_kind(cell)
            if kind not in {"blank", "string"}:
                coordinate = f"{_column_label(source_address.StartColumn + column)}{source_address.StartRow + row + 1}"
                raise AdapterError(
                    "INVALID_REQUEST",
                    "range.text_transform accepts only text and blank source cells",
                    {"cell": coordinate, "kind": kind},
                )
            value_row.append((kind, str(cell.getString())))
        source_values.append(value_row)

    destination_before = _text_properties([
        str(destination_sheet.getCellByPosition(
            destination_address.StartColumn + column,
            destination_address.StartRow + row,
        ).getString())
        for row in range(rows) for column in range(columns)
    ])
    skip_blank = bool(params.get("skip_blank", False))
    written = 0
    for row, value_row in enumerate(source_values):
        for column, (kind, value) in enumerate(value_row):
            destination = destination_sheet.getCellByPosition(
                destination_address.StartColumn + column,
                destination_address.StartRow + row,
            )
            if kind == "blank" and skip_blank:
                continue
            destination.setString(
                ""
                if kind == "blank"
                else _transform_text_value(value, [params["operation"]])
            )
            written += 1

    end_column = destination_address.StartColumn + columns - 1
    end_row = destination_address.StartRow + rows - 1
    output_range = (
        f"{_column_label(destination_address.StartColumn)}{destination_address.StartRow + 1}:"
        f"{_column_label(end_column)}{end_row + 1}"
    )
    session.doc.calculateAll()
    readback = _range_snapshot(destination_sheet.getCellRangeByName(output_range), session.doc)
    destination_after = _text_properties([
        str(value) for row in readback["display_text"] for value in row
    ])
    return {
        "text_properties": destination_after,
        "lost_text_properties": [
            name for name, satisfied in destination_before["satisfied"].items()
            if satisfied and not destination_after["satisfied"][name]
        ],
        "source_sheet": params["source_sheet"],
        "source_range": params["source_range"],
        "destination_sheet": params["destination_sheet"],
        "destination_range": output_range,
        "operation": params["operation"],
        "written_cells": written,
        "readback": readback,
    }


def _formula_string_literal(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _compose_text_column(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    source_sheet = session.sheet(params["source_sheet"])
    destination_sheet = session.sheet(params["destination_sheet"])
    source = source_sheet.getCellRangeByName(params["source_range"])
    destination = destination_sheet.getCellRangeByName(params["destination"])
    source_address = source.getRangeAddress()
    destination_address = destination.getRangeAddress()
    rows = source_address.EndRow - source_address.StartRow + 1
    columns = source_address.EndColumn - source_address.StartColumn + 1
    if rows < 2:
        raise AdapterError(
            "RANGE_INVALID",
            "source_range must contain a header row and at least one data row",
        )
    if destination_address.StartRow + rows > 1_048_576:
        raise AdapterError("RANGE_INVALID", "destination range exceeds Calc limits")

    headers = [
        str(source.getCellByPosition(column, 0).getString()).strip()
        for column in range(columns)
    ]
    if any(not header for header in headers):
        raise AdapterError(
            "INVALID_REQUEST",
            "every source column must have a non-empty header",
            {"headers": headers},
        )

    include_headers = bool(params.get("include_headers", True))
    decimal_places = int(params["decimal_places"])
    field_separator = resolve_text_separator(
        params,
        literal_key="field_separator",
        style_key="field_separator_style",
        styles=FIELD_SEPARATOR_STYLES,
        default=", ",
    )
    label_separator = resolve_text_separator(
        params,
        literal_key="label_separator",
        style_key="label_separator_style",
        styles=LABEL_SEPARATOR_STYLES,
        default=": ",
    )
    destination_column = destination_address.StartColumn
    destination_row = destination_address.StartRow
    destination_sheet.getCellByPosition(destination_column, destination_row).setString(
        params["header"]
    )
    for row_offset in range(1, rows):
        source_row = source_address.StartRow + row_offset + 1
        parts: list[str] = []
        for column_offset, header in enumerate(headers):
            source_column = _column_label(source_address.StartColumn + column_offset)
            reference = f"{source_column}{source_row}"
            value_expression = f"IF(ISNUMBER({reference});FIXED({reference};{decimal_places};1);{reference})"
            if include_headers:
                parts.extend(
                    [
                        _formula_string_literal(header),
                        _formula_string_literal(label_separator),
                    ]
                )
            parts.append(value_expression)
            if column_offset < columns - 1:
                parts.append(_formula_string_literal(field_separator))
        destination_sheet.getCellByPosition(
            destination_column, destination_row + row_offset
        ).setFormula("=" + "&".join(parts))

    end_row = destination_row + rows - 1
    output_range = (
        f"{_column_label(destination_column)}{destination_row + 1}:"
        f"{_column_label(destination_column)}{end_row + 1}"
    )
    session.doc.calculateAll()
    target = destination_sheet.getCellRangeByName(output_range)
    readback = _range_snapshot(target, session.doc)
    error_cells = []
    for row_offset, row in enumerate(readback.get("display_text", [])):
        for column_offset, value in enumerate(row):
            if (
                str(value)
                .strip()
                .upper()
                .startswith(("#NAME?", "#VALUE!", "#REF!", "#DIV/0!", "#N/A"))
            ):
                error_cells.append(
                    f"{_column_label(destination_column + column_offset)}"
                    f"{destination_row + row_offset + 1}"
                )
    if error_cells:
        raise AdapterError(
            "FORMULA_ERROR",
            "composed text formulas produced spreadsheet errors",
            {"cells": error_cells},
            422,
        )
    return {
        "source_sheet": params["source_sheet"],
        "source_range": params["source_range"],
        "destination_sheet": params["destination_sheet"],
        "destination_range": output_range,
        "header": params["header"],
        "decimal_places": decimal_places,
        "field_separator_style": params.get("field_separator_style"),
        "label_separator_style": params.get("label_separator_style"),
        "field_separator_text": field_separator,
        "label_separator_text": label_separator,
        "written_cells": rows,
        "error_cells": [],
        "readback": readback,
    }


def _copy_range(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    source = session.sheet(params["source_sheet"]).getCellRangeByName(
        params["source_range"]
    )
    destination_sheet = session.sheet(params["destination_sheet"])
    destination = destination_sheet.getCellRangeByName(params["destination"])
    source_address = source.getRangeAddress()
    dest_address = destination.getRangeAddress()
    source_rows = source_address.EndRow - source_address.StartRow + 1
    source_columns = source_address.EndColumn - source_address.StartColumn + 1
    transpose = bool(params.get("transpose", False))
    dest_rows = source_columns if transpose else source_rows
    dest_columns = source_rows if transpose else source_columns
    if (
        dest_address.StartRow + dest_rows > 1_048_576
        or dest_address.StartColumn + dest_columns > 16_384
    ):
        raise AdapterError("RANGE_INVALID", "destination range exceeds Calc limits")
    preserve_format = bool(params.get("preserve_format", True))
    for row in range(source_rows):
        for column in range(source_columns):
            dest_row, dest_column = (column, row) if transpose else (row, column)
            target = destination_sheet.getCellByPosition(
                dest_address.StartColumn + dest_column, dest_address.StartRow + dest_row
            )
            _copy_cell(source.getCellByPosition(column, row), target, preserve_format)
    session.doc.calculateAll()
    return {
        "copied_cells": source_rows * source_columns,
        "rows": dest_rows,
        "columns": dest_columns,
    }


def _scaled_number_format(
    divisor: int,
    decimal_places: int,
    unit: str,
    separator: str = " ",
) -> str:
    scale_steps = 0
    scaled = divisor
    while scaled > 1:
        if scaled % 1000:
            raise AdapterError(
                "INVALID_REQUEST", "divisor must be an integer power of 1000"
            )
        scaled //= 1000
        scale_steps += 1
    numeric = "0" + (
        f".{''.join('0' for _ in range(decimal_places))}" if decimal_places else ""
    )
    literal = f"{separator}{unit}"
    return f'{numeric}{"," * scale_steps}"{literal}"'


def _scaled_separator(value: Any) -> str:
    if value == "space":
        return " "
    if value == "none":
        return ""
    return str(value)


def _set_scaled_display(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    target = session.sheet(params["sheet"]).getCellRangeByName(params["range"])
    separator = _scaled_separator(params.get("separator", "space"))
    format_code = _scaled_number_format(
        int(params["divisor"]),
        int(params["decimal_places"]),
        str(params["unit"]),
        separator,
    )
    _apply_number_format(session.doc, target, format_code, params.get("locale"))
    session.doc.calculateAll()
    return {
        "sheet": params["sheet"],
        "range": params["range"],
        "divisor": params["divisor"],
        "decimal_places": params["decimal_places"],
        "unit": params["unit"],
        "separator": params.get("separator", "space"),
        "separator_text": separator,
        "rounding_mode": params.get("rounding_mode", "half_up"),
        "number_format": format_code,
        "readback": _range_snapshot(target, session.doc),
    }


def _copy_with_scaled_display(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    copy_result = _copy_range(
        session,
        {
            "source_sheet": params["source_sheet"],
            "source_range": params["source_range"],
            "destination_sheet": params["destination_sheet"],
            "destination": params["destination"],
            "preserve_format": bool(params.get("preserve_format", False)),
        },
    )
    destination_sheet = session.sheet(params["destination_sheet"])
    destination = destination_sheet.getCellRangeByName(params["destination"])
    address = destination.getRangeAddress()
    end_column = address.StartColumn + copy_result["columns"] - 1
    end_row = address.StartRow + copy_result["rows"] - 1
    output_range = (
        f"{_column_label(address.StartColumn)}{address.StartRow + 1}:"
        f"{_column_label(end_column)}{end_row + 1}"
    )
    target = destination_sheet.getCellRangeByName(output_range)
    separator = _scaled_separator(params.get("separator", "space"))
    format_code = _scaled_number_format(
        int(params["divisor"]),
        int(params["decimal_places"]),
        str(params["unit"]),
        separator,
    )
    _apply_number_format(session.doc, target, format_code, params.get("locale"))
    session.doc.calculateAll()
    return {
        **copy_result,
        "source_sheet": params["source_sheet"],
        "source_range": params["source_range"],
        "destination_sheet": params["destination_sheet"],
        "destination_range": output_range,
        "divisor": params["divisor"],
        "decimal_places": params["decimal_places"],
        "unit": params["unit"],
        "separator": params.get("separator", "space"),
        "separator_text": separator,
        "rounding_mode": params.get("rounding_mode", "half_up"),
        "number_format": format_code,
        "readback": _range_snapshot(target, session.doc),
    }


def _merge(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    cell_range = session.sheet(params["sheet"]).getCellRangeByName(params["range"])
    merged = params.get("merge", True)
    cell_range.merge(merged)
    return {
        "sheet": params["sheet"],
        "range": params["range"],
        "merged": bool(cell_range.IsMerged),
    }


def _formula_sheet_reference(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"


def _aggregate_column_plan(
    source: Any,
    *,
    source_sheet: str,
    aggregation: str,
    exclude_headers: set[str],
) -> list[dict[str, Any]]:
    address = source.getRangeAddress()
    row_count = address.EndRow - address.StartRow + 1
    column_count = address.EndColumn - address.StartColumn + 1
    if row_count < 2:
        raise AdapterError(
            "RANGE_INVALID",
            "source table requires a header row and at least one data row",
        )
    function = {
        "sum": "SUM",
        "count": "COUNT",
        "average": "AVERAGE",
        "min": "MIN",
        "max": "MAX",
    }[aggregation]
    sheet_reference = _formula_sheet_reference(source_sheet)
    plan = []
    for relative_column in range(column_count):
        header = source.getCellByPosition(relative_column, 0).getString().strip()
        if not header or header in exclude_headers:
            continue
        data_cells = [
            source.getCellByPosition(relative_column, relative_row)
            for relative_row in range(1, row_count)
        ]
        if not any(_cell_kind(cell) in {"number", "formula"} for cell in data_cells):
            continue
        absolute_column = address.StartColumn + relative_column
        start = f"{_column_label(absolute_column)}{address.StartRow + 2}"
        end = f"{_column_label(absolute_column)}{address.EndRow + 1}"
        plan.append(
            {
                "header": header,
                "source_range": f"{start}:{end}",
                "formula": f"={function}({sheet_reference}.{start}:{end})",
            }
        )
    if not plan:
        raise AdapterError(
            "CONFLICT", "source range contains no non-excluded numeric data columns"
        )
    headers = [item["header"] for item in plan]
    if len(headers) != len(set(headers)):
        raise AdapterError(
            "CONFLICT",
            "numeric source columns must have unique nonblank headers",
            headers,
        )
    return plan


def _aggregate_columns(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    source_sheet = session.sheet(params["source_sheet"])
    source = source_sheet.getCellRangeByName(params["source_range"])
    plan = _aggregate_column_plan(
        source,
        source_sheet=params["source_sheet"],
        aggregation=params["aggregation"],
        exclude_headers=set(params.get("exclude_headers", [])),
    )
    destination_sheet = session.sheet(params["destination_sheet"])
    destination = destination_sheet.getCellRangeByName(params["destination"])
    destination_address = destination.getRangeAddress()
    if (
        destination_address.StartColumn != destination_address.EndColumn
        or destination_address.StartRow != destination_address.EndRow
    ):
        raise AdapterError(
            "RANGE_INVALID", "destination must identify one top-left cell"
        )

    start_column = destination_address.StartColumn
    start_row = destination_address.StartRow
    end_column = start_column + 1
    end_row = start_row + len(plan)
    if params["source_sheet"] == params["destination_sheet"]:
        source_address = source.getRangeAddress()
        overlaps = not (
            end_column < source_address.StartColumn
            or start_column > source_address.EndColumn
            or end_row < source_address.StartRow
            or start_row > source_address.EndRow
        )
        if overlaps:
            raise AdapterError(
                "CONFLICT", "destination table must not overlap its source range"
            )

    destination_sheet.getCellByPosition(start_column, start_row).setString(
        params["label_header"]
    )
    destination_sheet.getCellByPosition(start_column + 1, start_row).setString(
        params["value_header"]
    )
    for offset, item in enumerate(plan, 1):
        destination_sheet.getCellByPosition(start_column, start_row + offset).setString(
            item["header"]
        )
        destination_sheet.getCellByPosition(
            start_column + 1, start_row + offset
        ).setFormula(item["formula"])
    session.doc.calculateAll()
    output = destination_sheet.getCellRangeByPosition(
        start_column, start_row, end_column, end_row
    )
    return {
        "source_sheet": params["source_sheet"],
        "source_range": params["source_range"],
        "destination_sheet": params["destination_sheet"],
        "destination_range": _range_a1(output.getRangeAddress()),
        "aggregation": params["aggregation"],
        "columns": plan,
        "readback": _range_snapshot(output, session.doc),
    }


def _expanded_contiguous_source(
    session: CalcSession,
    sheet: Any,
    requested_range: str,
    *,
    stop_labels: Iterable[str] = (),
) -> tuple[Any, dict[str, Any]]:
    """Expand a model-selected table slice through its live contiguous rows."""
    requested = sheet.getCellRangeByName(requested_range)
    requested_address = requested.getRangeAddress()
    used = _used_range(sheet)
    observed_end_row = max(requested_address.EndRow, used["end_row"])
    observed = sheet.getCellRangeByPosition(
        requested_address.StartColumn,
        requested_address.StartRow,
        requested_address.EndColumn,
        observed_end_row,
    )
    observed_snapshot = _range_snapshot(observed, session.doc)
    requested_rows = requested_address.EndRow - requested_address.StartRow + 1
    try:
        row_count = contiguous_table_row_count(
            observed_snapshot["display_text"],
            minimum_rows=max(2, requested_rows),
            stop_labels=list(stop_labels),
        )
    except SemanticTableError as exc:
        raise AdapterError("CONFLICT", str(exc)) from exc
    source = sheet.getCellRangeByPosition(
        requested_address.StartColumn,
        requested_address.StartRow,
        requested_address.EndColumn,
        requested_address.StartRow + row_count - 1,
    )
    return source, _range_snapshot(source, session.doc)


def _append_summary_rows(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    source, snapshot = _expanded_contiguous_source(
        session,
        sheet,
        params["source_range"],
        stop_labels=[summary["label"] for summary in params["summaries"]],
    )
    source_address = source.getRangeAddress()
    try:
        plan = plan_append_summary_rows(
            snapshot["display_text"],
            snapshot["kinds"],
            start_column=source_address.StartColumn,
            start_row=source_address.StartRow,
            summaries=params["summaries"],
        )
    except SemanticTableError as exc:
        raise AdapterError("CONFLICT", str(exc)) from exc

    destination = sheet.getCellRangeByPosition(
        source_address.StartColumn,
        plan[0]["row"],
        source_address.EndColumn,
        plan[-1]["row"],
    )
    if _range_has_content(destination):
        raise AdapterError(
            "CONFLICT",
            "summary destination rows are not blank",
            {"destination_range": _range_a1(destination.getRangeAddress())},
        )

    for row in plan:
        for cell_spec in row["cells"]:
            cell = sheet.getCellRangeByName(cell_spec["coordinate"])
            if cell_spec["kind"] == "string":
                cell.setString(cell_spec["value"])
            elif cell_spec["kind"] == "formula":
                cell.setFormula(cell_spec["formula"])
            else:
                cell.setString("")
        if row["operation"] == "period_over_period_change":
            first_numeric_cell = row["cells"][1]["coordinate"]
            last_cell = row["cells"][-1]["coordinate"]
            _apply_number_format(
                session.doc,
                sheet.getCellRangeByName(f"{first_numeric_cell}:{last_cell}"),
                params.get("percentage_number_format", "0.00%"),
            )
    session.doc.calculateAll()
    return {
        "sheet": params["sheet"],
        "requested_source_range": params["source_range"],
        "source_range": _range_a1(source_address),
        "summary_rows": [
            {
                "label": row["label"],
                "operation": row["operation"],
                "range": row["range"],
                "formulas": [
                    {
                        "coordinate": cell["coordinate"],
                        "formula": cell["formula"],
                    }
                    for cell in row["cells"]
                    if cell["kind"] == "formula"
                ],
            }
            for row in plan
        ],
        "destination_range": _range_a1(destination.getRangeAddress()),
        "readback": _range_snapshot(destination, session.doc),
    }


def _create_year_over_year_summary(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    source_sheet = session.sheet(params["source_sheet"])
    source = source_sheet.getCellRangeByName(params["source_range"])
    source_address = source.getRangeAddress()
    source_snapshot = _range_snapshot(source, session.doc)

    destination_sheet = session.sheet(params["destination_sheet"])
    try:
        requested_destination = destination_a1(
            params["destination_column"], params["destination_row"]
        )
    except YearOverYearError as exc:
        raise AdapterError("RANGE_INVALID", str(exc)) from exc
    destination_anchor = destination_sheet.getCellRangeByName(requested_destination)
    destination_address = destination_anchor.getRangeAddress()
    if (
        destination_address.StartColumn != destination_address.EndColumn
        or destination_address.StartRow != destination_address.EndRow
    ):
        raise AdapterError(
            "RANGE_INVALID", "destination must identify one top-left cell"
        )
    try:
        plan = plan_year_over_year_summary(
            source_snapshot["display_text"],
            source_snapshot["kinds"],
            source_sheet=params["source_sheet"],
            source_start_column=source_address.StartColumn,
            source_start_row=source_address.StartRow,
            destination_start_column=destination_address.StartColumn,
            destination_start_row=destination_address.StartRow,
            year_field=params["year_field"],
            value_fields=params["value_fields"],
            output_headers=params["output_headers"],
            start_year=params["start_year"],
            end_year=params["end_year"],
        )
    except YearOverYearError as exc:
        raise AdapterError("CONFLICT", str(exc)) from exc

    target = destination_sheet.getCellRangeByName(plan["output_range"])
    target_address = target.getRangeAddress()
    if params["source_sheet"].casefold() == params["destination_sheet"].casefold():
        overlaps = not (
            target_address.EndColumn < source_address.StartColumn
            or target_address.StartColumn > source_address.EndColumn
            or target_address.EndRow < source_address.StartRow
            or target_address.StartRow > source_address.EndRow
        )
        if overlaps:
            raise AdapterError(
                "CONFLICT", "destination table must not overlap its source range"
            )
    if _range_has_content(target):
        raise AdapterError(
            "CONFLICT",
            "year-over-year summary destination is not blank",
            {"destination_range": plan["output_range"]},
        )

    start_column = destination_address.StartColumn
    start_row = destination_address.StartRow
    for column_offset, header in enumerate(plan["output_headers"]):
        destination_sheet.getCellByPosition(
            start_column + column_offset, start_row
        ).setString(header)
    for row in plan["rows"]:
        destination_sheet.getCellByPosition(
            start_column, row["destination_row"]
        ).setValue(float(row["year"]))
        for column_offset, formula in enumerate(row["formulas"], start=1):
            destination_sheet.getCellByPosition(
                start_column + column_offset, row["destination_row"]
            ).setFormula(formula)
    number_format = params.get("number_format", "0.00%")
    _apply_number_format(
        session.doc,
        destination_sheet.getCellRangeByName(plan["percentage_range"]),
        number_format,
    )
    session.doc.calculateAll()
    readback = _range_snapshot(target, session.doc)
    return {
        "source_sheet": params["source_sheet"],
        "source_range": params["source_range"],
        "destination_sheet": params["destination_sheet"],
        "destination_column": params["destination_column"],
        "destination_row": params["destination_row"],
        "destination_range": plan["output_range"],
        "percentage_range": plan["percentage_range"],
        "year_field": params["year_field"],
        "resolved_year_field": plan["resolved_year_field"],
        "value_fields": list(params["value_fields"]),
        "resolved_value_fields": plan["resolved_value_fields"],
        "output_headers": plan["output_headers"],
        "start_year": params["start_year"],
        "end_year": params["end_year"],
        "number_format": number_format,
        "formula_count": sum(len(row["formulas"]) for row in plan["rows"]),
        "readback": readback,
    }


def _add_ratio_column(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    source = sheet.getCellRangeByName(params["source_range"])
    source_address = source.getRangeAddress()
    snapshot = _range_snapshot(source, session.doc)
    try:
        plan = plan_ratio_column(
            snapshot["display_text"],
            snapshot["kinds"],
            start_column=source_address.StartColumn,
            start_row=source_address.StartRow,
            numerator_header=params["numerator_header"],
            denominator_header=params["denominator_header"],
        )
    except SemanticTableError as exc:
        raise AdapterError("CONFLICT", str(exc)) from exc
    target = sheet.getCellRangeByName(plan["output_range"])
    if _range_has_content(target):
        raise AdapterError(
            "CONFLICT",
            "ratio-column destination is not blank",
            {"output_range": plan["output_range"]},
        )
    sheet.getCellRangeByName(plan["header_coordinate"]).setString(
        params["output_header"]
    )
    for item in plan["formulas"]:
        sheet.getCellRangeByName(item["coordinate"]).setFormula(item["formula"])
    _apply_number_format(
        session.doc,
        sheet.getCellRangeByName(plan["data_range"]),
        params.get("number_format", "0.00"),
    )
    session.doc.calculateAll()
    return {
        "sheet": params["sheet"],
        "source_range": params["source_range"],
        "numerator_header": params["numerator_header"],
        "denominator_header": params["denominator_header"],
        "output_header": params["output_header"],
        "output_range": plan["output_range"],
        "data_range": plan["data_range"],
        "formula_count": len(plan["formulas"]),
        "readback": _range_snapshot(target, session.doc),
    }


def _locale(value: str | None):
    uno, _ = _uno_modules()
    locale = uno.createUnoStruct("com.sun.star.lang.Locale")
    if value:
        parts = value.replace("_", "-").split("-", 1)
        locale.Language = parts[0]
        locale.Country = parts[1].upper() if len(parts) > 1 else ""
    else:
        locale.Language = "en"
        locale.Country = "US"
    return locale


def _apply_number_format(
    doc: Any, target: Any, format_code: str, locale_value: str | None = None
) -> int:
    formats = doc.getNumberFormats()
    locale = _locale(locale_value)
    key = formats.queryKey(format_code, locale, True)
    if key == -1:
        # UNO's lookup is case-sensitive, while addNew parses date/time tokens
        # case-insensitively and rejects a duplicate built-in format. Preserve
        # quoted, escaped, fill and bracket literals when finding that existing
        # native format; never uppercase a displayed unit or currency label.
        canonical = re.sub(
            r'"[^"]*"|\\.|_.|\*.|\[[^\]]*\]|[A-Za-z]+',
            lambda match: match[0].upper()
            if re.fullmatch(r"[ymdhs]+", match[0], re.IGNORECASE)
            else match[0],
            format_code,
        )
        if canonical != format_code:
            key = formats.queryKey(canonical, locale, True)
    if key == -1:
        key = formats.addNew(format_code, locale)
    target.NumberFormat = key
    return int(key)


def _apply_format(session: CalcSession, target: Any, spec: dict[str, Any]) -> None:
    if "background_color" in spec:
        target.CellBackColor = _color(spec["background_color"])
    if "font_color" in spec:
        target.CharColor = _color(spec["font_color"])
    if "bold" in spec:
        if not isinstance(spec["bold"], bool):
            raise AdapterError("INVALID_REQUEST", "format.bold must be a boolean")
        target.CharWeight = 150.0 if spec["bold"] else 100.0
    if "number_format" in spec:
        _apply_number_format(
            session.doc, target, str(spec["number_format"]), spec.get("locale")
        )
    uno, _ = _uno_modules()
    if "horizontal_alignment" in spec:
        mapping = {
            "left": "LEFT",
            "center": "CENTER",
            "right": "RIGHT",
            "standard": "STANDARD",
        }
        key = str(spec["horizontal_alignment"]).lower()
        if key not in mapping:
            raise AdapterError("INVALID_REQUEST", "unsupported horizontal alignment")
        target.HoriJustify = uno.Enum(
            "com.sun.star.table.CellHoriJustify", mapping[key]
        )
    if "vertical_alignment" in spec:
        mapping = {
            "top": "TOP",
            "center": "CENTER",
            "bottom": "BOTTOM",
            "standard": "STANDARD",
        }
        key = str(spec["vertical_alignment"]).lower()
        if key not in mapping:
            raise AdapterError("INVALID_REQUEST", "unsupported vertical alignment")
        target.VertJustify = uno.Enum(
            "com.sun.star.table.CellVertJustify", mapping[key]
        )


def _format_range(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    requested_range = params["range"]
    selected_ranges = (requested_range,)
    resolved: list[tuple[str, Any]] = []
    applied_ranges: list[str] = []
    unattempted_ranges = list(selected_ranges)
    failed_range = requested_range
    stage = "resolve"
    try:
        try:
            resolved = [(requested_range, sheet.getCellRangeByName(requested_range))]
        except Exception:
            explicit_ranges = explicit_format_ranges(requested_range)
            if explicit_ranges is None:
                raise
            selected_ranges = explicit_ranges
            unattempted_ranges = list(selected_ranges)
            for selected_range in selected_ranges:
                failed_range = selected_range
                resolved.append((selected_range, sheet.getCellRangeByName(selected_range)))

        stage = "apply"
        for index, (selected_range, target) in enumerate(resolved):
            failed_range = selected_range
            unattempted_ranges = list(selected_ranges[index + 1:])
            _apply_format(session, target, params["format"])
            applied_ranges.append(selected_range)

        stage = "readback"
        range_results = []
        for selected_range, target in resolved:
            failed_range = selected_range
            address = target.getRangeAddress()
            end_column = min(address.EndColumn, address.StartColumn + 15)
            end_row = min(address.EndRow, address.StartRow + 31)
            truncated = end_column < address.EndColumn or end_row < address.EndRow
            # Apply formatting to the full model-selected target. Only the
            # returned observation is bounded, including for entire rows/columns.
            preview = (
                sheet.getCellRangeByPosition(
                    address.StartColumn, address.StartRow, end_column, end_row
                )
                if truncated else target
            )
            snapshot = _range_snapshot(preview, session.doc)
            range_results.append(
                {
                    "range": selected_range,
                    **({
                        "readback_range": _range_a1(preview.getRangeAddress()),
                        "truncated": True,
                    } if truncated else {}),
                    "styles": snapshot["styles"],
                    "display_text": snapshot["display_text"],
                    "date_cells": snapshot.get("date_cells", {}),
                    "background_cells": snapshot["background_cells"],
                }
            )
    except Exception as exc:
        guidance = {
            "resolve": (
                "No formatting was applied. Use one native range or comma-separated "
                "unqualified A1 cells/ranges such as D4,D9:E10."
            ),
            "apply": (
                "Applied ranges remain changed; the failed range may be partly changed. "
                "Inspect the reported areas before retrying."
            ),
            "readback": (
                "Formatting was applied to all selected ranges, but read-back failed. "
                "Inspect the selected areas before retrying."
            ),
        }[stage]
        details = {
            "sheet": params["sheet"],
            "range": requested_range,
            "stage": stage,
            "applied_ranges": applied_ranges,
            "failed_range": failed_range,
            "failed_range_may_be_partially_formatted": stage == "apply",
            "unattempted_ranges": unattempted_ranges,
            "guidance": guidance,
            "native_error": str(exc),
            "traceback": traceback.format_exc()[-8000:],
        }
        if isinstance(exc, AdapterError):
            details["adapter_error_details"] = exc.details
            raise AdapterError(exc.code, exc.message, details, exc.http_status) from exc
        raise AdapterError(
            "INTERNAL_ERROR",
            f"range.format failed during {stage}. {guidance} Native error: {exc}",
            details,
            500,
        ) from exc
    result = {
        "sheet": params["sheet"],
        "range": requested_range,
        "formatted_ranges": applied_ranges,
        "range_results": range_results,
        "date_cells": {
            address: observation
            for item in range_results
            for address, observation in item["date_cells"].items()
        },
        "background_cells": {
            address: color
            for item in range_results
            for address, color in item["background_cells"].items()
        },
    }
    if any(item.get("truncated") for item in range_results):
        result.update(
            truncated=True,
            date_cells_truncated=True,
            background_cells_truncated=True,
        )
    if len(range_results) == 1:
        result["styles"] = range_results[0]["styles"]
    return result


_COMMA_DECIMAL_LANGUAGES = frozenset(
    {
        "de",
        "es",
        "fr",
        "it",
        "nl",
        "pl",
        "pt",
        "ru",
        "tr",
        "uk",
    }
)


def _is_date_number_format(format_code: str | None) -> bool:
    if not format_code:
        return False
    normalized = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", format_code).lower()
    return "d" in normalized and "m" in normalized


def _visible_decimal_places(
    display_text: str, format_code: str | None, locale_name: str | None
) -> int:
    """Infer displayed precision without inspecting or changing the numeric value."""
    code = str(format_code or "").split(";", 1)[0]
    normalized = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", code)
    language = str(locale_name or "en").replace("_", "-").split("-", 1)[0]
    decimal = "," if language in _COMMA_DECIMAL_LANGUAGES else "."
    if normalized and normalized.casefold() != "general":
        if decimal not in normalized:
            return 0
        suffix = normalized.rsplit(decimal, 1)[1]
        placeholders = re.match(r"[0#?]+", suffix)
        return len(placeholders.group(0)) if placeholders else 0

    matches = re.findall(r"[.,](\d+)", str(display_text).strip())
    return len(matches[-1]) if matches else 0


def _set_decimal_separator(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    target = session.sheet(params["sheet"]).getCellRangeByName(params["range"])
    address = target.getRangeAddress()
    separator = params["separator"]
    decimal = "," if separator == "comma" else "."
    locale_name = "de-DE" if separator == "comma" else "en-US"
    formatted_cells: list[dict[str, Any]] = []
    skipped_non_numeric = 0
    skipped_date_formatted = 0

    for row_offset in range(address.EndRow - address.StartRow + 1):
        for column_offset in range(address.EndColumn - address.StartColumn + 1):
            cell = target.getCellByPosition(column_offset, row_offset)
            if _cell_kind(cell) not in {"number", "formula"}:
                skipped_non_numeric += 1
                continue
            details = _number_format_details(session.doc, int(cell.NumberFormat))
            if _is_date_number_format(details.get("code")):
                skipped_date_formatted += 1
                continue
            places = _visible_decimal_places(
                str(cell.getString()), details.get("code"), details.get("locale")
            )
            format_code = "0" + (decimal + ("0" * places) if places else "")
            number_format_id = _apply_number_format(
                session.doc, cell, format_code, locale_name
            )
            formatted_cells.append(
                {
                    "cell": (
                        f"{_column_label(address.StartColumn + column_offset)}"
                        f"{address.StartRow + row_offset + 1}"
                    ),
                    "decimal_places": places,
                    "number_format": format_code,
                    "number_format_id": number_format_id,
                }
            )

    return {
        "sheet": params["sheet"],
        "range": params["range"],
        "separator": separator,
        "locale": locale_name,
        "formatted_cell_count": len(formatted_cells),
        "formatted_cells": formatted_cells,
        "skipped_non_numeric": skipped_non_numeric,
        "skipped_date_formatted": skipped_date_formatted,
        "readback": _range_snapshot(target, session.doc),
    }


def _set_text_and_format(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    target = sheet.getCellRangeByName(params["range"])
    address = target.getRangeAddress()
    merged = bool(params.get("merge", False))
    if merged:
        target.merge(True)
    sheet.getCellByPosition(address.StartColumn, address.StartRow).setString(
        params["text"]
    )
    format_spec = params.get("format", {})
    if format_spec:
        _apply_format(session, target, format_spec)
    session.doc.calculateAll()
    return {
        "sheet": params["sheet"],
        "range": params["range"],
        "anchor": f"{_column_label(address.StartColumn)}{address.StartRow + 1}",
        "text": params["text"],
        "merged": bool(target.IsMerged),
        "format": dict(format_spec),
        "readback": _range_snapshot(target, session.doc),
    }


def _set_validation(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    uno, _ = _uno_modules()
    target = session.sheet(params["sheet"]).getCellRangeByName(params["range"])
    validation = target.Validation
    validation.Type = uno.Enum("com.sun.star.sheet.ValidationType", "LIST")
    escaped = [value.replace('"', '""') for value in params["values"]]
    validation.Formula1 = ";".join(f'"{value}"' for value in escaped)
    validation.ShowList = 1
    validation.IgnoreBlankCells = bool(params.get("allow_blank", True))
    validation.ShowErrorMessage = bool(params.get("show_error", True))
    target.Validation = validation
    return {
        "sheet": params["sheet"],
        "range": params["range"],
        "values": params["values"],
    }


def _sort_table(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    uno, _ = _uno_modules()
    target = session.sheet(params["sheet"]).getCellRangeByName(params["range"])
    address = target.getRangeAddress()
    columns = address.EndColumn - address.StartColumn + 1
    fields = []
    for raw in params["keys"]:
        if not isinstance(raw, dict):
            raise AdapterError("INVALID_REQUEST", "sort keys must be objects")
        index = raw.get("column")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < columns
        ):
            raise AdapterError(
                "INVALID_REQUEST", "sort key column is outside the table range"
            )
        field = uno.createUnoStruct("com.sun.star.table.TableSortField")
        field.Field = index
        field.IsAscending = bool(raw.get("ascending", True))
        field.IsCaseSensitive = bool(raw.get("case_sensitive", False))
        field.FieldType = uno.Enum(
            "com.sun.star.table.TableSortFieldType",
            str(raw.get("type", "automatic")).upper(),
        )
        fields.append(field)
    descriptor = list(target.createSortDescriptor())
    for prop in descriptor:
        if prop.Name == "SortFields":
            prop.Value = uno.Any("[]com.sun.star.table.TableSortField", tuple(fields))
        elif prop.Name == "ContainsHeader":
            prop.Value = bool(params.get("contains_header", True))
        elif prop.Name == "BindFormatsToContent":
            prop.Value = True
    target.sort(tuple(descriptor))
    session.doc.calculateAll()
    return {
        "sheet": params["sheet"],
        "range": params["range"],
        "keys": params["keys"],
        "sorted_rows": address.EndRow
        - address.StartRow
        + (0 if params.get("contains_header", True) else 1),
    }


def _reorder_table_target(sheet: Any, requested_range: str) -> tuple[Any, bool]:
    target = sheet.getCellRangeByName(requested_range)
    address = target.getRangeAddress()
    if address.StartRow != address.EndRow:
        return target, False

    end_row = address.EndRow
    used_end_row = _used_range(sheet)["end_row"]
    for row in range(address.EndRow + 1, used_end_row + 1):
        if not any(
            _cell_kind(sheet.getCellByPosition(column, row)) != "blank"
            for column in range(address.StartColumn, address.EndColumn + 1)
        ):
            break
        end_row = row
    if end_row == address.EndRow:
        return target, False
    return (
        sheet.getCellRangeByPosition(
            address.StartColumn,
            address.StartRow,
            address.EndColumn,
            end_row,
        ),
        True,
    )


def _range_a1(address: Any) -> str:
    start = f"{_column_label(address.StartColumn)}{address.StartRow + 1}"
    end = f"{_column_label(address.EndColumn)}{address.EndRow + 1}"
    return start if start == end else f"{start}:{end}"


def _trim_reorder_target_to_requested_headers(
    sheet: Any, target: Any, requested: list[str]
) -> tuple[Any, bool]:
    """Trim only completely blank edge columns accidentally included by selection."""
    address = target.getRangeAddress()
    rows = address.EndRow - address.StartRow + 1
    columns = address.EndColumn - address.StartColumn + 1
    headers = [
        target.getCellByPosition(column, 0).getString() for column in range(columns)
    ]
    if len(requested) == columns and set(requested) == set(headers):
        return target, False
    selected = [index for index, header in enumerate(headers) if header in requested]
    if not selected or len(selected) != len(requested):
        return target, False
    first, last = min(selected), max(selected)
    if selected != list(range(first, last + 1)):
        return target, False
    if set(headers[first : last + 1]) != set(requested):
        return target, False
    omitted = [*range(0, first), *range(last + 1, columns)]
    if any(headers[index].strip() for index in omitted):
        return target, False
    if any(
        _cell_kind(target.getCellByPosition(column, row)) != "blank"
        for column in omitted
        for row in range(rows)
    ):
        return target, False
    return (
        sheet.getCellRangeByPosition(
            address.StartColumn + first,
            address.StartRow,
            address.StartColumn + last,
            address.EndRow,
        ),
        True,
    )


def _reorder_columns(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    target, auto_expanded = _reorder_table_target(sheet, params["range"])
    target, trimmed_blank_edges = _trim_reorder_target_to_requested_headers(
        sheet, target, params["headers"]
    )
    address = target.getRangeAddress()
    rows = address.EndRow - address.StartRow + 1
    columns = address.EndColumn - address.StartColumn + 1
    headers = [
        target.getCellByPosition(column, 0).getString() for column in range(columns)
    ]
    requested = params["headers"]
    if len(requested) != columns or set(requested) != set(headers):
        raise AdapterError(
            "INVALID_REQUEST",
            "headers must contain each selected table column exactly once",
            {"actual": headers, "requested": requested},
        )
    source_by_header = {header: index for index, header in enumerate(headers)}
    snapshot = [
        [target.getCellByPosition(column, row) for column in range(columns)]
        for row in range(rows)
    ]
    cached = []
    for row in range(rows):
        cached_row = []
        for header in requested:
            cell = snapshot[row][source_by_header[header]]
            cached_row.append(
                {
                    "formula": str(cell.getFormula()),
                    "kind": _cell_kind(cell),
                    "value": cell.getValue(),
                    "string": cell.getString(),
                    "style": {prop: getattr(cell, prop) for prop in STYLE_PROPERTIES},
                }
            )
        cached.append(cached_row)
    for row, cached_row in enumerate(cached):
        for column, item in enumerate(cached_row):
            cell = target.getCellByPosition(column, row)
            if item["formula"].startswith("="):
                cell.setFormula(item["formula"])
            elif item["kind"] == "number":
                cell.setValue(item["value"])
            else:
                cell.setString(item["string"])
            for prop, value in item["style"].items():
                try:
                    setattr(cell, prop, value)
                except Exception:
                    continue
    session.doc.calculateAll()
    result = {
        "sheet": params["sheet"],
        "requested_range": params["range"],
        "range": _range_a1(address),
        "auto_expanded": auto_expanded,
        "headers": requested,
        "rows": rows,
        "columns": columns,
    }
    if trimmed_blank_edges:
        result["trimmed_blank_edge_columns"] = True
    return result


def _set_rows_hidden(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    visible = not params.get("hidden", True)
    for row in params["rows"]:
        sheet.getRows().getByIndex(row - 1).IsVisible = visible
    return {"rows": params["rows"], "hidden": not visible}


def _range_has_content(cell_range: Any) -> bool:
    address = cell_range.getRangeAddress()
    rows = address.EndRow - address.StartRow + 1
    columns = address.EndColumn - address.StartColumn + 1
    return any(
        _cell_kind(cell_range.getCellByPosition(column, row)) != "blank"
        for row in range(rows)
        for column in range(columns)
    )


def _chart_ranges_have_content(sheet: Any, source_ranges: list[str]) -> bool:
    try:
        return all(
            _range_has_content(sheet.getCellRangeByName(a1)) for a1 in source_ranges
        )
    except Exception:
        return False


def _resolve_chart_source_sheet(session: CalcSession, params: dict[str, Any]) -> Any:
    requested = params.get("source_sheet")
    if requested:
        return session.sheet(requested)

    candidates = []
    for name in _sheet_names(session.doc):
        sheet = session.sheet(name)
        if _chart_ranges_have_content(sheet, params["source_ranges"]):
            candidates.append(sheet)
    if len(candidates) == 1:
        return candidates[0]

    candidate_names = [sheet.getName() for sheet in candidates]
    if candidate_names:
        message = (
            "source_sheet is required because source_ranges contain data on multiple "
            "worksheets"
        )
    else:
        message = (
            "source_sheet is required because no unique populated source was found"
        )
    raise AdapterError(
        "INVALID_REQUEST",
        message,
        {
            "source_ranges": params["source_ranges"],
            "candidate_sheets": candidate_names,
        },
    )


def _infer_chart_data_row_source(sheet: Any, source_ranges: list[str]) -> str:
    row_score = 0
    column_score = 0
    for a1 in source_ranges:
        address = sheet.getCellRangeByName(a1).getRangeAddress()
        rows = address.EndRow - address.StartRow + 1
        columns = address.EndColumn - address.StartColumn + 1
        if columns > rows:
            row_score += columns - rows
        elif rows > columns:
            column_score += rows - columns

    # A vertical table normally has a small number of series columns and many
    # observation rows; a horizontal table has the inverse shape. Ties retain
    # Calc's conventional one-series-per-column behavior.
    return "rows" if row_score > column_score else "columns"


def _chart_create(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    uno, _ = _uno_modules()
    sheet = session.sheet(params["sheet"])
    source_sheet = _resolve_chart_source_sheet(session, params)
    data_row_source = params.get("data_row_source", "auto")
    if data_row_source == "auto":
        data_row_source = _infer_chart_data_row_source(
            source_sheet, params["source_ranges"]
        )
    charts = sheet.getCharts()
    previous_chart_removed = charts.hasByName(params["name"])
    if previous_chart_removed:
        if params.get("replace", False):
            charts.removeByName(params["name"])
        else:
            raise AdapterError(
                "CONFLICT",
                f"chart already exists: {params['name']}. Select replace=true with this "
                "same name only when you intend to remove and recreate the existing "
                "chart using your new arguments; choose a different name to keep it.",
                {
                    "name": params["name"],
                    "sheet": params["sheet"],
                    "replace_requested": False,
                    "existing_chart_removed": False,
                },
                409,
            )
    rectangle = uno.createUnoStruct("com.sun.star.awt.Rectangle")
    position = params.get("position", {})
    rectangle.X = int(position.get("x", 12000))
    rectangle.Y = int(position.get("y", 1000))
    rectangle.Width = int(position.get("width", 16000))
    rectangle.Height = int(position.get("height", 9000))
    addresses = tuple(
        source_sheet.getCellRangeByName(a1).getRangeAddress()
        for a1 in params["source_ranges"]
    )
    charts.addNewByName(
        params["name"],
        rectangle,
        addresses,
        bool(params.get("column_headers", True)),
        bool(params.get("row_headers", True)),
    )
    service = {
        "column": "com.sun.star.chart.BarDiagram",
        "bar": "com.sun.star.chart.BarDiagram",
        "line": "com.sun.star.chart.LineDiagram",
    }[params["type"]]
    table_chart = None
    chart = None
    diagram = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            table_chart = charts.getByName(params["name"])
            chart = table_chart.getEmbeddedObject()
            diagram = chart.createInstance(service) if chart is not None else None
            if diagram is not None:
                break
        except Exception:
            pass
        time.sleep(0.1)
    if chart is None or diagram is None:
        charts.removeByName(params["name"])
        raise AdapterError(
            "INTERNAL_ERROR",
            "LibreOffice failed to initialize the chart diagram",
            {"name": params["name"], "service": service},
            500,
        )
    if params["type"] in {"column", "bar"}:
        diagram.Vertical = params["type"] == "bar"
    diagram.DataRowSource = uno.Enum(
        "com.sun.star.chart.ChartDataRowSource",
        str(data_row_source).upper(),
    )
    chart.setDiagram(diagram)
    # Changing series orientation can reinterpret the initial header binding.
    # Reapply the model-selected physical first-row/first-column flags afterward.
    table_chart.setHasColumnHeaders(bool(params.get("column_headers", True)))
    table_chart.setHasRowHeaders(bool(params.get("row_headers", True)))
    title = params.get("title")
    if title is not None:
        chart.HasMainTitle = True
        chart.Title.String = str(title)
    result = {
        "name": params["name"],
        "type": params["type"],
        "title": title,
        "sheet": params["sheet"],
        "source_sheet": source_sheet.getName(),
        "source_ranges": list(params["source_ranges"]),
        "data_row_source": data_row_source,
    }
    for field, getter in (
        ("column_headers", "getHasColumnHeaders"),
        ("row_headers", "getHasRowHeaders"),
    ):
        try:
            result[field] = bool(getattr(table_chart, getter)())
        except Exception as exc:
            result.setdefault("header_inspect_error", {})[field] = str(exc)
    # The native chart model resolves category labels separately from plotted
    # value series. Return that observation immediately so the model can
    # distinguish a label column from an additional numeric series before its
    # required save/read-back step.
    try:
        series_details = _chart_series_details(chart)
    except Exception as exc:
        result["data_series_inspect_error"] = str(exc)
    else:
        if series_details["data_series_count"] == 0:
            charts.removeByName(params["name"])
            raise AdapterError(
                "INVALID_REQUEST",
                "LibreOffice created no data series from source_ranges; the empty "
                "chart was removed. For column-oriented data, select category and "
                "value ranges spanning the same rows; for row-oriented data, use "
                "the same columns. Include or exclude the header row consistently "
                "and set the header flags for that selection.",
                {
                    "name": params["name"],
                    "source_ranges": list(params["source_ranges"]),
                    "data_row_source": data_row_source,
                    "empty_chart_removed": True,
                    "previous_chart_removed": previous_chart_removed,
                },
                422,
            )
        result.update(series_details)
    return result


def _object_name(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9 _-]+", "", value).strip()
    return normalized[:80] or fallback


def _chart_create_from_summary_rows(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    source_sheet = session.sheet(params["source_sheet"])
    source = source_sheet.getCellRangeByName(params["source_range"])
    source_address = source.getRangeAddress()
    used = _used_range(source_sheet)
    observed_end_row = max(source_address.EndRow, used["end_row"])
    observed = source_sheet.getCellRangeByPosition(
        source_address.StartColumn,
        source_address.StartRow,
        source_address.EndColumn,
        observed_end_row,
    )
    snapshot = _range_snapshot(observed, session.doc)
    try:
        plans = plan_summary_row_charts(
            snapshot["display_text"],
            start_column=source_address.StartColumn,
            start_row=source_address.StartRow,
            source_data_rows=source_address.EndRow - source_address.StartRow + 1,
            series=params["series"],
        )
    except SemanticTableError as exc:
        raise AdapterError("CONFLICT", str(exc)) from exc

    prefix = params.get("name_prefix", "Summary Chart")
    charts = []
    created_names: list[str] = []
    try:
        for index, (plan, spec) in enumerate(zip(plans, params["series"]), start=1):
            name = _object_name(f"{prefix} {index}", fallback=f"Summary Chart {index}")
            chart = _chart_create(
                session,
                {
                    "sheet": params["sheet"],
                    "source_sheet": params["source_sheet"],
                    "name": name,
                    "source_ranges": list(plan.source_ranges),
                    "type": spec["type"],
                    "data_row_source": "rows",
                    "column_headers": True,
                    "row_headers": True,
                    "title": spec.get("title", plan.row_label),
                    "replace": params.get("replace", False),
                    "position": {
                        "x": 12000,
                        "y": 1000 + (index - 1) * 10000,
                        "width": 16000,
                        "height": 9000,
                    },
                },
            )
            created_names.append(name)
            charts.append(
                {
                    **chart,
                    "row_label": plan.row_label,
                    "row": plan.row + 1,
                    "omitted_categories": list(spec.get("omit_categories", [])),
                }
            )
    except Exception:
        collection = session.sheet(params["sheet"]).getCharts()
        for name in created_names:
            if collection.hasByName(name):
                collection.removeByName(name)
        raise
    return {
        "sheet": params["sheet"],
        "source_sheet": params["source_sheet"],
        "source_range": params["source_range"],
        "chart_count": len(charts),
        "charts": charts,
    }


def _pivot_create(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    uno, _ = _uno_modules()
    source_sheet = session.sheet(params["source_sheet"])
    destination_sheet = session.sheet(params["destination_sheet"])
    requested_destination = params["destination"]
    resolved_destination = requested_destination
    placement = {}
    if isinstance(requested_destination, dict):
        reference = destination_sheet.getCellRangeByName(
            requested_destination["below_range"]
        ).getRangeAddress()
        resolved_destination = (
            f"{_column_label(reference.StartColumn)}"
            f"{reference.EndRow + requested_destination['blank_rows'] + 2}"
        )
        placement = {"requested_destination": dict(requested_destination)}
    destination = destination_sheet.getCellRangeByName(resolved_destination).getCellAddress()
    tables = destination_sheet.getDataPilotTables()
    if tables.hasByName(params["name"]):
        if params.get("replace", False):
            tables.removeByName(params["name"])
        else:
            raise AdapterError(
                "CONFLICT",
                f"pivot table already exists: {params['name']}",
                http_status=409,
            )
    descriptor = tables.createDataPilotDescriptor()
    descriptor.ShowFilterButton = bool(params.get("show_filter_button", False))
    descriptor.SourceRange = source_sheet.getCellRangeByName(
        params["source_range"]
    ).getRangeAddress()
    fields = descriptor.getDataPilotFields()
    orientations = {
        "row": uno.Enum("com.sun.star.sheet.DataPilotFieldOrientation", "ROW"),
        "column": uno.Enum("com.sun.star.sheet.DataPilotFieldOrientation", "COLUMN"),
        "page": uno.Enum("com.sun.star.sheet.DataPilotFieldOrientation", "PAGE"),
        "data": uno.Enum("com.sun.star.sheet.DataPilotFieldOrientation", "DATA"),
    }
    for orientation, key in (
        ("row", "row_fields"),
        ("column", "column_fields"),
        ("page", "page_fields"),
    ):
        for name in params.get(key, []):
            if not fields.hasByName(name):
                raise AdapterError("INVALID_REQUEST", f"pivot field not found: {name}")
            fields.getByName(name).Orientation = orientations[orientation]
    functions = {
        "sum": "SUM",
        "count": "COUNT",
        "average": "AVERAGE",
        "max": "MAX",
        "min": "MIN",
    }
    reference_types = {
        "none": "NONE",
        "item_difference": "ITEM_DIFFERENCE",
        "item_percentage": "ITEM_PERCENTAGE",
        "item_percentage_difference": "ITEM_PERCENTAGE_DIFFERENCE",
        "running_total": "RUNNING_TOTAL",
        "row_percentage": "ROW_PERCENTAGE",
        "column_percentage": "COLUMN_PERCENTAGE",
        "total_percentage": "TOTAL_PERCENTAGE",
        "index": "INDEX",
    }
    normalized_data_fields = [
        normalize_pivot_data_field(spec, index=index)
        for index, spec in enumerate(params.get("data_fields", []))
    ]
    for spec in normalized_data_fields:
        if not fields.hasByName(spec["name"]):
            raise AdapterError("INVALID_REQUEST", "pivot data field is invalid", spec)
        field = fields.getByName(spec["name"])
        function = str(spec.get("function", "sum")).lower()
        if function not in functions:
            raise AdapterError(
                "INVALID_REQUEST", f"unsupported pivot function: {function}"
            )
        field.Orientation = orientations["data"]
        field.Function = uno.Enum(
            "com.sun.star.sheet.GeneralFunction", functions[function]
        )
        show_data_as = str(spec.get("show_data_as", "none")).lower()
        if show_data_as not in reference_types:
            raise AdapterError(
                "INVALID_REQUEST", f"unsupported pivot show_data_as: {show_data_as}"
            )
        if show_data_as != "none":
            reference = uno.createUnoStruct(
                "com.sun.star.sheet.DataPilotFieldReference"
            )
            reference.ReferenceType = uno.getConstantByName(
                "com.sun.star.sheet.DataPilotFieldReferenceType."
                + reference_types[show_data_as]
            )
            reference.ReferenceField = str(spec.get("reference_field", ""))
            reference.ReferenceItemName = str(spec.get("reference_item", ""))
            field.Reference = reference
    tables.insertNewByName(params["name"], destination, descriptor)
    output = tables.getByName(params["name"]).getOutputRange()
    result = {
        "name": params["name"],
        "source_range": params["source_range"],
        "destination": resolved_destination,
        **placement,
        "destination_sheet": params["destination_sheet"],
        "output_range": _range_a1(output),
        "output_last_row": int(output.EndRow) + 1,
        "output_row_count": int(output.EndRow - output.StartRow) + 1,
    }
    try:
        end_column = min(output.EndColumn, output.StartColumn + 15)
        end_row = min(output.EndRow, output.StartRow + 31)
        preview = destination_sheet.getCellRangeByPosition(
            output.StartColumn, output.StartRow, end_column, end_row
        )
        result["readback"] = {
            "sheet": params["destination_sheet"],
            "range": _range_a1(preview.getRangeAddress()),
            "display_text": _display_text_matrix(preview),
            "truncated": end_column < output.EndColumn or end_row < output.EndRow,
        }
    except Exception as exc:
        # The native pivot already exists; a failed read must not invite a duplicate insert.
        result["readback_error"] = str(exc)
    return result


def _stacked_pivot_anchor(
    destination_sheet: Any, params: dict[str, Any]
) -> tuple[int, int, str]:
    if "destination" in params:
        requested = params["destination"]
        anchor = destination_sheet.getCellRangeByName(requested).getCellAddress()
        return anchor.Column, anchor.Row, requested

    column_label = str(params.get("destination_column", "A")).upper()
    column = (
        destination_sheet.getCellRangeByName(f"{column_label}1").getCellAddress().Column
    )
    used = _used_range(destination_sheet)
    used_cells = destination_sheet.getCellRangeByPosition(
        used["start_column"],
        used["start_row"],
        used["end_column"],
        used["end_row"],
    )
    current_row = next_content_row(
        used_cells.getDataArray(),
        used_cells.getFormulaArray(),
        start_row=used["start_row"],
    )
    return column, current_row, f"{column_label}{current_row + 1}"


def _stacked_pivot_outputs(tables: Any) -> list[dict[str, int]]:
    outputs = []
    for table_name in tables.getElementNames():
        output = tables.getByName(table_name).getOutputRange()
        outputs.append(
            {
                "start_column": output.StartColumn,
                "start_row": output.StartRow,
                "end_column": output.EndColumn,
                "end_row": output.EndRow,
            }
        )
    return outputs


def _assert_stacked_pivot_anchor_available(
    destination_sheet: Any,
    params: dict[str, Any],
    *,
    column: int,
    row: int,
    existing_outputs: list[dict[str, int]],
) -> None:
    if "destination" not in params:
        return
    if any(
        output["start_column"] <= column <= output["end_column"]
        and output["start_row"] <= row <= output["end_row"]
        for output in existing_outputs
    ):
        return

    target = destination_sheet.getCellRangeByName(params["destination"])
    anchor = target.getCellByPosition(0, 0)
    anchor_kind = _cell_kind(anchor)
    merged = bool(getattr(target, "IsMerged", False))
    if anchor_kind == "blank" and not merged:
        return
    raise AdapterError(
        "CONFLICT",
        (
            "explicit stacked-pivot destination overlaps live worksheet content; "
            "choose another destination or placement=below_existing_content"
        ),
        {
            "destination_sheet": params["destination_sheet"],
            "destination": params["destination"],
            "anchor_kind": anchor_kind,
            "merged": merged,
        },
        409,
    )


def _pivot_create_stacked(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    try:
        resolved_source_sheet, resolved_source_range = resolve_sheet_range_reference(
            params["source_sheet"], params["source_range"]
        )
    except SemanticTableError as exc:
        raise AdapterError("INVALID_REQUEST", str(exc)) from exc
    source_sheet = session.sheet(resolved_source_sheet)
    source, _snapshot = _expanded_contiguous_source(
        session, source_sheet, resolved_source_range
    )
    effective_source_range = _range_a1(source.getRangeAddress())
    destination_sheet = session.sheet(params["destination_sheet"])
    tables = destination_sheet.getDataPilotTables()
    current_column, current_row, requested_destination = _stacked_pivot_anchor(
        destination_sheet, params
    )
    existing_outputs = _stacked_pivot_outputs(tables)
    gap_rows = params.get("gap_rows", 1)
    if not params.get("replace", False):
        try:
            current_row = stacked_destination_row(
                current_row,
                current_column,
                existing_outputs,
                gap_rows=gap_rows,
            )
        except SemanticTableError as exc:
            raise AdapterError("CONFLICT", str(exc)) from exc
    name_prefix = params.get("name_prefix", "Distribution")
    created_names: list[str] = []
    results = []
    first_destination: str | None = None
    try:
        for index, field in enumerate(params["fields"], start=1):
            destination = f"{_column_label(current_column)}{current_row + 1}"
            if first_destination is None:
                first_destination = destination
            name = _object_name(
                f"{name_prefix} {index} {field}",
                fallback=f"Distribution {index}",
            )
            pivot_params = {
                "source_sheet": resolved_source_sheet,
                "source_range": effective_source_range,
                "destination_sheet": params["destination_sheet"],
                "destination": destination,
                "name": name,
                "row_fields": [field],
                "column_fields": [],
                "page_fields": [],
                "data_fields": [
                    {
                        "field": field,
                        "aggregation": "count",
                        "show_data_as": "total_percentage",
                    }
                ],
                "replace": params.get("replace", False),
                "show_filter_button": params.get("show_filter_button", False),
            }
            _assert_stacked_pivot_anchor_available(
                destination_sheet,
                pivot_params,
                column=current_column,
                row=current_row,
                existing_outputs=_stacked_pivot_outputs(tables),
            )
            result = _pivot_create(session, pivot_params)
            created_names.append(name)
            output_address = tables.getByName(name).getOutputRange()
            output_range = _range_a1(output_address)
            results.append({**result, "field": field, "output_range": output_range})
            current_row = output_address.EndRow + gap_rows + 1
    except Exception:
        for name in created_names:
            if tables.hasByName(name):
                tables.removeByName(name)
        raise
    return {
        "requested_source_sheet": params["source_sheet"],
        "requested_source_range": params["source_range"],
        "source_sheet": resolved_source_sheet,
        "source_range": effective_source_range,
        "destination_sheet": params["destination_sheet"],
        "requested_destination": params.get("destination"),
        "requested_placement": params.get("placement"),
        "requested_destination_column": params.get("destination_column", "A")
        if "placement" in params
        else None,
        "resolved_destination": requested_destination,
        "destination": first_destination or requested_destination,
        "gap_rows": gap_rows,
        "pivot_count": len(results),
        "pivots": results,
    }


def _pivot_create_stacked_aggregate(
    session: CalcSession, params: dict[str, Any]
) -> dict[str, Any]:
    try:
        resolved_source_sheet, resolved_source_range = resolve_sheet_range_reference(
            params["source_sheet"], params["source_range"]
        )
    except SemanticTableError as exc:
        raise AdapterError("INVALID_REQUEST", str(exc)) from exc
    source_sheet = session.sheet(resolved_source_sheet)
    source, snapshot = _expanded_contiguous_source(
        session, source_sheet, resolved_source_range
    )
    try:
        resolved_fields = resolve_stacked_aggregate_fields(
            snapshot["display_text"],
            snapshot["kinds"],
            group_selectors=params["group_fields"],
            value_selector=params["value_field"],
            aggregation=params["aggregation"],
        )
    except SemanticTableError as exc:
        raise AdapterError("CONFLICT", str(exc)) from exc

    effective_source_range = _range_a1(source.getRangeAddress())
    destination_sheet = session.sheet(params["destination_sheet"])
    tables = destination_sheet.getDataPilotTables()
    current_column, current_row, requested_destination = _stacked_pivot_anchor(
        destination_sheet, params
    )
    existing_outputs = _stacked_pivot_outputs(tables)
    gap_rows = params.get("gap_rows", 1)
    if not params.get("replace", False):
        try:
            current_row = stacked_destination_row(
                current_row,
                current_column,
                existing_outputs,
                gap_rows=gap_rows,
            )
        except SemanticTableError as exc:
            raise AdapterError("CONFLICT", str(exc)) from exc

    name_prefix = params.get("name_prefix", "Aggregate")
    created_names: list[str] = []
    results = []
    first_destination: str | None = None
    try:
        for index, group_field in enumerate(resolved_fields.group_fields, start=1):
            destination = f"{_column_label(current_column)}{current_row + 1}"
            if first_destination is None:
                first_destination = destination
            name = _object_name(
                f"{name_prefix} {index} {group_field}",
                fallback=f"Aggregate {index}",
            )
            pivot_params = {
                "source_sheet": resolved_source_sheet,
                "source_range": effective_source_range,
                "destination_sheet": params["destination_sheet"],
                "destination": destination,
                "name": name,
                "row_fields": [group_field],
                "column_fields": [],
                "page_fields": [],
                "data_fields": [
                    {
                        "field": resolved_fields.value_field,
                        "aggregation": resolved_fields.aggregation,
                        "show_data_as": "none",
                    }
                ],
                "replace": params.get("replace", False),
                "show_filter_button": params.get("show_filter_button", False),
            }
            _assert_stacked_pivot_anchor_available(
                destination_sheet,
                pivot_params,
                column=current_column,
                row=current_row,
                existing_outputs=_stacked_pivot_outputs(tables),
            )
            result = _pivot_create(session, pivot_params)
            created_names.append(name)
            output_address = tables.getByName(name).getOutputRange()
            output_range = _range_a1(output_address)
            results.append(
                {
                    **result,
                    "group_field": group_field,
                    "value_field": resolved_fields.value_field,
                    "aggregation": resolved_fields.aggregation,
                    "output_range": output_range,
                }
            )
            current_row = output_address.EndRow + gap_rows + 1
    except Exception:
        for name in created_names:
            if tables.hasByName(name):
                tables.removeByName(name)
        raise

    return {
        "requested_source_sheet": params["source_sheet"],
        "requested_source_range": params["source_range"],
        "source_sheet": resolved_source_sheet,
        "source_range": effective_source_range,
        "destination_sheet": params["destination_sheet"],
        "requested_destination": params.get("destination"),
        "requested_placement": params.get("placement"),
        "requested_destination_column": params.get("destination_column", "A")
        if "placement" in params
        else None,
        "resolved_destination": requested_destination,
        "destination": first_destination or requested_destination,
        "requested_group_fields": list(params["group_fields"]),
        "group_fields": list(resolved_fields.group_fields),
        "requested_value_field": params["value_field"],
        "value_field": resolved_fields.value_field,
        "aggregation": resolved_fields.aggregation,
        "gap_rows": gap_rows,
        "pivot_count": len(results),
        "pivots": results,
    }


def _set_zoom(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    controller = session.activate_sheet(params["sheet"])
    previous_zoom = int(controller.ZoomValue)
    controller.ZoomValue = params["zoom"]
    actual_zoom = int(controller.ZoomValue)
    return {"sheet": params["sheet"], "previous_zoom": previous_zoom,
            "zoom": actual_zoom, "requested_zoom": params["zoom"],
            "direction": "out" if actual_zoom < previous_zoom else (
                "in" if actual_zoom > previous_zoom else "unchanged")}



def _freeze(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    controller = session.activate_sheet(params["sheet"])
    columns = params.get("columns", 0)
    rows = params.get("rows", 0)
    controller.freezeAtPosition(0, 0)
    controller.setFirstVisibleColumn(0)
    controller.setFirstVisibleRow(0)
    controller.select(session.sheet(params["sheet"]).getCellByPosition(columns, rows))
    controller.freezeAtPosition(columns, rows)
    return {"sheet": params["sheet"], "columns": columns, "rows": rows}


def _freeze_range(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    target = session.sheet(params["sheet"]).getCellRangeByName(params["range"])
    address = target.getRangeAddress()
    if address.StartColumn != 0 or address.StartRow != 0:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.range must start at A1 so its bottom-right cell unambiguously defines the frozen panes",
        )
    result = _freeze(
        session,
        {
            "sheet": params["sheet"],
            "columns": address.EndColumn + 1,
            "rows": address.EndRow + 1,
        },
    )
    return {**result, "range": _range_a1(address)}


def _fit_pages(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    sheet = session.sheet(params["sheet"])
    families = session.doc.getStyleFamilies()
    page_styles = families.getByName("PageStyles")
    style = page_styles.getByName(sheet.PageStyle)
    style.ScaleToPagesX = params.get("pages_wide", 1)
    style.ScaleToPagesY = params.get("pages_tall", 1)
    if params.get("print_range"):
        sheet.setPrintAreas(
            (sheet.getCellRangeByName(params["print_range"]).getRangeAddress(),)
        )
    return {
        "sheet": params["sheet"],
        "pages_wide": int(style.ScaleToPagesX),
        "pages_tall": int(style.ScaleToPagesY),
    }


def _export(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    doc = session.doc
    doc.calculateAll()
    format_name = params["format"]
    url = _file_url(params["url"])
    path = _url_path(url)
    if path is None or not path.name:
        raise AdapterError(
            "INVALID_REQUEST",
            "export URL must identify a file, not a directory",
            {"url": params["url"]},
        )
    if path:
        path.unlink(missing_ok=True)
        if format_name == "csv":
            for candidate in path.parent.glob(f"{path.stem}-*{path.suffix}"):
                candidate.unlink(missing_ok=True)
    properties = []
    if format_name == "pdf":
        properties.append(_property("FilterName", "calc_pdf_Export"))
    else:
        sheet_name = (
            params.get("sheet") or doc.getCurrentController().getActiveSheet().getName()
        )
        session.activate_sheet(sheet_name)
        properties.append(_property("FilterName", "Text - txt - csv (StarCalc)"))
        properties.append(
            _property(
                "FilterOptions",
                params.get(
                    "filter_options",
                    "44,34,UTF-8,,,,false,true,true,false,false,1",
                ),
            )
        )
    try:
        doc.storeToURL(url, tuple(properties))
    except Exception as exc:
        raise AdapterError(
            "EXPORT_FAILED", f"failed to export {format_name}", str(exc), 500
        ) from exc
    if format_name == "csv" and path and not path.is_file():
        selected = (
            params.get("sheet") or doc.getCurrentController().getActiveSheet().getName()
        )
        generated = path.with_name(f"{path.stem}-{selected}{path.suffix}")
        if generated.is_file():
            generated.replace(path)
            for candidate in path.parent.glob(f"{path.stem}-*{path.suffix}"):
                if candidate != path:
                    candidate.unlink(missing_ok=True)
    if not path or not path.is_file() or path.stat().st_size == 0:
        raise AdapterError(
            "EXPORT_FAILED", "exported file is missing or empty", {"url": url}, 500
        )
    return {
        "format": format_name,
        "url": url,
        "path": str(path),
        "size": path.stat().st_size,
    }


_CONVERSION_FILTERS = {
    ".csv": "Text - txt - csv (StarCalc)",
    ".ods": "calc8",
    ".xlsx": "Calc MS Excel 2007 XML",
}
_DEFAULT_CSV_FILTER_OPTIONS = "44,34,UTF-8,,,,false,true,true,false,false,1"


def _close_document(doc: Any) -> None:
    try:
        doc.close(True)
    except Exception:
        try:
            doc.dispose()
        except Exception:
            pass


def _convert_file(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    input_url = _file_url(params["input_path"])
    output_url = _file_url(params["output_path"])
    input_path = _url_path(input_url)
    output_path = _url_path(output_url)
    if input_path is None or output_path is None:
        raise AdapterError(
            "INVALID_REQUEST", "workbook.convert_file supports local files only"
        )
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path:
        raise AdapterError(
            "INVALID_REQUEST",
            "input_path and output_path must identify different files",
        )
    if not input_path.is_file() or input_path.stat().st_size == 0:
        raise AdapterError(
            "FILE_NOT_FOUND",
            "input spreadsheet is missing or empty",
            {"input_path": str(input_path)},
            404,
        )
    input_suffix = input_path.suffix.lower()
    output_suffix = output_path.suffix.lower()
    if (
        input_suffix not in _CONVERSION_FILTERS
        or output_suffix not in _CONVERSION_FILTERS
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "supported spreadsheet formats are CSV, ODS, and XLSX",
            {"input_format": input_suffix, "output_format": output_suffix},
        )

    load_properties = [_property("Hidden", True)]
    if input_suffix == ".csv":
        load_properties.extend(
            [
                _property("FilterName", _CONVERSION_FILTERS[input_suffix]),
                _property("FilterOptions", _DEFAULT_CSV_FILTER_OPTIONS),
            ]
        )
    doc = None
    try:
        doc = session.desktop.loadComponentFromURL(
            input_url, "_blank", 0, tuple(load_properties)
        )
        if doc is None or not doc.supportsService(
            "com.sun.star.sheet.SpreadsheetDocument"
        ):
            raise AdapterError(
                "DOCUMENT_OPEN_FAILED",
                "input file did not open as a Calc spreadsheet",
                {"input_path": str(input_path)},
                422,
            )
        doc.calculateAll()
        sheet_count = int(doc.getSheets().getCount())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
        store_properties = [_property("FilterName", _CONVERSION_FILTERS[output_suffix])]
        if output_suffix == ".csv":
            store_properties.append(
                _property("FilterOptions", _DEFAULT_CSV_FILTER_OPTIONS)
            )
        doc.storeToURL(output_url, tuple(store_properties))
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "CONVERSION_FAILED",
            "LibreOffice failed to convert the spreadsheet",
            {
                "input_path": str(input_path),
                "output_path": str(output_path),
                "error": str(exc),
            },
            500,
        ) from exc
    finally:
        if doc is not None:
            _close_document(doc)

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise AdapterError(
            "CONVERSION_FAILED",
            "converted spreadsheet is missing or empty",
            {"output_path": str(output_path)},
            500,
        )
    if output_suffix in {".ods", ".xlsx"} and not zipfile.is_zipfile(output_path):
        raise AdapterError(
            "CONVERSION_FAILED",
            "converted spreadsheet package is invalid",
            {"output_path": str(output_path)},
            500,
        )
    return {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "input_format": input_suffix.removeprefix("."),
        "output_format": output_suffix.removeprefix("."),
        "size": output_path.stat().st_size,
        "sheet_count": sheet_count,
        "verified": True,
    }


def _display_text_matrix(cell_range: Any) -> list[list[str]]:
    address = cell_range.getRangeAddress()
    return [
        [
            str(cell_range.getCellByPosition(column, row).getString())
            for column in range(address.EndColumn - address.StartColumn + 1)
        ]
        for row in range(address.EndRow - address.StartRow + 1)
    ]


def _read_file(session: CalcSession, params: dict[str, Any]) -> dict[str, Any]:
    input_url = _file_url(params["path"])
    input_path = _url_path(input_url)
    if input_path is None:
        raise AdapterError(
            "INVALID_REQUEST", "workbook.read_file supports local files only"
        )
    input_path = input_path.resolve()
    if not input_path.is_file() or input_path.stat().st_size == 0:
        details: dict[str, Any] = {"path": str(input_path)}
        try:
            documents = session._documents()
            details["open_documents"] = [
                session._identity(doc) for doc in documents[:8]
            ]
            details["open_documents_omitted"] = max(0, len(documents) - 8)
        except Exception as exc:
            details["open_documents_error"] = f"{type(exc).__name__}: {exc}"[:500]
        raise AdapterError(
            "FILE_NOT_FOUND",
            "input spreadsheet is missing or empty. open_documents lists live open "
            "Calc workbooks, not confirmed substitutes. Choose the intended file from "
            "observed state; workbook.inspect needs no path when only one workbook is open. "
            "No alternative file was read.",
            details,
            404,
        )
    suffix = input_path.suffix.lower()
    if suffix not in _CONVERSION_FILTERS:
        raise AdapterError(
            "INVALID_REQUEST",
            "supported spreadsheet formats are CSV, ODS, and XLSX",
            {"format": suffix},
        )

    load_properties = [_property("Hidden", True), _property("ReadOnly", True)]
    if suffix == ".csv":
        load_properties.extend(
            [
                _property("FilterName", _CONVERSION_FILTERS[suffix]),
                _property("FilterOptions", _DEFAULT_CSV_FILTER_OPTIONS),
            ]
        )
    document = None
    try:
        document = session.desktop.loadComponentFromURL(
            input_url, "_blank", 0, tuple(load_properties)
        )
        if document is None or not document.supportsService(
            "com.sun.star.sheet.SpreadsheetDocument"
        ):
            raise AdapterError(
                "DOCUMENT_OPEN_FAILED",
                "input file did not open as a Calc spreadsheet",
                {"path": str(input_path)},
                422,
            )
        document.calculateAll()
        sheets = document.getSheets()
        sheet_names = list(sheets.getElementNames())
        requested_sheet = params.get("sheet")
        if requested_sheet is not None:
            if not sheets.hasByName(requested_sheet):
                raise AdapterError(
                    "SHEET_NOT_FOUND",
                    f"sheet not found: {requested_sheet}",
                    {"sheet_names": sheet_names},
                    404,
                )
            selected_names = [requested_sheet]
        else:
            selected_names = sheet_names[: params.get("max_sheets", 8)]

        max_rows = params.get("max_rows", 200)
        max_columns = params.get("max_columns", 64)
        requested_range = params.get("range")
        previews = []
        any_truncated = len(selected_names) < len(sheet_names)
        for sheet_name in selected_names:
            sheet = sheets.getByName(sheet_name)
            used_cursor = sheet.createCursor()
            used_cursor.gotoEndOfUsedArea(True)
            used_address = used_cursor.getRangeAddress()
            source = (
                sheet.getCellRangeByName(requested_range)
                if requested_range is not None
                else sheet.getCellRangeByPosition(
                    params.get("start_column", used_address.StartColumn + 1) - 1,
                    params.get("start_row", used_address.StartRow + 1) - 1,
                    used_address.EndColumn,
                    used_address.EndRow,
                )
            )
            source_address = source.getRangeAddress()
            source_rows = source_address.EndRow - source_address.StartRow + 1
            source_columns = source_address.EndColumn - source_address.StartColumn + 1
            end_row = min(source_address.EndRow, source_address.StartRow + max_rows - 1)
            end_column = min(
                source_address.EndColumn,
                source_address.StartColumn + max_columns - 1,
            )
            returned = sheet.getCellRangeByPosition(
                source_address.StartColumn,
                source_address.StartRow,
                end_column,
                end_row,
            )
            truncated = (
                end_row < source_address.EndRow or end_column < source_address.EndColumn
            )
            any_truncated = any_truncated or truncated
            previews.append(
                {
                    "name": sheet_name,
                    "used_range": _range_a1(used_address),
                    "source_range": _range_a1(source_address),
                    "returned_range": _range_a1(returned.getRangeAddress()),
                    "source_rows": source_rows,
                    "source_columns": source_columns,
                    "returned_rows": end_row - source_address.StartRow + 1,
                    "returned_columns": end_column - source_address.StartColumn + 1,
                    "truncated": truncated,
                    "display_text": _display_text_matrix(returned),
                }
            )
        return {
            "path": str(input_path),
            "url": input_url,
            "format": suffix.removeprefix("."),
            "read_mode": "saved_file_snapshot",
            "activates_document": False,
            "sheet_count": len(sheet_names),
            "returned_sheet_count": len(previews),
            "sheets_truncated": len(previews) < len(sheet_names),
            "truncated": any_truncated,
            "sheets": previews,
        }
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "DOCUMENT_READ_FAILED",
            "failed to read spreadsheet display text",
            {"path": str(input_path), "error": str(exc)},
            500,
        ) from exc
    finally:
        if document is not None:
            _close_document(document)


ACTIONS = {
    "workbook.inspect": _inspect,
    "workbook.read_file": _read_file,
    "workbook.create_new": _create_new,
    "workbook.save": _save,
    "workbook.export": _export,
    "workbook.convert_file": _convert_file,
    "sheet.create": _create_sheet,
    "sheet.rename": _rename_sheet,
    "sheet.copy": _copy_sheet,
    "sheet.move": _move_sheet,
    "range.read": _read,
    "range.write": _write,
    "cells.set_formulas": _set_formulas,
    "range.copy": _copy_range,
    "range.fill_down": _fill_down,
    "range.text_transform": _text_transform,
    "range.merge": _merge,
    "range.format": _format_range,
    "range.set_scaled_display": _set_scaled_display,
    "range.set_decimal_separator": _set_decimal_separator,
    "range.set_validation": _set_validation,
    "table.sort": _sort_table,
    "table.reorder_columns": _reorder_columns,
    "rows.set_hidden": _set_rows_hidden,
    "chart.create": _chart_create,
    "pivot.create": _pivot_create,
    "view.set_zoom": _set_zoom,
    "view.freeze_panes": _freeze,
    "view.freeze_range": _freeze_range,
    "page.fit_to_pages": _fit_pages,
}


def _equivalent(actual: Any, expected: Any, tolerance: float) -> bool:
    if (
        isinstance(actual, (int, float))
        and not isinstance(actual, bool)
        and isinstance(expected, (int, float))
        and not isinstance(expected, bool)
    ):
        return abs(float(actual) - float(expected)) <= tolerance
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _equivalent(a, e, tolerance) for a, e in zip(actual, expected)
        )
    if isinstance(actual, dict) and isinstance(expected, dict):
        return all(
            key in actual and _equivalent(actual[key], value, tolerance)
            for key, value in expected.items()
        )
    return actual == expected


def _verification_observed(session: CalcSession, check: dict[str, Any]) -> Any:
    check_type = check["type"]
    if check_type == "document_identity":
        return session._identity(session.doc)
    if check_type == "sheet_names":
        return _sheet_names(session.doc)
    if check_type.startswith("range_"):
        snapshot = _read(session, {"sheet": check["sheet"], "range": check["range"]})
        key = {
            "range_values": "values",
            "range_formulas": "formulas",
            "range_display_text": "display_text",
            "range_styles": "styles",
        }[check_type]
        return snapshot[key]
    if check_type == "merged_ranges":
        return {
            a1: bool(session.sheet(check["sheet"]).getCellRangeByName(a1).IsMerged)
            for a1 in check.get("ranges", [])
        }
    if check_type == "row_hidden":
        sheet = session.sheet(check["sheet"])
        return {
            str(row): not bool(sheet.getRows().getByIndex(row - 1).IsVisible)
            for row in check.get("rows", [])
        }
    if check_type == "data_validation":
        validation = (
            session.sheet(check["sheet"]).getCellRangeByName(check["range"]).Validation
        )
        return {
            "type": _enum_name(validation.Type),
            "formula1": str(validation.Formula1),
            "show_list": int(validation.ShowList),
        }
    if check_type == "chart_properties":
        charts = session.sheet(check["sheet"]).getCharts()
        result = []
        for name in charts.getElementNames():
            chart = charts.getByName(name).getEmbeddedObject()
            result.append(
                {
                    "name": name,
                    "title": chart.Title.String if chart.HasMainTitle else "",
                    "diagram": str(chart.getDiagram().getImplementationName()),
                }
            )
        return result
    if check_type == "pivot_properties":
        tables = session.sheet(check["sheet"]).getDataPilotTables()
        return list(tables.getElementNames())
    if check_type == "zoom":
        if check.get("persisted"):
            return _saved_sheet_view(session.doc, check["sheet"])["zoom"]
        return int(session.activate_sheet(check["sheet"]).ZoomValue)
    if check_type == "freeze_panes":
        if check.get("persisted"):
            view = _saved_sheet_view(session.doc, check["sheet"])
            return {key: view[key] for key in ("columns", "rows", "frozen")}
        controller = session.activate_sheet(check["sheet"])
        return {
            "columns": int(controller.getSplitColumn()),
            "rows": int(controller.getSplitRow()),
            "frozen": bool(controller.hasFrozenPanes()),
        }
    if check_type in {"export_file", "file_reopen"}:
        path = Path(check["path"]).expanduser()
        if check_type == "file_reopen" and path.suffix.lower() == ".xlsx":
            return _reopen_xlsx(path)
        return {
            "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else 0,
        }
    raise AdapterError("UNSUPPORTED_OPERATION", f"unsupported verifier: {check_type}")


def _verify(session: CalcSession, checks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    results = []
    all_passed = True
    observed_state = {}
    expected_state = {}
    for index, check in enumerate(checks):
        observed = _verification_observed(session, check)
        expected = check.get("expected")
        passed = expected is None or _equivalent(
            observed, expected, float(check.get("tolerance", 1e-6))
        )
        all_passed = all_passed and passed
        results.append({"index": index, "type": check["type"], "passed": passed})
        observed_state[str(index)] = observed
        expected_state[str(index)] = expected
    return {
        "passed": all_passed,
        "checks": results,
        "observed_state": observed_state,
        "expected_state": expected_state,
        "error_code": None if all_passed else "VERIFICATION_FAILED",
        "details": None if all_passed else "one or more state checks did not match",
    }


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action not in ACTIONS:
        raise AdapterError("UNSUPPORTED_OPERATION", f"unsupported action: {action}")
    if action == "range.text_transform":
        validate_action_params(action, payload.get("params") or {})
    session = CalcSession(
        payload.get("document") or {},
        allow_no_document=action
        in {"workbook.convert_file", "workbook.create_new", "workbook.read_file"},
    )
    started = time.monotonic()
    result = ACTIONS[action](session, payload.get("params") or {})
    verification = _verify(session, payload.get("verify") or [])
    return {
        "result": result,
        "verification": verification,
        "logs": [
            {
                "level": "info",
                "message": f"{action} completed in {round((time.monotonic() - started) * 1000)} ms",
            }
        ],
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        print(
            json.dumps(execute(payload), ensure_ascii=True, separators=(",", ":")),
            flush=True,
        )
        os._exit(0)
    except AdapterError as error:
        print(
            json.dumps(
                {"error": {**error_payload(error), "http_status": error.http_status}},
                ensure_ascii=True,
            ),
            flush=True,
        )
        os._exit(1)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": str(exc),
                        "details": traceback.format_exc()[-8000:],
                        "http_status": 500,
                    }
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        os._exit(1)


if __name__ == "__main__":
    main()
