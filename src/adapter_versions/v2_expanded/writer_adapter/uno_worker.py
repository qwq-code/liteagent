from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import traceback
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .errors import AdapterError, error_payload
from .image_extract import extract_document_images
from .native_references import (
    _explicit_range,
    apply_paragraph_numbering,
    create_bookmark,
    insert_cross_reference,
    paragraph_numbering_state,
)
from .pdf_export import preserve_docx_soft_wrap_spaces
from .schema import TAB_STOP_UNITS, parse_rgb_color
from .text_format import set_text_format
from .text_search import find_text


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


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", None)
    return str(raw if raw is not None else value).rsplit(".", 1)[-1].lower()


def _paragraphs(text: Any) -> list[Any]:
    result = []
    enumeration = text.createEnumeration()
    while enumeration.hasMoreElements():
        item = enumeration.nextElement()
        try:
            if item.supportsService("com.sun.star.text.Paragraph"):
                result.append(item)
        except Exception:
            continue
    return result


def _tables(doc: Any) -> list[Any]:
    collection = doc.getTextTables()
    return [collection.getByName(name) for name in collection.getElementNames()]


def _named_table(doc: Any, name: str) -> Any:
    collection = doc.getTextTables()
    if not collection.hasByName(name):
        raise AdapterError(
            "TABLE_NOT_FOUND", f"table does not exist: {name}", http_status=404
        )
    return collection.getByName(name)


def _cell_names(table: Any) -> list[str]:
    names = list(table.getCellNames())

    def key(name: str) -> tuple[int, int]:
        match = re.fullmatch(r"([A-Z]+)(\d+)", name)
        if not match:
            return (10**9, 10**9)
        column = 0
        for character in match.group(1):
            column = column * 26 + ord(character) - 64
        return (int(match.group(2)), column)

    return sorted(names, key=key)


def _all_text_objects(doc: Any) -> Iterable[Any]:
    yield doc.Text
    for table in _tables(doc):
        for name in _cell_names(table):
            yield table.getCellByName(name).Text


def _all_paragraphs(doc: Any) -> Iterable[Any]:
    for text in _all_text_objects(doc):
        yield from _paragraphs(text)


def _select_paragraph(paragraph: Any) -> Any:
    text = paragraph.getText()
    cursor = text.createTextCursorByRange(paragraph.getStart())
    cursor.gotoRange(paragraph.getEnd(), True)
    return cursor


def _whole_text_cursor(text: Any) -> Any:
    cursor = text.createTextCursorByRange(text.getStart())
    cursor.gotoRange(text.getEnd(), True)
    return cursor


def _font_summary(doc: Any) -> dict[str, Any]:
    properties = {
        "western": "CharFontName",
        "asian": "CharFontNameAsian",
        "complex": "CharFontNameComplex",
    }
    summaries = {
        script: {"names": set(), "mixed_text_objects": 0, "unknown_text_objects": 0}
        for script in properties
    }
    count = 0
    for text in _all_text_objects(doc):
        count += 1
        try:
            cursor = _whole_text_cursor(text)
        except Exception:
            cursor = None
        for script, name in properties.items():
            summary = summaries[script]
            try:
                state = _enum_value(cursor.getPropertyState(name))
                if state == "ambiguous_value":
                    summary["mixed_text_objects"] += 1
                    continue
                if state in {"direct_value", "default_value"}:
                    value = cursor.getPropertyValue(name)
                    if isinstance(value, str) and value.strip():
                        summary["names"].add(value)
                        continue
            except Exception:
                pass
            summary["unknown_text_objects"] += 1
    return {
        "scope": "body_and_table_cells",
        "text_object_count": count,
        **{
            script: summary | {"names": sorted(summary["names"])}
            for script, summary in summaries.items()
        },
    }


def _line_spacing_value(paragraph: Any) -> float:
    spacing = paragraph.ParaLineSpacing
    if int(spacing.Mode) == 0:
        return round(float(spacing.Height) / 100.0, 3)
    return float(spacing.Height)


def _set_line_spacing(paragraph: Any, value: float) -> None:
    uno, _ = _uno_modules()
    spacing = uno.createUnoStruct("com.sun.star.style.LineSpacing")
    spacing.Mode = 0
    spacing.Height = int(round(value * 100))
    paragraph.ParaLineSpacing = spacing


def _paragraph_alignment_value(paragraph: Any) -> str:
    alignment = getattr(paragraph, "ParaAdjust", None)
    try:
        numeric = int(alignment)
    except (TypeError, ValueError):
        numeric = -1
    return {0: "left", 1: "right", 2: "justify", 3: "center"}.get(
        numeric, _enum_value(alignment)
    )


def _paragraph_font_size_value(paragraph: Any) -> float | None:
    for attribute in ("CharHeight", "CharHeightAsian", "CharHeightComplex"):
        value = getattr(paragraph, attribute, None)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        ):
            return round(float(value), 3)
    return None


def _paragraph_strikethrough_value(paragraph: Any) -> bool | str | None:
    try:
        cursor = _select_paragraph(paragraph)
        state = _enum_value(cursor.getPropertyState("CharStrikeout"))
        if state == "ambiguous_value":
            return "mixed"
        if state not in {"direct_value", "default_value"}:
            return None
        value = cursor.CharStrikeout
        if isinstance(value, int) and not isinstance(value, bool):
            # FontStrikeout.DONTKNOW (3) is not evidence of enabled formatting.
            if value == 0:
                return False
            if value in {1, 2, 4, 5, 6}:
                return True
    except Exception:
        # Unavailable formatting must not hide otherwise readable paragraph text.
        pass
    return None


def _paragraph_detail(
    paragraph: Any, index: int, nonempty_ordinal: int | None
) -> dict[str, Any]:
    text = str(paragraph.String)
    tab_stops = []
    for tab_stop in getattr(paragraph, "ParaTabStops", ()):
        decimal_character = getattr(tab_stop, "DecimalChar", ".")
        fill_character = getattr(tab_stop, "FillChar", " ")
        tab_stops.append(
            {
                "position": {
                    "value": int(getattr(tab_stop, "Position", 0)) / 100,
                    "unit": "mm",
                },
                "alignment": _enum_value(getattr(tab_stop, "Alignment", "")),
                "decimal_character": str(
                    getattr(decimal_character, "value", decimal_character)
                ),
                "fill_character": str(getattr(fill_character, "value", fill_character)),
            }
        )
    return {
        "index": index,
        "nonempty_ordinal": nonempty_ordinal,
        "text": text[:500],
        "text_length": len(text),
        "line_spacing": _line_spacing_value(paragraph),
        "alignment": _paragraph_alignment_value(paragraph),
        "font_size": _paragraph_font_size_value(paragraph),
        "strikethrough": _paragraph_strikethrough_value(paragraph),
        "has_tab_character": "\t" in text,
        "tab_character_offsets": [
            offset for offset, character in enumerate(text) if character == "\t"
        ],
        "literal_tab_escape_count": text.count("\\t"),
        "tab_stops": tab_stops,
        "numbering": paragraph_numbering_state(paragraph),
    }


def _paragraph_details(paragraphs: list[Any]) -> list[dict[str, Any]]:
    ordinal = 0
    details = []
    for index, paragraph in enumerate(paragraphs):
        nonempty_ordinal = None
        if str(paragraph.String).strip():
            ordinal += 1
            nonempty_ordinal = ordinal
        details.append(_paragraph_detail(paragraph, index, nonempty_ordinal))
    return details


def _page_layout_summary(doc: Any) -> list[dict[str, Any]]:
    styles = doc.StyleFamilies.getByName("PageStyles")
    layouts = []
    for name in styles.getElementNames():
        style = styles.getByName(name)
        if not style.isInUse():
            continue
        native = {
            field: getattr(style, prop, None)
            for field, prop in (
                ("width_mm", "Width"),
                ("height_mm", "Height"),
                ("left_margin_mm", "LeftMargin"),
                ("right_margin_mm", "RightMargin"),
            )
        }
        if any(not isinstance(value, (int, float)) for value in native.values()):
            continue
        values = {field: value / 100 for field, value in native.items()}
        layouts.append(
            {
                "page_style": str(name),
                **values,
                "body_width_mm": (
                    native["width_mm"]
                    - native["left_margin_mm"]
                    - native["right_margin_mm"]
                )
                / 100,
            }
        )
    return layouts


def _footer_summary(doc: Any) -> list[dict[str, Any]]:
    styles = doc.StyleFamilies.getByName("PageStyles")
    records = []
    for name in styles.getElementNames():
        style = styles.getByName(name)
        in_use = bool(style.isInUse())
        if not in_use and not bool(style.IsPhysical):
            continue
        state = {
            "page_style": str(name),
            "in_use": in_use,
            "enabled": bool(style.FooterIsOn),
        }
        if not state["enabled"]:
            records.append(state)
            continue
        # Shared regions alias the same native text; inspect independent variants once.
        variants = (
            [("shared", "FooterText")]
            if style.FooterIsShared
            else [("right", "FooterTextRight"), ("left", "FooterTextLeft")]
        )
        if not style.FirstIsShared:
            variants.append(("first", "FooterTextFirst"))
        for variant, property_name in variants:
            text = getattr(style, property_name)
            fields = []
            for index, paragraph in enumerate(_paragraphs(text)):
                portions = paragraph.createEnumeration()
                while portions.hasMoreElements():
                    portion = portions.nextElement()
                    field = getattr(portion, "TextField", None)
                    if field is None or not field.supportsService(
                        "com.sun.star.text.TextField.PageNumber"
                    ):
                        continue
                    fields.append(
                        {
                            "paragraph_index": index,
                            "alignment": _paragraph_alignment_value(paragraph),
                            "offset": int(field.Offset),
                            "numbering_type": int(field.NumberingType),
                            "sub_type": _enum_value(field.SubType),
                        }
                    )
            records.append(
                state
                | {
                    "variant": variant,
                    "text": str(text.String)[:500],
                    "page_number_fields": fields,
                }
            )
    return records


def _highlight_summary(doc: Any) -> dict[str, Any]:
    run_count = 0
    paragraph_count = 0
    colors: dict[str, int] = {}
    for paragraph in _all_paragraphs(doc):
        highlighted_in_paragraph = False
        try:
            portions = paragraph.createEnumeration()
        except (AttributeError, TypeError):
            portions = None
        while portions is not None and portions.hasMoreElements():
            portion = portions.nextElement()
            try:
                color = int(portion.CharBackColor)
            except (AttributeError, TypeError, ValueError):
                continue
            if color >= 0:
                run_count += 1
                highlighted_in_paragraph = True
                color_name = f"#{color & 0xFFFFFF:06X}"
                colors[color_name] = colors.get(color_name, 0) + 1
        if not highlighted_in_paragraph:
            try:
                color = int(_select_paragraph(paragraph).CharBackColor)
            except (AttributeError, TypeError, ValueError):
                color = -1
            if color >= 0:
                run_count += 1
                highlighted_in_paragraph = True
                color_name = f"#{color & 0xFFFFFF:06X}"
                colors[color_name] = colors.get(color_name, 0) + 1
        if highlighted_in_paragraph:
            paragraph_count += 1
    return {
        "highlighted_run_count": run_count,
        "highlighted_paragraph_count": paragraph_count,
        "colors": colors,
    }


def _paragraph_target_indices(
    paragraphs: list[Any], params: dict[str, Any]
) -> list[int]:
    indices = params.get("indices")
    if indices is not None:
        targets = list(indices)
        if any(index >= len(paragraphs) for index in targets):
            raise AdapterError(
                "PARAGRAPH_NOT_FOUND",
                "paragraph index is out of range",
                {"paragraph_count": len(paragraphs), "indices": targets},
                404,
            )
        return targets

    ordinals = params.get("nonempty_ordinals")
    if ordinals is None:
        return list(range(len(paragraphs)))
    nonempty_indices = [
        index
        for index, paragraph in enumerate(paragraphs)
        if str(paragraph.String).strip()
    ]
    missing = [ordinal for ordinal in ordinals if ordinal > len(nonempty_indices)]
    if missing:
        raise AdapterError(
            "PARAGRAPH_NOT_FOUND",
            "nonempty paragraph ordinal is out of range",
            {
                "nonempty_paragraph_count": len(nonempty_indices),
                "nonempty_ordinals": list(ordinals),
                "missing": missing,
            },
            404,
        )
    return [nonempty_indices[ordinal - 1] for ordinal in ordinals]


def _title_case_preserve(text: str) -> str:
    def convert(token: str) -> str:
        match = re.search(r"[A-Za-z]", token)
        if not match:
            return token
        index = match.start()
        return token[:index] + token[index].upper() + token[index + 1 :]

    return re.sub(r"\S+", lambda match: convert(match.group(0)), text)


def _docx_page_break_count(path: Path) -> int:
    if not path.is_file() or not zipfile.is_zipfile(path):
        return 0
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(path) as package:
        try:
            document_xml = package.read("word/document.xml")
        except KeyError:
            return 0
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError:
        return 0
    return sum(
        1
        for element in root.findall(f".//{{{namespace}}}br")
        if element.attrib.get(f"{{{namespace}}}type") == "page"
    )


def _docx_image_count(path: Path) -> int:
    if not path.is_file() or not zipfile.is_zipfile(path):
        return 0
    with zipfile.ZipFile(path) as package:
        return sum(1 for name in package.namelist() if name.startswith("word/media/"))


def _graphic_object_count(document: Any) -> int | None:
    try:
        names = document.getGraphicObjects().getElementNames()
    except Exception:
        return None
    return len(names)


def _docx_table_dimensions(path: Path) -> list[tuple[int, int]]:
    if not path.is_file() or not zipfile.is_zipfile(path):
        return []
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(path) as package:
        root = ET.fromstring(package.read("word/document.xml"))
    result = []
    for table in root.findall(f".//{{{namespace}}}tbl"):
        rows = len(table.findall(f"{{{namespace}}}tr"))
        grid = table.find(f"{{{namespace}}}tblGrid")
        columns = (
            len(grid.findall(f"{{{namespace}}}gridCol")) if grid is not None else 0
        )
        result.append((rows, columns))
    return result


def _docx_table_values(path: Path) -> list[list[list[str]]]:
    if not path.is_file() or not zipfile.is_zipfile(path):
        return []
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(path) as package:
        root = ET.fromstring(package.read("word/document.xml"))
    result = []
    for table in root.findall(f".//{{{namespace}}}tbl"):
        rows = []
        for row in table.findall(f"{{{namespace}}}tr"):
            cells = []
            for cell in row.findall(f"{{{namespace}}}tc"):
                cells.append(
                    "".join(
                        node.text or "" for node in cell.findall(f".//{{{namespace}}}t")
                    )
                )
            rows.append(cells)
        result.append(rows)
    return result


def _saved_file_state(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"exists": False, "path": None, "size": 0, "valid": False}
    exists = path.is_file()
    suffix = path.suffix.lower()
    valid = exists and (suffix == ".pdf" or zipfile.is_zipfile(path))
    return {
        "exists": exists,
        "path": str(path),
        "size": path.stat().st_size if exists else 0,
        "valid": valid,
    }


def _verification(
    passed: bool,
    checks: list[dict[str, Any]],
    observed: Any,
    expected: Any,
    details: Any = None,
) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "checks": checks,
        "observed_state": observed,
        "expected_state": expected,
        "error_code": None if passed else "VERIFICATION_FAILED",
        "details": details,
    }


class WriterSession:
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
        self.doc = None if allow_no_document else self._select_document(selector)

    def _documents(self) -> list[Any]:
        result = []
        components = self.desktop.getComponents().createEnumeration()
        while components.hasMoreElements():
            component = components.nextElement()
            try:
                if component.supportsService("com.sun.star.text.TextDocument"):
                    result.append(component)
            except Exception:
                continue
        return result

    @staticmethod
    def identity_for(doc: Any) -> dict[str, str]:
        url = str(getattr(doc, "URL", "") or "")
        title = str(getattr(doc, "Title", "") or "")
        if not title:
            path = _url_path(url)
            title = path.name if path else ""
        return {"url": url, "title": title}

    def identity(self) -> dict[str, str]:
        return self.identity_for(self.doc)

    def _select_document(self, selector: dict[str, Any]) -> Any:
        documents = self._documents()
        if not documents:
            raise AdapterError(
                "NO_WRITER_DOCUMENT",
                "no open Writer document was found",
                http_status=404,
            )
        requested_url = selector.get("url")
        requested_title = selector.get("title")
        if requested_url:
            requested_url = _file_url(str(requested_url))
        matches = []
        for document in documents:
            identity = self.identity_for(document)
            if requested_url and identity["url"] != requested_url:
                continue
            if requested_title and identity["title"] != requested_title:
                continue
            matches.append(document)
        if requested_url or requested_title:
            if len(matches) != 1:
                raise AdapterError(
                    "DOCUMENT_MISMATCH",
                    "Writer document selector did not match exactly one open document",
                    {
                        "selector": selector,
                        "open_documents": [
                            self.identity_for(item) for item in documents
                        ],
                    },
                    404,
                )
            return matches[0]
        current = self.desktop.getCurrentComponent()
        if current in documents:
            return current
        if len(documents) == 1:
            return documents[0]
        raise AdapterError(
            "DOCUMENT_MISMATCH",
            "multiple Writer documents are open; document.url or document.title is required",
            {"open_documents": [self.identity_for(item) for item in documents]},
        )

    @property
    def path(self) -> Path | None:
        return _url_path(str(getattr(self.doc, "URL", "") or ""))

    def save(self) -> dict[str, Any]:
        if not self.doc.hasLocation():
            raise AdapterError("SAVE_FAILED", "Writer document has no saved location")
        try:
            if self.doc.isModified():
                self.doc.store()
        except Exception as exc:
            raise AdapterError(
                "SAVE_FAILED", "failed to save Writer document", str(exc), 500
            ) from exc
        state = _saved_file_state(self.path)
        if not state["exists"] or not state["valid"]:
            raise AdapterError(
                "VERIFICATION_FAILED", "saved Writer file is missing or invalid", state
            )
        return state

    def view_cursor(self) -> Any:
        controller = self.doc.getCurrentController()
        if controller is None:
            raise AdapterError(
                "LIBREOFFICE_NOT_READY", "Writer document has no active controller"
            )
        cursor = controller.getViewCursor()
        if cursor is None:
            raise AdapterError(
                "LIBREOFFICE_NOT_READY", "Writer view cursor is unavailable"
            )
        return cursor

    def dispatch(self, command: str, arguments: tuple[Any, ...] = ()) -> None:
        helper = self.service_manager.createInstanceWithContext(
            "com.sun.star.frame.DispatchHelper", self.context
        )
        helper.executeDispatch(
            self.doc.getCurrentController().getFrame(), command, "", 0, arguments
        )


def _close_component(component: Any) -> None:
    try:
        component.close(True)
        return
    except Exception:
        pass
    try:
        component.dispose()
    except Exception:
        pass


def _file_body_text(text: Any) -> str:
    parts = []
    elements = text.createEnumeration()
    while elements.hasMoreElements():
        element = elements.nextElement()
        if element.supportsService("com.sun.star.text.Paragraph"):
            parts.append(str(element.String))
        elif element.supportsService("com.sun.star.text.TextTable"):
            rows: dict[str, list[str]] = {}
            for name in _cell_names(element):
                row = re.search(r"\d+$", name)
                row_key = row.group() if row else name
                rows.setdefault(row_key, []).append(
                    _file_body_text(element.getCellByName(name).Text)
                )
            parts.extend("\t".join(cells) for cells in rows.values())
    return "\n".join(parts)


def _read_file(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    source_url = _file_url(params["path"])
    source = _url_path(source_url)
    if source is None or not source.is_file():
        raise AdapterError(
            "FILE_NOT_FOUND",
            "input document does not exist",
            {"path": str(source) if source is not None else params["path"]},
            404,
        )
    uno, _ = _uno_modules()
    properties = (
        _property("Hidden", True),
        _property("ReadOnly", True),
        # A template load is an independent in-memory copy, never an open editor.
        _property("AsTemplate", True),
        _property(
            "MacroExecutionMode",
            uno.getConstantByName("com.sun.star.document.MacroExecMode.NEVER_EXECUTE"),
        ),
        _property(
            "UpdateDocMode",
            uno.getConstantByName("com.sun.star.document.UpdateDocMode.NO_UPDATE"),
        ),
    )
    document = None
    try:
        document = session.desktop.loadComponentFromURL(
            source_url, "_blank", 0, properties
        )
        if document is None or not document.supportsService(
            "com.sun.star.text.TextDocument"
        ):
            raise AdapterError(
                "DOCUMENT_OPEN_FAILED",
                "input file did not open as a Writer document",
                {"path": str(source)},
                422,
            )
        text = _file_body_text(document.Text)
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "DOCUMENT_READ_FAILED",
            "failed to read the source Writer document",
            {"path": str(source), "error": str(exc)},
            422,
        ) from exc
    finally:
        if document is not None:
            _close_component(document)
    start = params.get("start_char", 0)
    if start > len(text):
        raise AdapterError(
            "INVALID_REQUEST",
            "start_char exceeds the source text length",
            {"path": str(source), "start_char": start, "source_total_chars": len(text)},
        )
    end = min(len(text), start + params.get("max_chars", 2000))
    content = text[start:end]
    return {
        "path": str(source),
        "status": "ok",
        "source_kind": "writer_body_text",
        "read_mode": "saved_file_snapshot",
        "activates_document": False,
        "text": content,
        "returned_chars": len(content),
        "source_start_char": start,
        "source_end_char": start + len(content),
        "source_total_chars": len(text),
        "next_start_char": end if end < len(text) else None,
        "source_truncated": end < len(text),
        "offset_basis": "writer_body_text",
    }


def _open_spreadsheet_source(
    session: WriterSession, source_url: str
) -> tuple[Any, bool]:
    components = session.desktop.getComponents().createEnumeration()
    while components.hasMoreElements():
        component = components.nextElement()
        try:
            if (
                component.supportsService("com.sun.star.sheet.SpreadsheetDocument")
                and str(getattr(component, "URL", "") or "") == source_url
            ):
                return component, False
        except Exception:
            continue
    try:
        document = session.desktop.loadComponentFromURL(
            source_url,
            "_blank",
            0,
            (_property("Hidden", True), _property("ReadOnly", True)),
        )
    except Exception as exc:
        raise AdapterError(
            "DOCUMENT_OPEN_FAILED",
            "failed to open the source spreadsheet",
            {"source_url": source_url, "error": str(exc)},
            422,
        ) from exc
    if document is None or not document.supportsService(
        "com.sun.star.sheet.SpreadsheetDocument"
    ):
        if document is not None:
            _close_component(document)
        raise AdapterError(
            "DOCUMENT_OPEN_FAILED",
            "the source file did not open as a Calc spreadsheet",
            {"source_url": source_url},
            422,
        )
    return document, True


def _open_presentation_source(
    session: WriterSession, source_url: str
) -> tuple[Any, bool]:
    components = session.desktop.getComponents().createEnumeration()
    while components.hasMoreElements():
        component = components.nextElement()
        try:
            if (
                component.supportsService(
                    "com.sun.star.presentation.PresentationDocument"
                )
                and str(getattr(component, "URL", "") or "") == source_url
            ):
                return component, False
        except Exception:
            continue
    try:
        document = session.desktop.loadComponentFromURL(
            source_url,
            "_blank",
            0,
            (_property("Hidden", True), _property("ReadOnly", True)),
        )
    except Exception as exc:
        raise AdapterError(
            "DOCUMENT_OPEN_FAILED",
            "failed to open the source presentation",
            {"source_url": source_url, "error": str(exc)},
            422,
        ) from exc
    if document is None or not document.supportsService(
        "com.sun.star.presentation.PresentationDocument"
    ):
        if document is not None:
            _close_component(document)
        raise AdapterError(
            "DOCUMENT_OPEN_FAILED",
            "the source file did not open as an Impress presentation",
            {"source_url": source_url},
            422,
        )
    return document, True


def _create_document_from_image(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    source_url = _file_url(str(params["source_path"]))
    source_path = _url_path(source_url)
    output_url = _file_url(str(params["output_path"]))
    output_path = _url_path(output_url)
    if source_path is None or output_path is None:
        raise AdapterError(
            "INVALID_REQUEST", "source_path and output_path must be local files"
        )
    source_path = source_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    source_url = _file_url(str(source_path))
    output_url = _file_url(str(output_path))
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise AdapterError(
            "FILE_NOT_FOUND",
            "the source image is missing or empty",
            {"source_path": str(source_path)},
            404,
        )
    if source_path == output_path:
        raise AdapterError(
            "INVALID_REQUEST", "source_path and output_path must be different"
        )
    overwrite = bool(params.get("overwrite", True))
    if output_path.exists() and not overwrite:
        raise AdapterError(
            "FILE_EXISTS",
            "the destination exists and overwrite is false",
            {"output_path": str(output_path)},
            409,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer_document = None
    try:
        writer_document = session.desktop.loadComponentFromURL(
            "private:factory/swriter", "_blank", 0, ()
        )
        if writer_document is None or not writer_document.supportsService(
            "com.sun.star.text.TextDocument"
        ):
            raise AdapterError(
                "DOCUMENT_CREATE_FAILED",
                "failed to create a Writer document",
                http_status=500,
            )
        image = writer_document.createInstance("com.sun.star.text.TextGraphicObject")
        image.GraphicURL = source_url
        image.AnchorType = 0
        text = writer_document.Text
        text.insertTextContent(text.getStart(), image, False)
        writer_document.storeAsURL(
            output_url,
            (
                _property("FilterName", "Office Open XML Text"),
                _property("Overwrite", overwrite),
            ),
        )
    except AdapterError:
        if writer_document is not None:
            _close_component(writer_document)
        raise
    except Exception as exc:
        if writer_document is not None:
            _close_component(writer_document)
        raise AdapterError(
            "DOCUMENT_CREATE_FAILED",
            "failed to create the Writer image document",
            {"output_path": str(output_path), "error": str(exc)},
            500,
        ) from exc

    _close_component(writer_document)
    try:
        reopened = session.desktop.loadComponentFromURL(output_url, "_blank", 0, ())
    except Exception as exc:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the saved Writer document could not be reopened",
            {"output_path": str(output_path), "error": str(exc)},
            422,
        ) from exc
    if reopened is None or not reopened.supportsService(
        "com.sun.star.text.TextDocument"
    ):
        if reopened is not None:
            _close_component(reopened)
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the saved output did not reopen as a Writer document",
            {"output_path": str(output_path)},
            422,
        )
    session.doc = reopened
    try:
        graphic_object_count = len(reopened.getGraphicObjects().getElementNames())
    except Exception:
        graphic_object_count = 0
    embedded_image_count = _docx_image_count(output_path)
    if graphic_object_count != 1 or embedded_image_count != 1:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the reopened Writer document does not contain exactly one embedded image",
            {
                "graphic_object_count": graphic_object_count,
                "embedded_image_count": embedded_image_count,
            },
            422,
        )
    saved = _saved_file_state(output_path)
    if not saved["exists"] or not saved["valid"]:
        raise AdapterError(
            "VERIFICATION_FAILED", "the output DOCX is missing or invalid", saved, 422
        )
    return {
        "source_path": str(source_path),
        "source_url": source_url,
        "output_path": str(output_path),
        "output_bytes": output_path.stat().st_size,
        "graphic_object_count": graphic_object_count,
        "embedded_image_count": embedded_image_count,
        "reopened": True,
        "verified": True,
    }


def _normalized_writer_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _create_document_from_text_files(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    input_paths: list[Path] = []
    input_text: list[str] = []
    input_files: list[dict[str, Any]] = []
    total_input_bytes = 0
    for index, raw_path in enumerate(params["input_paths"]):
        source_url = _file_url(str(raw_path))
        source_path = _url_path(source_url)
        if source_path is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "input_paths must identify local files",
                {"index": index, "path": raw_path},
            )
        source_path = source_path.expanduser().resolve()
        if not source_path.is_file():
            raise AdapterError(
                "FILE_NOT_FOUND",
                "an input text file does not exist",
                {"index": index, "path": str(source_path)},
                404,
            )
        data = source_path.read_bytes()
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AdapterError(
                "TEXT_DECODE_FAILED",
                "an input file is not valid UTF-8 text",
                {
                    "index": index,
                    "path": str(source_path),
                    "byte_offset": exc.start,
                },
                422,
            ) from exc
        content = _normalized_writer_text(content)
        input_paths.append(source_path)
        input_text.append(content)
        total_input_bytes += len(data)
        input_files.append(
            {
                "index": index,
                "path": str(source_path),
                "bytes": len(data),
                "characters": len(content),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    output_url = _file_url(str(params["output_path"]))
    output_path = _url_path(output_url)
    if output_path is None:
        raise AdapterError("INVALID_REQUEST", "output_path must be a local file")
    output_path = output_path.expanduser().resolve()
    output_url = _file_url(str(output_path))
    if output_path in input_paths:
        raise AdapterError(
            "INVALID_REQUEST", "output_path must differ from every input path"
        )
    overwrite = bool(params.get("overwrite", True))
    if output_path.exists() and not overwrite:
        raise AdapterError(
            "FILE_EXISTS",
            "the destination exists and overwrite is false",
            {"output_path": str(output_path)},
            409,
        )
    separator = _normalized_writer_text(str(params["separator"]))
    combined = separator.join(input_text)
    if len(combined) > 2_000_000:
        raise AdapterError(
            "TEXT_TOO_LARGE",
            "the combined text exceeds the bounded Writer document limit",
            {
                "characters": len(combined),
                "max_characters": 2_000_000,
                "input_count": len(input_paths),
            },
            422,
        )
    font_size = float(params["font_size"])
    expected_sha256 = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer_document = None
    try:
        writer_document = session.desktop.loadComponentFromURL(
            "private:factory/swriter", "_blank", 0, ()
        )
        if writer_document is None or not writer_document.supportsService(
            "com.sun.star.text.TextDocument"
        ):
            raise AdapterError(
                "DOCUMENT_CREATE_FAILED",
                "failed to create a Writer document",
                http_status=500,
            )
        writer_document.Text.String = combined
        cursor = _whole_text_cursor(writer_document.Text)
        cursor.CharHeight = font_size
        cursor.CharHeightAsian = font_size
        cursor.CharHeightComplex = font_size
        writer_document.storeAsURL(
            output_url,
            (
                _property("FilterName", "Office Open XML Text"),
                _property("Overwrite", overwrite),
            ),
        )
    except AdapterError:
        if writer_document is not None:
            _close_component(writer_document)
        raise
    except Exception as exc:
        if writer_document is not None:
            _close_component(writer_document)
        raise AdapterError(
            "DOCUMENT_CREATE_FAILED",
            "failed to create the Writer text document",
            {"output_path": str(output_path), "error": str(exc)},
            500,
        ) from exc

    _close_component(writer_document)
    try:
        reopened = session.desktop.loadComponentFromURL(output_url, "_blank", 0, ())
    except Exception as exc:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the saved Writer document could not be reopened",
            {"output_path": str(output_path), "error": str(exc)},
            422,
        ) from exc
    if reopened is None or not reopened.supportsService(
        "com.sun.star.text.TextDocument"
    ):
        if reopened is not None:
            _close_component(reopened)
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the saved output did not reopen as a Writer document",
            {"output_path": str(output_path)},
            422,
        )
    session.doc = reopened
    observed_text = _normalized_writer_text(str(reopened.Text.String))
    observed_sha256 = hashlib.sha256(observed_text.encode("utf-8")).hexdigest()
    observed_cursor = _whole_text_cursor(reopened.Text)
    observed_font_sizes = {
        name: float(getattr(observed_cursor, name))
        for name in ("CharHeight", "CharHeightAsian", "CharHeightComplex")
    }
    font_verified = all(
        abs(value - font_size) <= 0.01 for value in observed_font_sizes.values()
    )
    if observed_text != combined or not font_verified:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the reopened Writer document did not preserve the combined text and uniform font size",
            {
                "expected_characters": len(combined),
                "observed_characters": len(observed_text),
                "expected_sha256": expected_sha256,
                "observed_sha256": observed_sha256,
                "expected_font_size": font_size,
                "observed_font_sizes": observed_font_sizes,
            },
            422,
        )
    saved = _saved_file_state(output_path)
    if not saved["exists"] or not saved["valid"]:
        raise AdapterError(
            "VERIFICATION_FAILED", "the output DOCX is missing or invalid", saved, 422
        )
    return {
        "input_files": input_files,
        "input_count": len(input_paths),
        "input_bytes": total_input_bytes,
        "separator": separator,
        "characters": len(combined),
        "content_sha256": expected_sha256,
        "font_size": font_size,
        "observed_font_sizes": observed_font_sizes,
        "output_path": str(output_path),
        "output_bytes": output_path.stat().st_size,
        "reopened": True,
        "verified": True,
    }


_PRESENTATION_AUTO_FIELDS = frozenset(
    {"<number>", "<date>", "<time>", "<date/time>", "<footer>"}
)


def _presentation_shape_text_blocks(
    shape: Any, *, include_auto_fields: bool
) -> list[str]:
    blocks: list[str] = []
    try:
        paragraphs = shape.getText().createEnumeration()
        while paragraphs.hasMoreElements():
            paragraph = paragraphs.nextElement()
            value = str(paragraph.getString()).replace("\r", "").replace("\v", "")
            if not value.strip():
                continue
            if (
                not include_auto_fields
                and value.strip().casefold() in _PRESENTATION_AUTO_FIELDS
            ):
                continue
            blocks.append(value)
    except Exception:
        pass

    if not blocks:
        try:
            model = shape.Model
            rows = int(model.getRowCount())
            columns = int(model.getColumnCount())
            for row in range(rows):
                for column in range(columns):
                    value = str(model.getCellByPosition(column, row).String)
                    if value.strip():
                        blocks.append(value)
        except Exception:
            pass

    try:
        child_count = int(shape.getCount())
    except Exception:
        child_count = 0
    if child_count and not blocks:
        for index in range(child_count):
            blocks.extend(
                _presentation_shape_text_blocks(
                    shape.getByIndex(index),
                    include_auto_fields=include_auto_fields,
                )
            )
    return blocks


def _presentation_page_text_blocks(
    page: Any, *, include_auto_fields: bool
) -> list[str]:
    blocks: list[str] = []
    for index in range(int(page.getCount())):
        blocks.extend(
            _presentation_shape_text_blocks(
                page.getByIndex(index), include_auto_fields=include_auto_fields
            )
        )
    return blocks


def _safe_property(value: Any, name: str) -> Any:
    try:
        return getattr(value, name)
    except Exception:
        return None


def _spreadsheet_cell_snapshot(cell: Any) -> dict[str, Any]:
    return {
        "text": str(cell.getString()),
        "background": _safe_property(cell, "CellBackColor"),
        "font_color": _safe_property(cell, "CharColor"),
        "font_weight": _safe_property(cell, "CharWeight"),
        "font_posture": _safe_property(cell, "CharPosture"),
        "font_height": _safe_property(cell, "CharHeight"),
        "font_name": _safe_property(cell, "CharFontName"),
        "horizontal_alignment": _safe_property(cell, "HoriJustify"),
        "borders": {
            name: _safe_property(cell, name)
            for name in ("TopBorder", "BottomBorder", "LeftBorder", "RightBorder")
        },
    }


def _trim_trailing_blank_cells(
    rows: list[list[dict[str, Any]]],
    column_widths: list[int],
    *,
    enabled: bool,
) -> tuple[list[list[dict[str, Any]]], list[int], int, int]:
    original_rows = len(rows)
    original_columns = len(rows[0]) if rows else 0
    if enabled:
        while rows and all(not cell["text"].strip() for cell in rows[-1]):
            rows.pop()
        while rows and rows[0] and all(not row[-1]["text"].strip() for row in rows):
            for row in rows:
                row.pop()
            if column_widths:
                column_widths.pop()
    if not rows or not rows[0]:
        raise AdapterError(
            "EMPTY_RANGE",
            "the selected spreadsheet range contains no displayed data",
            http_status=422,
        )
    return (
        rows,
        column_widths,
        original_rows - len(rows),
        original_columns - len(rows[0]),
    )


def _set_writer_property(target: Any, name: str, value: Any) -> bool:
    if value is None:
        return False
    try:
        setattr(target, name, value)
        return True
    except Exception:
        return False


def _apply_spreadsheet_cell_format(source: dict[str, Any], target: Any) -> bool:
    changed = False
    background = source.get("background")
    if isinstance(background, int) and 0 <= background <= 0xFFFFFF:
        changed |= _set_writer_property(target, "BackTransparent", False)
        changed |= _set_writer_property(target, "BackColor", background)
    for name, value in source.get("borders", {}).items():
        changed |= _set_writer_property(target, name, value)
    try:
        cursor = target.createTextCursor()
        cursor.gotoEnd(True)
    except Exception:
        return changed
    for target_name, source_name in (
        ("CharColor", "font_color"),
        ("CharWeight", "font_weight"),
        ("CharPosture", "font_posture"),
        ("CharHeight", "font_height"),
        ("CharFontName", "font_name"),
    ):
        changed |= _set_writer_property(cursor, target_name, source.get(source_name))
    alignment = _enum_value(source.get("horizontal_alignment"))
    paragraph_alignment = {
        "standard": 0,
        "left": 0,
        "right": 1,
        "block": 2,
        "center": 3,
    }.get(alignment)
    if paragraph_alignment is not None:
        changed |= _set_writer_property(cursor, "ParaAdjust", paragraph_alignment)
    return changed


def _apply_relative_column_widths(table: Any, widths: list[int]) -> bool:
    if len(widths) < 2 or any(width <= 0 for width in widths):
        return False
    total = sum(widths)
    try:
        separators = list(table.TableColumnSeparators)
        if len(separators) != len(widths) - 1:
            return False
        cumulative = 0
        for separator, width in zip(separators, widths[:-1]):
            cumulative += width
            separator.Position = round(10_000 * cumulative / total)
        table.IsWidthRelative = True
        table.RelativeWidth = 100
        table.TableColumnSeparators = tuple(separators)
        return True
    except Exception:
        return False


def _uno_table_values(table: Any) -> list[list[str]]:
    rows = int(table.Rows.Count)
    columns = int(table.Columns.Count)
    names = _cell_names(table)
    return [
        [
            str(table.getCellByName(names[row * columns + column]).String)
            for column in range(columns)
        ]
        for row in range(rows)
    ]


def _create_document_from_spreadsheet(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    source_url = _file_url(str(params["source_path"]))
    source_path = _url_path(source_url)
    output_url = _file_url(str(params["output_path"]))
    output_path = _url_path(output_url)
    if source_path is None or output_path is None:
        raise AdapterError(
            "INVALID_REQUEST", "source_path and output_path must be local files"
        )
    source_path = source_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    source_url = _file_url(str(source_path))
    output_url = _file_url(str(output_path))
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise AdapterError(
            "FILE_NOT_FOUND",
            "the source spreadsheet is missing or empty",
            {"source_path": str(source_path)},
            404,
        )
    if source_path == output_path:
        raise AdapterError(
            "INVALID_REQUEST", "source_path and output_path must be different"
        )
    overwrite = bool(params.get("overwrite", True))
    if output_path.exists() and not overwrite:
        raise AdapterError(
            "FILE_EXISTS",
            "the destination exists and overwrite is false",
            {"output_path": str(output_path)},
            409,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_document, close_source = _open_spreadsheet_source(session, source_url)
    try:
        try:
            source_document.calculateAll()
            sheets = source_document.getSheets()
            sheet_name = str(params["sheet"])
            if not sheets.hasByName(sheet_name):
                raise AdapterError(
                    "SHEET_NOT_FOUND",
                    f"sheet not found: {sheet_name}",
                    {"sheet_names": list(sheets.getElementNames())},
                    404,
                )
            sheet = sheets.getByName(sheet_name)
            source_range = sheet.getCellRangeByName(str(params["range"]))
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(
                "RANGE_NOT_FOUND",
                "the requested A1 range could not be read",
                {"sheet": params["sheet"], "range": params["range"], "error": str(exc)},
                404,
            ) from exc
        address = source_range.getRangeAddress()
        source_rows = address.EndRow - address.StartRow + 1
        source_columns = address.EndColumn - address.StartColumn + 1
        if (
            source_rows > 500
            or source_columns > 100
            or source_rows * source_columns > 20_000
        ):
            raise AdapterError(
                "RANGE_TOO_LARGE",
                "the selected range exceeds the bounded Writer table limit",
                {
                    "rows": source_rows,
                    "columns": source_columns,
                    "max_rows": 500,
                    "max_columns": 100,
                    "max_cells": 20_000,
                },
                422,
            )
        snapshots = [
            [
                _spreadsheet_cell_snapshot(source_range.getCellByPosition(column, row))
                for column in range(source_columns)
            ]
            for row in range(source_rows)
        ]
        try:
            columns = sheet.getColumns()
            column_widths = [
                int(columns.getByIndex(address.StartColumn + index).Width)
                for index in range(source_columns)
            ]
        except Exception:
            column_widths = [1] * source_columns
    finally:
        if close_source:
            _close_component(source_document)

    snapshots, column_widths, trimmed_rows, trimmed_columns = (
        _trim_trailing_blank_cells(
            snapshots,
            column_widths,
            enabled=bool(params.get("trim_trailing_blank", True)),
        )
    )
    display_text = [[cell["text"] for cell in row] for row in snapshots]
    row_count = len(display_text)
    column_count = len(display_text[0])
    preserve_format = bool(params.get("preserve_format", True))

    writer_document = None
    try:
        writer_document = session.desktop.loadComponentFromURL(
            "private:factory/swriter", "_blank", 0, ()
        )
        if writer_document is None or not writer_document.supportsService(
            "com.sun.star.text.TextDocument"
        ):
            raise AdapterError(
                "DOCUMENT_CREATE_FAILED",
                "failed to create a Writer document",
                http_status=500,
            )
        table = writer_document.createInstance("com.sun.star.text.TextTable")
        table.initialize(row_count, column_count)
        anchor = writer_document.Text.getStart()
        writer_document.Text.insertTextContent(anchor, table, False)
        names = _cell_names(table)
        formatted_cells = 0
        for row_index, row in enumerate(snapshots):
            for column_index, source_cell in enumerate(row):
                target = table.getCellByName(
                    names[row_index * column_count + column_index]
                )
                target.String = source_cell["text"]
                if preserve_format and _apply_spreadsheet_cell_format(
                    source_cell, target
                ):
                    formatted_cells += 1
        column_widths_applied = preserve_format and _apply_relative_column_widths(
            table, column_widths
        )
        writer_document.storeAsURL(
            output_url,
            (
                _property("FilterName", "Office Open XML Text"),
                _property("Overwrite", overwrite),
            ),
        )
    except AdapterError:
        if writer_document is not None:
            _close_component(writer_document)
        raise
    except Exception as exc:
        if writer_document is not None:
            _close_component(writer_document)
        raise AdapterError(
            "DOCUMENT_CREATE_FAILED",
            "failed to create the Writer table document",
            {"output_path": str(output_path), "error": str(exc)},
            500,
        ) from exc

    _close_component(writer_document)
    try:
        reopened = session.desktop.loadComponentFromURL(output_url, "_blank", 0, ())
    except Exception as exc:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the saved Writer document could not be reopened",
            {"output_path": str(output_path), "error": str(exc)},
            422,
        ) from exc
    if reopened is None or not reopened.supportsService(
        "com.sun.star.text.TextDocument"
    ):
        if reopened is not None:
            _close_component(reopened)
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the saved output did not reopen as a Writer document",
            {"output_path": str(output_path)},
            422,
        )
    session.doc = reopened
    tables = _tables(reopened)
    observed_dimensions = [
        [int(item.Rows.Count), int(item.Columns.Count)] for item in tables
    ]
    observed_values = _uno_table_values(tables[0]) if len(tables) == 1 else []
    if (
        observed_dimensions != [[row_count, column_count]]
        or observed_values != display_text
    ):
        mismatch_count = 0
        if len(observed_values) == row_count:
            mismatch_count = sum(
                actual != expected
                for actual_row, expected_row in zip(observed_values, display_text)
                for actual, expected in zip(actual_row, expected_row)
            )
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the reopened Writer table did not match the source displayed text",
            {
                "expected_dimensions": [[row_count, column_count]],
                "observed_dimensions": observed_dimensions,
                "mismatch_count": mismatch_count,
            },
            422,
        )
    saved = _saved_file_state(output_path)
    if not saved["exists"] or not saved["valid"]:
        raise AdapterError(
            "VERIFICATION_FAILED", "the output DOCX is missing or invalid", saved, 422
        )
    return {
        "source_path": str(source_path),
        "source_url": source_url,
        "sheet": str(params["sheet"]),
        "range": str(params["range"]),
        "source_rows": source_rows,
        "source_columns": source_columns,
        "rows": row_count,
        "columns": column_count,
        "trimmed_trailing_rows": trimmed_rows,
        "trimmed_trailing_columns": trimmed_columns,
        "preserve_format": preserve_format,
        "formatted_cells": formatted_cells,
        "column_widths_applied": bool(column_widths_applied),
        "output_path": str(output_path),
        "output_bytes": output_path.stat().st_size,
        "reopened": True,
        "verified": True,
    }


def _create_document_from_presentation(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    source_url = _file_url(str(params["source_path"]))
    source_path = _url_path(source_url)
    output_url = _file_url(str(params["output_path"]))
    output_path = _url_path(output_url)
    if source_path is None or output_path is None:
        raise AdapterError(
            "INVALID_REQUEST", "source_path and output_path must be local files"
        )
    source_path = source_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    source_url = _file_url(str(source_path))
    output_url = _file_url(str(output_path))
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise AdapterError(
            "FILE_NOT_FOUND",
            "the source presentation is missing or empty",
            {"source_path": str(source_path)},
            404,
        )
    if source_path == output_path:
        raise AdapterError(
            "INVALID_REQUEST", "source_path and output_path must be different"
        )
    overwrite = bool(params.get("overwrite", True))
    if output_path.exists() and not overwrite:
        raise AdapterError(
            "FILE_EXISTS",
            "the destination exists and overwrite is false",
            {"output_path": str(output_path)},
            409,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    include_notes = bool(params.get("include_notes", False))
    include_auto_fields = bool(params.get("include_auto_fields", False))
    source_document, close_source = _open_presentation_source(session, source_url)
    slide_block_counts: list[int] = []
    note_block_counts: list[int] = []
    text_blocks: list[str] = []
    try:
        pages = source_document.getDrawPages()
        slide_count = int(pages.getCount())
        for slide_index in range(slide_count):
            page = pages.getByIndex(slide_index)
            slide_blocks = _presentation_page_text_blocks(
                page, include_auto_fields=include_auto_fields
            )
            text_blocks.extend(slide_blocks)
            slide_block_counts.append(len(slide_blocks))
            note_blocks: list[str] = []
            if include_notes:
                try:
                    note_blocks = _presentation_page_text_blocks(
                        page.getNotesPage(),
                        include_auto_fields=include_auto_fields,
                    )
                except Exception:
                    note_blocks = []
                text_blocks.extend(note_blocks)
            note_block_counts.append(len(note_blocks))
    except Exception as exc:
        raise AdapterError(
            "PRESENTATION_READ_FAILED",
            "failed to read presentation text",
            {"source_path": str(source_path), "error": str(exc)},
            422,
        ) from exc
    finally:
        if close_source:
            _close_component(source_document)

    total_characters = sum(len(value) for value in text_blocks)
    if not text_blocks:
        raise AdapterError(
            "EMPTY_PRESENTATION_TEXT",
            "the presentation contains no selected nonempty text",
            {"slide_count": slide_count},
            422,
        )
    if len(text_blocks) > 20_000 or total_characters > 2_000_000:
        raise AdapterError(
            "PRESENTATION_TEXT_TOO_LARGE",
            "the selected presentation text exceeds the bounded Writer document limit",
            {
                "text_blocks": len(text_blocks),
                "characters": total_characters,
                "max_text_blocks": 20_000,
                "max_characters": 2_000_000,
            },
            422,
        )

    writer_document = None
    try:
        writer_document = session.desktop.loadComponentFromURL(
            "private:factory/swriter", "_blank", 0, ()
        )
        if writer_document is None or not writer_document.supportsService(
            "com.sun.star.text.TextDocument"
        ):
            raise AdapterError(
                "DOCUMENT_CREATE_FAILED",
                "failed to create a Writer document",
                http_status=500,
            )
        text = writer_document.Text
        cursor = text.createTextCursorByRange(text.getStart())
        for index, value in enumerate(text_blocks):
            text.insertString(cursor, value, False)
            if index + 1 < len(text_blocks):
                text.insertControlCharacter(cursor, 0, False)
        writer_document.storeAsURL(
            output_url,
            (
                _property("FilterName", "Office Open XML Text"),
                _property("Overwrite", overwrite),
            ),
        )
    except AdapterError:
        if writer_document is not None:
            _close_component(writer_document)
        raise
    except Exception as exc:
        if writer_document is not None:
            _close_component(writer_document)
        raise AdapterError(
            "DOCUMENT_CREATE_FAILED",
            "failed to create the Writer text document",
            {"output_path": str(output_path), "error": str(exc)},
            500,
        ) from exc

    _close_component(writer_document)
    try:
        reopened = session.desktop.loadComponentFromURL(output_url, "_blank", 0, ())
    except Exception as exc:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the saved Writer document could not be reopened",
            {"output_path": str(output_path), "error": str(exc)},
            422,
        ) from exc
    if reopened is None or not reopened.supportsService(
        "com.sun.star.text.TextDocument"
    ):
        if reopened is not None:
            _close_component(reopened)
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the saved output did not reopen as a Writer document",
            {"output_path": str(output_path)},
            422,
        )
    session.doc = reopened
    observed_blocks = [
        str(paragraph.String)
        for paragraph in _paragraphs(reopened.Text)
        if str(paragraph.String).strip()
    ]
    if observed_blocks != text_blocks:
        mismatch_count = sum(
            actual != expected for actual, expected in zip(observed_blocks, text_blocks)
        ) + abs(len(observed_blocks) - len(text_blocks))
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the reopened Writer paragraphs did not match the extracted presentation text",
            {
                "expected_text_blocks": len(text_blocks),
                "observed_paragraphs": len(observed_blocks),
                "mismatch_count": mismatch_count,
            },
            422,
        )
    saved = _saved_file_state(output_path)
    if not saved["exists"] or not saved["valid"]:
        raise AdapterError(
            "VERIFICATION_FAILED", "the output DOCX is missing or invalid", saved, 422
        )
    return {
        "source_path": str(source_path),
        "source_url": source_url,
        "slide_count": slide_count,
        "slide_text_blocks": slide_block_counts,
        "note_text_blocks": note_block_counts,
        "text_blocks": len(text_blocks),
        "characters": total_characters,
        "include_notes": include_notes,
        "include_auto_fields": include_auto_fields,
        "output_path": str(output_path),
        "output_bytes": output_path.stat().st_size,
        "reopened": True,
        "verified": True,
    }


def _inspect(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    body = _paragraphs(session.doc.Text)
    tables = _tables(session.doc)
    details = _paragraph_details(body)
    page: dict[str, Any] = {}
    selected_body = body
    if "paragraph_start" in params or "paragraph_limit" in params:
        start = params.get("paragraph_start", 0)
        limit = params.get("paragraph_limit", 12)
        selected_body = body[start : start + limit]
        # Slice after enumeration so raw indices and text ordinals stay document-wide.
        details = details[start : start + limit]
        for detail, paragraph in zip(details, selected_body):
            detail["text"] = str(paragraph.String)
        end = start + len(selected_body)
        page = {
            "paragraph_start": start,
            "paragraph_limit": limit,
            "next_paragraph_start": end if end < len(body) else None,
            "has_more": end < len(body),
        }
    return {
        "identity": session.identity(),
        "modified": bool(session.doc.isModified()),
        "paragraph_count": len(body),
        "nonempty_paragraph_count": sum(
            1 for paragraph in body if paragraph.String.strip()
        ),
        "paragraphs": [detail["text"] for detail in details],
        "paragraph_details": details,
        "page_layouts": _page_layout_summary(session.doc),
        "footers": _footer_summary(session.doc),
        "fonts": _font_summary(session.doc),
        "tables": [
            {
                "name": str(table.Name),
                "rows": int(table.Rows.Count),
                "columns": int(table.Columns.Count),
            }
            for table in tables
        ],
        "highlighting": _highlight_summary(session.doc),
        "graphic_object_count": _graphic_object_count(session.doc),
        "embedded_images": _docx_image_count(session.path) if session.path else 0,
        "page_breaks": _docx_page_break_count(session.path) if session.path else 0,
    } | page


def _save_action(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    target = params.get("url")
    if target:
        properties = [_property("Overwrite", True)]
        filter_name = params.get("filter_name")
        if filter_name:
            properties.append(_property("FilterName", filter_name))
        try:
            session.doc.storeAsURL(_file_url(str(target)), tuple(properties))
        except Exception as exc:
            raise AdapterError(
                "SAVE_FAILED", "failed to save Writer document", str(exc), 500
            ) from exc
    return session.save()


def _pdf_export_path(session: WriterSession, params: dict[str, Any]) -> Path:
    if "path" in params:
        return Path(params["path"]).expanduser()
    source = session.path
    if source is None:
        raise AdapterError(
            "EXPORT_PATH_UNAVAILABLE",
            "same-basename PDF export requires an active document with a local saved URL",
            session.identity(),
            422,
        )
    return source.with_suffix(".pdf")


def _export_pdf(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    path = _pdf_export_path(session, params)
    return _export_pdf_document(
        session.doc, session.path, path,
        preserve_soft_wrap_spaces=params.get("preserve_soft_wrap_spaces", True),
    )


def _export_pdf_document(
    document: Any, source: Path | None, path: Path, *, preserve_soft_wrap_spaces: bool
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        document.storeToURL(
            _file_url(str(path)),
            (
                _property("FilterName", "writer_pdf_Export"),
                _property("Overwrite", True),
            ),
        )
    except Exception as exc:
        raise AdapterError(
            "EXPORT_FAILED", "failed to export Writer PDF", str(exc), 500
        ) from exc
    state = _saved_file_state(path)
    if not state["exists"] or path.read_bytes()[:5] != b"%PDF-":
        raise AdapterError(
            "VERIFICATION_FAILED", "exported PDF is missing or invalid", state
        )
    soft_wrap_spaces = (
        preserve_docx_soft_wrap_spaces(source, path)
        if preserve_soft_wrap_spaces
        else {
            "status": "disabled",
            "source_format": source.suffix.lower() if source else None,
            "target_count": 0,
            "patched_trailing_spaces": 0,
        }
    )
    state = _saved_file_state(path)
    if not state["exists"] or path.read_bytes()[:5] != b"%PDF-":
        raise AdapterError(
            "VERIFICATION_FAILED", "normalized PDF is missing or invalid", state
        )
    return {
        **state,
        "source_path": str(source) if source else None,
        "source_url": str(getattr(document, "URL", "") or ""),
        "pdf_header": True,
        "soft_wrap_space_preservation": soft_wrap_spaces,
    }


def _export_file_pdf(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    source_url = _file_url(params["source_path"])
    source = _url_path(source_url)
    target = _url_path(_file_url(params["output_path"]))
    if source is None or not source.is_file():
        raise AdapterError("FILE_NOT_FOUND", "input document does not exist", http_status=404)
    if target is None or target.suffix.lower() != ".pdf":
        raise AdapterError("INVALID_REQUEST", "output_path must be a local PDF path")
    if source.resolve() == target.resolve() or (
        target.exists() and os.path.samefile(source, target)
    ):
        raise AdapterError("INVALID_REQUEST", "PDF destination must not overwrite the source")
    uno, _ = _uno_modules()
    properties = (
        _property("Hidden", True),
        _property("ReadOnly", True),
        _property("AsTemplate", True),
        _property(
            "MacroExecutionMode",
            uno.getConstantByName("com.sun.star.document.MacroExecMode.NEVER_EXECUTE"),
        ),
        _property(
            "UpdateDocMode",
            uno.getConstantByName("com.sun.star.document.UpdateDocMode.NO_UPDATE"),
        ),
    )
    document = None
    try:
        document = session.desktop.loadComponentFromURL(source_url, "_blank", 0, properties)
        if document is None or not document.supportsService("com.sun.star.text.TextDocument"):
            raise AdapterError(
                "DOCUMENT_OPEN_FAILED", "input file did not open as a Writer document",
                {"path": str(source)}, 422,
            )
        result = _export_pdf_document(
            document, source, target,
            preserve_soft_wrap_spaces=params.get("preserve_soft_wrap_spaces", True),
        )
        return {
            **result, "source_url": source_url,
            "export_mode": "saved_file_snapshot", "activates_document": False,
            "output_path": str(target), "output_bytes": target.stat().st_size,
            "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "EXPORT_FAILED", "failed to export the source Writer file",
            {"source_path": str(source), "output_path": str(target), "error": str(exc)}, 500,
        ) from exc
    finally:
        if document is not None:
            _close_component(document)


def _set_font(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    font_name = params["font_name"]
    changed = 0
    for text in _all_text_objects(session.doc):
        cursor = _whole_text_cursor(text)
        for property_name in (
            "CharFontName",
            "CharFontNameAsian",
            "CharFontNameComplex",
        ):
            cursor.setPropertyValue(property_name, font_name)
        changed += 1
    return {
        "font_name": font_name,
        "text_objects": changed,
        "fonts": _font_summary(session.doc),
    }


def _transform_case(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    mode = params["mode"]
    changed = 0
    for paragraph in list(_all_paragraphs(session.doc)):
        original = str(paragraph.String)
        transformed = (
            original.lower() if mode == "lower" else _title_case_preserve(original)
        )
        if transformed != original:
            paragraph.String = transformed
            changed += 1
    return {"mode": mode, "paragraphs_changed": changed}


def _remove_highlighting(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    before = _highlight_summary(session.doc)
    for paragraph in _all_paragraphs(session.doc):
        cursor = _select_paragraph(paragraph)
        cursor.CharBackColor = -1
        portions = paragraph.createEnumeration()
        while portions.hasMoreElements():
            portion = portions.nextElement()
            try:
                portion.CharBackColor = -1
            except Exception:
                continue
    after = _highlight_summary(session.doc)
    if after["highlighted_run_count"]:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "character background highlighting remains after removal",
            {"before": before, "after": after},
            422,
        )
    return {
        "paragraphs_changed": before["highlighted_paragraph_count"],
        "highlighting_before": before,
        "highlighting_after": after,
        "verified": True,
    }


def _add_page_numbers(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    alignment = {"bottom_left": 0, "bottom_center": 3, "bottom_right": 1}[
        params.get("position", "bottom_left")
    ]
    page_styles = session.doc.StyleFamilies.getByName("PageStyles")
    changed = []
    for name in page_styles.getElementNames():
        style = page_styles.getByName(name)
        if name != "Standard" and not bool(getattr(style, "IsPhysical", False)):
            continue
        try:
            style.FooterIsOn = True
            footer = style.FooterText
            cursor = footer.createTextCursorByRange(footer.getStart())
            cursor.gotoRange(footer.getEnd(), True)
            cursor.String = ""
            cursor.gotoStart(False)
            cursor.ParaAdjust = alignment
            field = session.doc.createInstance("com.sun.star.text.TextField.PageNumber")
            field.NumberingType = 4
            footer.insertTextContent(cursor, field, False)
            changed.append(name)
        except Exception:
            if name == "Standard":
                raise
    session.doc.getTextFields().refresh()
    return {"position": params.get("position", "bottom_left"), "page_styles": changed}


def _insert_page_break(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    session.dispatch(".uno:InsertPagebreak")
    return {"inserted": True, "position": "view_cursor"}


def _append_paragraphs(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    values = list(params["paragraphs"])
    blank_before = int(params.get("blank_paragraphs_before", 0))
    blank_between = int(params.get("blank_paragraphs_between", 0))
    text = session.doc.Text
    existing = _paragraphs(text)

    first_index = 0
    if existing and not str(existing[-1].String).strip() and blank_before == 0:
        existing[-1].String = values[0]
        first_index = 1
    else:
        cursor = text.createTextCursorByRange(text.getEnd())
        for _ in range(blank_before + 1):
            text.insertControlCharacter(cursor, 0, False)
        text.insertString(cursor, values[0], False)
        first_index = 1

    cursor = text.createTextCursorByRange(text.getEnd())
    for value in values[first_index:]:
        for _ in range(blank_between + 1):
            text.insertControlCharacter(cursor, 0, False)
        text.insertString(cursor, value, False)
    return {
        "paragraphs": values,
        "appended_count": len(values),
        "blank_paragraphs_before": blank_before,
        "blank_paragraphs_between": blank_between,
    }


def _apply_paragraph_format_fields(paragraph: Any, params: dict[str, Any]) -> None:
    alignment = {"left": 0, "right": 1, "justify": 2, "center": 3}
    if "line_spacing" in params:
        _set_line_spacing(paragraph, float(params["line_spacing"]))
    if "alignment" in params:
        paragraph.ParaAdjust = alignment[params["alignment"]]
    if "tab_stops" in params:
        uno, _ = _uno_modules()
        tab_stops = []
        for item in params["tab_stops"]:
            stop = uno.createUnoStruct("com.sun.star.style.TabStop")
            position = item["position"]
            stop.Position = round(position["value"] * TAB_STOP_UNITS[position["unit"]])
            stop.Alignment = uno.Enum(
                "com.sun.star.style.TabAlign", item["alignment"].upper()
            )
            stop.DecimalChar = uno.Char(item.get("decimal_character", "."))
            stop.FillChar = uno.Char(item.get("fill_character", " "))
            tab_stops.append(stop)
        paragraph.ParaTabStops = tuple(tab_stops)
    cursor = _select_paragraph(paragraph)
    if "font_size" in params:
        size = float(params["font_size"])
        cursor.CharHeight = size
        cursor.CharHeightAsian = size
        cursor.CharHeightComplex = size
    if "strikethrough" in params:
        cursor.CharStrikeout = 1 if params["strikethrough"] else 0


def _set_paragraph_format(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    paragraphs = _paragraphs(session.doc.Text)
    targets = _paragraph_target_indices(paragraphs, params)
    for index in targets:
        _apply_paragraph_format_fields(paragraphs[index], params)
    selector_fields = {"indices", "nonempty_ordinals"}
    details_by_index = {
        detail["index"]: detail for detail in _paragraph_details(paragraphs)
    }
    selected_details = [details_by_index[index] for index in targets]
    result = {
        "indices": targets,
        "nonempty_ordinals": params.get("nonempty_ordinals"),
        "formats": {
            key: value for key, value in params.items() if key not in selector_fields
        },
        "paragraph_details": selected_details,
    }
    if "tab_stops" in params:
        with_tabs = sum(detail["has_tab_character"] for detail in selected_details)
        without_tabs = len(selected_details) - with_tabs
        if not params["tab_stops"]:
            guidance = (
                "Explicit tab stops cleared; paragraph text and any Tab characters "
                "were not changed."
            )
        elif without_tabs:
            guidance = (
                "Tab-stop formatting changed; paragraph text was not changed. "
                "Paragraphs without a Tab have no following text for these stops to align. "
                "To insert a Tab, use text.find_replace with an observed anchor and JSON \\t."
            )
        else:
            guidance = (
                "Tab-stop formatting changed; paragraph text was not changed. "
                "Stops align text following an actual Tab."
            )
        result["tab_stop_observation"] = {
            "selected_paragraph_count": len(selected_details),
            "paragraphs_with_tabs_count": with_tabs,
            "paragraphs_without_tabs_count": without_tabs,
            "guidance": guidance,
        }
    return result


def _clear_paragraph_text(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    paragraphs = _paragraphs(session.doc.Text)
    targets = _paragraph_target_indices(paragraphs, {"indices": params["indices"]})
    cursors = [_select_paragraph(paragraphs[index]) for index in targets]
    for cursor in cursors:
        cursor.String = ""
    after = _paragraphs(session.doc.Text)
    result = {
        "indices": targets,
        "paragraph_count_before": len(paragraphs),
        "paragraph_count_after": len(after),
        "paragraph_details": [
            {
                "index": index,
                "text_length": len(str(after[index].String)) if index < len(after) else None,
            }
            for index in targets
        ],
    }
    if len(after) != len(paragraphs) or any(
        detail["text_length"] != 0 for detail in result["paragraph_details"]
    ):
        raise AdapterError(
            "VERIFICATION_FAILED",
            "native paragraph clearing did not leave every selected paragraph empty "
            "with paragraph boundaries preserved",
            result,
        )
    return result


def _replace_paragraph_text(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    index = int(params["index"])
    replacements = list(params["paragraphs"])
    blank_between = int(params.get("blank_paragraphs_between", 0))
    paragraphs = _paragraphs(session.doc.Text)
    if index >= len(paragraphs):
        raise AdapterError(
            "PARAGRAPH_NOT_FOUND", "paragraph index is out of range", http_status=404
        )
    paragraph = paragraphs[index]
    text = paragraph.getText()
    cursor = text.createTextCursorByRange(paragraph.getStart())
    cursor.gotoRange(paragraph.getEnd(), True)
    cursor.String = ""
    text.insertString(cursor, replacements[0], False)
    for replacement in replacements[1:]:
        for _ in range(blank_between + 1):
            text.insertControlCharacter(cursor, 0, False)
        text.insertString(cursor, replacement, False)
    return {
        "paragraph_index": index,
        "paragraphs": replacements,
        "replacement_count": len(replacements),
        "blank_paragraphs_between": blank_between,
    }


def _split_paragraph(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    index = int(params["index"])
    after_text = params["after_text"]
    anchors = [after_text] if isinstance(after_text, str) else after_text
    blank_between = int(params.get("blank_paragraphs_between", 0))
    paragraphs = _paragraphs(session.doc.Text)
    if index >= len(paragraphs):
        raise AdapterError(
            "PARAGRAPH_NOT_FOUND", "paragraph index is out of range", http_status=404
        )
    paragraph = paragraphs[index]
    original_text = str(paragraph.String)
    boundaries = []
    cursors = []
    expected = []
    search_start = 0
    for anchor_index, anchor in enumerate(anchors):
        start = original_text.find(anchor, search_start)
        if start < 0:
            raise AdapterError(
                "TEXT_NOT_FOUND",
                "after_text anchor was not found at or after the preceding boundary; "
                "check the exact literal and its order. No paragraph breaks were inserted",
                {
                    "index": index,
                    "after_text": after_text,
                    "anchor_index": anchor_index,
                    "search_start_offset": search_start,
                },
                404,
            )
        split_offset = start + len(anchor)
        cursor = _explicit_range(
            paragraph, start_offset=start, end_offset=split_offset, expected_text=anchor
        )
        cursor.collapseToEnd()
        cursors.append(cursor)
        boundaries.append(
            {
                "after_text": anchor,
                "split_offset": split_offset,
                "right_paragraph_index": index
                + (anchor_index + 1) * (blank_between + 1),
            }
        )
        expected.extend(
            [original_text[search_start:split_offset], *([""] * blank_between)]
        )
        search_start = split_offset
    expected.append(original_text[search_start:])

    # Resolve every range before editing, then preserve earlier offsets by working back.
    text = paragraph.getText()
    for cursor in reversed(cursors):
        for _ in range(blank_between + 1):
            text.insertControlCharacter(cursor, 0, False)
    after = _paragraphs(session.doc.Text)
    added_paragraphs = len(anchors) * (blank_between + 1)
    right_index = index + added_paragraphs
    observed = [str(item.String) for item in after[index : right_index + 1]]
    if len(after) != len(paragraphs) + added_paragraphs or observed != expected:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "native paragraph split did not preserve the selected text",
            {
                "paragraph_index": index,
                "boundaries": boundaries,
                "paragraphs": observed,
            },
        )
    result = {
        "paragraph_index": index,
        "after_text": after_text,
        "boundaries": boundaries,
        "blank_paragraphs_between": blank_between,
        "right_paragraph_index": right_index,
        "paragraphs": observed,
        "text_unchanged": True,
    }
    if len(boundaries) == 1:
        result["split_offset"] = boundaries[0]["split_offset"]
    return result


def _find_replace(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    descriptor = session.doc.createReplaceDescriptor()
    descriptor.SearchString = params["find"]
    descriptor.ReplaceString = params["replacement"]
    descriptor.SearchCaseSensitive = bool(params["case_sensitive"])
    descriptor.SearchRegularExpression = False
    if params["replace_all"] and "\r" in params["replacement"]:
        # Replace descriptors embed CR literally; range assignment creates paragraphs.
        matches = session.doc.findAll(descriptor)
        replaced = int(matches.getCount())
        for index in range(replaced - 1, -1, -1):
            matches.getByIndex(index).String = params["replacement"]
    elif params["replace_all"]:
        replaced = int(session.doc.replaceAll(descriptor))
    else:
        match = session.doc.findFirst(descriptor)
        replaced = 0
        if match is not None:
            match.String = params["replacement"]
            replaced = 1
    if replaced == 0:
        raise AdapterError(
            "TEXT_NOT_FOUND",
            f"literal text was not found: {params['find']}",
            http_status=404,
        )
    return {
        "find": params["find"],
        "replacement": params["replacement"],
        "replace_all": bool(params["replace_all"]),
        "case_sensitive": bool(params["case_sensitive"]),
        "replacement_count": replaced,
    }


def _convert_text_to_table(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    start, end = params["start_index"], params["end_index"]
    delimiter = params["delimiter"]
    paragraphs = _paragraphs(session.doc.Text)
    if end >= len(paragraphs):
        raise AdapterError(
            "PARAGRAPH_NOT_FOUND", "paragraph range is out of bounds",
            {"paragraph_count": len(paragraphs), "start_index": start, "end_index": end},
            404,
        )
    # Raw paragraph indices omit tables; the native selection must not enclose one.
    enumeration = session.doc.Text.createEnumeration()
    paragraph_index = -1
    selection_ends_body = False
    while enumeration.hasMoreElements():
        element = enumeration.nextElement()
        if element.supportsService("com.sun.star.text.Paragraph"):
            paragraph_index += 1
            selection_ends_body = paragraph_index == end
        else:
            selection_ends_body = False
            if start <= paragraph_index < end:
                raise AdapterError(
                    "UNSUPPORTED_OPERATION",
                    "selected paragraph range contains a table or other non-paragraph content",
                    {"start_index": start, "end_index": end},
                )
    before_text = [str(paragraph.String) for paragraph in paragraphs]
    source = before_text[start : end + 1]
    expected = [text.split(delimiter) for text in source]
    widths = [len(row) for row in expected]
    if len(set(widths)) != 1:
        raise AdapterError(
            "INVALID_REQUEST",
            "selected paragraphs have different cell counts for the supplied delimiter; "
            "choose a rectangular paragraph range",
            {"start_index": start, "end_index": end, "column_counts": widths},
        )
    before_tables = {str(table.Name) for table in _tables(session.doc)}
    selection = session.doc.Text.createTextCursorByRange(paragraphs[start].getStart())
    selection.gotoRange(paragraphs[end].getEnd(), True)
    controller = session.doc.getCurrentController()
    if controller is None or not controller.select(selection):
        raise AdapterError(
            "LIBREOFFICE_NOT_READY", "Writer could not select the requested paragraph range"
        )
    session.dispatch(".uno:ConvertTextToTable", (_property("Delimiter", delimiter),))
    after_tables = _tables(session.doc)
    after_names = {str(table.Name) for table in after_tables}
    created = [table for table in after_tables if str(table.Name) not in before_tables]
    if len(after_tables) != len(before_tables) + 1 or len(created) != 1 or not (
        before_tables <= after_names
    ):
        raise AdapterError(
            "VERIFICATION_FAILED", "native text conversion did not create exactly one table",
            {"table_count_before": len(before_tables), "table_count_after": len(after_tables)},
        )
    table = created[0]
    rows, columns = int(table.Rows.Count), int(table.Columns.Count)
    actual = [
        [str(table.getCellByPosition(column, row).String) for column in range(columns)]
        for row in range(rows)
    ]
    outside = before_text[:start] + before_text[end + 1 :]
    after_text = [str(paragraph.String) for paragraph in _paragraphs(session.doc.Text)]
    outside_text_unchanged = after_text == outside
    if selection_ends_body and after_text == outside + [""]:
        # Writer keeps one empty body paragraph after a table converted at document end.
        # Accept only that native tail, while preserving every original outside paragraph.
        enumeration = session.doc.Text.createEnumeration()
        penultimate = terminal = None
        while enumeration.hasMoreElements():
            penultimate, terminal = terminal, enumeration.nextElement()
        outside_text_unchanged = bool(
            penultimate is not None
            and penultimate.supportsService("com.sun.star.text.TextTable")
            and str(penultimate.Name) == str(table.Name)
            and terminal.supportsService("com.sun.star.text.Paragraph")
            and str(terminal.String) == ""
        )
    result = {
        "name": str(table.Name),
        "start_index": start,
        "end_index": end,
        "delimiter": delimiter,
        "rows": rows,
        "columns": columns,
        "source_text_char_count": sum(len(text) for text in source),
        "text_preserved": actual == expected and outside_text_unchanged,
    }
    if not result["text_preserved"]:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "native conversion did not preserve the exact source cell text and outside paragraphs",
            result | {
                "cell_text_matches": actual == expected,
                "outside_text_unchanged": outside_text_unchanged,
                "expected_rows": len(expected),
                "expected_columns": widths[0],
            },
        )
    return result


def _insert_table_at_cursor(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    rows = int(params["rows"])
    columns = int(params["columns"])
    table = session.doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(rows, columns)
    cursor = session.view_cursor()
    cursor_text = cursor.getText()
    forced_last_paragraph = bool(params.get("fallback_to_last_paragraph"))
    used_cursor_fallback = forced_last_paragraph or cursor_text != session.doc.Text
    if forced_last_paragraph:
        paragraphs = _paragraphs(session.doc.Text)
        anchor = paragraphs[-1].getStart() if paragraphs else session.doc.Text.getEnd()
    elif used_cursor_fallback:
        anchor = session.doc.Text.getEnd()
    else:
        anchor = cursor
    anchor.getText().insertTextContent(anchor, table, False)
    return {
        "name": str(table.Name),
        "rows": rows,
        "columns": columns,
        "cursor_fallback": used_cursor_fallback,
    }


def _table_cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def _find_identical_table(doc: Any, rows: list[list[Any]]) -> Any | None:
    expected = [_table_cell_text(value) for row in rows for value in row]
    for table in _tables(doc):
        names = _cell_names(table)
        if len(names) != len(expected):
            continue
        actual = [str(table.getCellByName(name).String) for name in names]
        if actual == expected:
            return table
    return None


def _insert_table_after_text(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    anchor_text = str(params["anchor_text"]).strip()
    match_mode = str(params.get("match_mode", "exact"))
    case_sensitive = bool(params.get("case_sensitive", False))
    wanted = anchor_text if case_sensitive else anchor_text.casefold()
    paragraphs = _paragraphs(session.doc.Text)

    def matches(paragraph: Any) -> bool:
        candidate = str(paragraph.String).strip()
        candidate = candidate if case_sensitive else candidate.casefold()
        return candidate == wanted if match_mode == "exact" else wanted in candidate

    matching_indices = [
        index for index, paragraph in enumerate(paragraphs) if matches(paragraph)
    ]
    if not matching_indices:
        raise AdapterError(
            "TEXT_NOT_FOUND",
            "no body paragraph matched params.anchor_text",
            {
                "anchor_text": anchor_text,
                "match_mode": match_mode,
                "case_sensitive": case_sensitive,
                "paragraph_count": len(paragraphs),
                "paragraph_preview": [
                    str(item.String)[:160] for item in paragraphs[:40]
                ],
            },
            404,
        )
    if len(matching_indices) != 1:
        raise AdapterError(
            "TEXT_NOT_UNIQUE",
            "params.anchor_text matched more than one body paragraph",
            {
                "anchor_text": anchor_text,
                "match_mode": match_mode,
                "case_sensitive": case_sensitive,
                "paragraph_numbers": [index + 1 for index in matching_indices],
            },
            422,
        )

    anchor_index = matching_indices[0]
    rows = params["rows"]
    column_count = len(rows[0])
    existing = _find_identical_table(session.doc, rows)
    if existing is not None:
        return {
            "name": str(existing.Name),
            "rows": len(rows),
            "columns": column_count,
            "anchor_text": anchor_text,
            "anchor_paragraph_number": anchor_index + 1,
            "match_mode": match_mode,
            "case_sensitive": case_sensitive,
            "display_text": [
                [_table_cell_text(value) for value in row] for row in rows
            ],
            "changed": False,
            "duplicate": True,
        }
    insertion_range = (
        paragraphs[anchor_index + 1].getStart()
        if anchor_index + 1 < len(paragraphs)
        else session.doc.Text.getEnd()
    )
    table = session.doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(len(rows), column_count)
    insertion_range.getText().insertTextContent(insertion_range, table, False)
    names = _cell_names(table)
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            name = names[row_index * column_count + column_index]
            table.getCellByName(name).String = _table_cell_text(value)
    return {
        "name": str(table.Name),
        "rows": len(rows),
        "columns": column_count,
        "anchor_text": anchor_text,
        "anchor_paragraph_number": anchor_index + 1,
        "match_mode": match_mode,
        "case_sensitive": case_sensitive,
        "display_text": [[_table_cell_text(value) for value in row] for row in rows],
        "changed": True,
        "duplicate": False,
    }


def _table_cell_snapshot(name: str, cell: Any) -> dict[str, Any]:
    snapshot = {
        "name": name,
        "text": str(cell.String),
        "font_color": None,
    }
    coordinate = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", name)
    if coordinate:
        column_index = 0
        for letter in coordinate.group(1):
            column_index = column_index * 26 + ord(letter) - ord("A") + 1
        snapshot["row_index"] = int(coordinate.group(2))
        snapshot["column_index"] = column_index
    try:
        cursor = _whole_text_cursor(cell.Text)
        state = cursor.getPropertyState("CharColor")
        if state.value == "AMBIGUOUS_VALUE":
            snapshot["font_color"] = "mixed"
        else:
            color = cursor.CharColor
            if isinstance(color, int) and not isinstance(color, bool):
                if color == -1:
                    snapshot["font_color"] = "automatic"
                elif 0 <= color <= 0xFFFFFF:
                    snapshot["font_color"] = f"#{color:06X}"
    except Exception:
        # Unavailable formatting must not hide otherwise readable cell text.
        pass
    return snapshot


def _read_table(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    table = _named_table(session.doc, params["name"])
    cells = [
        _table_cell_snapshot(name, table.getCellByName(name))
        for name in _cell_names(table)
    ]
    return {
        "name": str(table.Name),
        "rows": int(table.Rows.Count),
        "columns": int(table.Columns.Count),
        "cells": cells,
    }


def _set_table_cell_text_color(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    table = _named_table(session.doc, params["name"])
    available = set(_cell_names(table))
    requested = list(params["cells"])
    missing = [name for name in requested if name not in available]
    if missing:
        raise AdapterError(
            "CELL_NOT_FOUND",
            "one or more table cells do not exist",
            {"table": params["name"], "cells": missing},
            404,
        )
    color = parse_rgb_color(params["color"], "params.color")
    for name in requested:
        _whole_text_cursor(table.getCellByName(name).Text).CharColor = color
    return {
        "name": str(table.Name),
        "cells": [
            {"name": name, "text": str(table.getCellByName(name).String)}
            for name in requested
        ],
        "color": color,
        "cells_changed": len(set(requested)),
    }


def _insert_image_at_cursor(
    session: WriterSession, params: dict[str, Any]
) -> dict[str, Any]:
    path = Path(params["path"]).expanduser()
    if not path.is_file():
        raise AdapterError(
            "FILE_NOT_FOUND", f"image file does not exist: {path}", http_status=404
        )
    before = _graphic_object_count(session.doc)
    image = session.doc.createInstance("com.sun.star.text.TextGraphicObject")
    image.GraphicURL = _file_url(str(path))
    image.AnchorType = 0
    cursor = session.view_cursor()
    cursor.getText().insertTextContent(cursor, image, False)
    after = _graphic_object_count(session.doc)
    added = after - before if before is not None and after is not None else None
    if added is not None and added != 1:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "Writer did not report exactly one newly inserted graphic object",
            {
                "graphic_object_count_before": before,
                "graphic_object_count_after": after,
                "graphic_objects_added": added,
            },
            422,
        )
    return {
        "path": str(path),
        "inserted": True,
        "anchor": "as_character",
        "graphic_object_count_before": before,
        "graphic_object_count_after": after,
        "graphic_objects_added": added,
        "count_verified": added == 1,
    }


def _read_default_font(session: WriterSession) -> str:
    provider = session.service_manager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", session.context
    )
    access = provider.createInstanceWithArguments(
        "com.sun.star.configuration.ConfigurationAccess",
        (_property("nodepath", "/org.openoffice.Office.Writer/DefaultFont"),),
    )
    return str(access.getPropertyValue("Standard"))


def _set_default_font(session: WriterSession, params: dict[str, Any]) -> dict[str, Any]:
    font_name = params["font_name"]
    provider = session.service_manager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", session.context
    )
    access = provider.createInstanceWithArguments(
        "com.sun.star.configuration.ConfigurationUpdateAccess",
        (_property("nodepath", "/org.openoffice.Office.Writer/DefaultFont"),),
    )
    access.setPropertyValue("Standard", font_name)
    access.commitChanges()
    observed = _read_default_font(session)
    if observed != font_name:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "Writer default font did not persist",
            {"expected": font_name, "observed": observed},
        )
    return {
        "font_name": observed,
        "nodepath": "/org.openoffice.Office.Writer/DefaultFont",
    }


GENERIC_ACTIONS = {
    "document.inspect": _inspect,
    "document.save": _save_action,
    "document.export_pdf": _export_pdf,
    "document.set_font": _set_font,
    "document.transform_case": _transform_case,
    "document.remove_highlighting": _remove_highlighting,
    "document.add_page_numbers": _add_page_numbers,
    "document.insert_page_break": _insert_page_break,
    "document.append_paragraphs": _append_paragraphs,
    "paragraph.set_format": _set_paragraph_format,
    "paragraph.clear_text": _clear_paragraph_text,
    "paragraph.apply_numbering": apply_paragraph_numbering,
    "paragraph.replace_text": _replace_paragraph_text,
    "paragraph.split": _split_paragraph,
    "bookmark.create": create_bookmark,
    "cross_reference.insert": insert_cross_reference,
    "text.find": find_text,
    "text.find_replace": _find_replace,
    "text.set_format": set_text_format,
    "table.read": _read_table,
    "table.convert_text": _convert_text_to_table,
    "table.insert_at_cursor": _insert_table_at_cursor,
    "table.insert_after_text": _insert_table_after_text,
    "table.set_cell_text_color": _set_table_cell_text_color,
    "image.insert_at_cursor": _insert_image_at_cursor,
    "settings.set_default_font": _set_default_font,
}

NO_AUTO_SAVE_ACTIONS = frozenset(
    {
        "document.inspect",
        "document.save",
        "document.export_pdf",
        "settings.set_default_font",
        "text.find",
    }
)


def _observed(session: WriterSession, check: dict[str, Any]) -> Any:
    kind = check["type"]
    if kind == "document_identity":
        return session.identity()
    if kind == "file_saved":
        return _saved_file_state(session.path)
    if kind == "paragraphs":
        return [paragraph.String for paragraph in _paragraphs(session.doc.Text)]
    if kind == "tables":
        return [
            {"rows": int(table.Rows.Count), "columns": int(table.Columns.Count)}
            for table in _tables(session.doc)
        ]
    if kind == "images":
        return _docx_image_count(session.path) if session.path else 0
    if kind == "page_breaks":
        return _docx_page_break_count(session.path) if session.path else 0
    if kind == "pdf":
        return _saved_file_state(Path(check["path"]).expanduser())
    if kind == "default_font":
        return _read_default_font(session)
    if kind in {"text_format", "page_numbers"}:
        return _inspect(session, {})
    raise AdapterError("UNSUPPORTED_OPERATION", f"unsupported verifier: {kind}")


def _equivalent(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(
            key in actual and _equivalent(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list) and isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _equivalent(a, b) for a, b in zip(actual, expected)
        )
    return actual == expected


def _verify_requested(
    session: WriterSession, checks: list[dict[str, Any]]
) -> dict[str, Any]:
    results = []
    observed = {}
    expected = {}
    passed = True
    for index, check in enumerate(checks):
        actual = _observed(session, check)
        wanted = check.get("expected")
        ok = wanted is None or _equivalent(actual, wanted)
        passed = passed and ok
        results.append({"index": index, "type": check["type"], "passed": ok})
        observed[str(index)] = actual
        expected[str(index)] = wanted
    verification = _verification(passed, results, observed, expected)
    if checks and all(check["type"] == "default_font" for check in checks):
        verification["scope"] = "application_settings"
    return verification


def _implicit_action_verification(
    action: str,
    session: WriterSession,
    result: dict[str, Any],
) -> dict[str, Any]:
    if action == "settings.set_default_font":
        return _verify_requested(
            session, [{"type": "default_font", "expected": result["font_name"]}]
        )
    if action in {"document.export_pdf", "document.export_file_pdf"}:
        expected = {"exists": True, "valid": True, "pdf_header": True}
        passed = all(result.get(key) == value for key, value in expected.items())
        return _verification(
            passed,
            [{"type": "pdf", "passed": passed}],
            result,
            expected,
        )
    state = _saved_file_state(session.path)
    passed = state["exists"] and state["valid"]
    return _verification(
        passed,
        [{"type": "file_saved", "passed": passed}],
        state,
        {"exists": True, "valid": True},
    )


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "document.export_file_pdf":
        session = WriterSession({}, allow_no_document=True)
        result = _export_file_pdf(session, payload.get("params") or {})
        return {
            "result": result,
            "verification": _implicit_action_verification(action, session, result),
            "logs": [],
        }
    if action == "document.read_file":
        session = WriterSession({}, allow_no_document=True)
        result = _read_file(session, payload.get("params") or {})
        return {
            "result": result,
            "verification": _verification(
                True,
                [{"type": "document_text_read", "passed": True}],
                {key: value for key, value in result.items() if key != "text"},
                {},
            ),
            "logs": [],
        }
    if action not in GENERIC_ACTIONS:
        if action != "document.extract_images":
            raise AdapterError("UNSUPPORTED_OPERATION", f"unsupported action: {action}")
    if action == "document.extract_images":
        started = time.monotonic()
        result = extract_document_images(payload.get("params") or {})
        checks = [
            {
                "type": "extracted_image",
                "path": image["output_path"],
                "sha256": image["sha256"],
                "passed": True,
            }
            for image in result["images"]
        ]
        return {
            "result": result,
            "verification": {
                "passed": bool(checks),
                "checks": checks,
                "observed_state": {"images": result["images"]},
                "expected_state": {
                    "extracted_count": result["extracted_count"],
                    "content_matches_embedded_members": True,
                },
            },
            "logs": [
                {
                    "level": "info",
                    "message": (
                        "document.extract_images completed in "
                        f"{round((time.monotonic() - started) * 1000)} ms"
                    ),
                }
            ],
        }
    session = WriterSession(payload.get("document") or {})
    started = time.monotonic()
    result = GENERIC_ACTIONS[action](session, payload.get("params") or {})
    if action not in NO_AUTO_SAVE_ACTIONS:
        result = {**result, "saved": session.save()}
    verification = _verify_requested(session, payload.get("verify") or [])
    if not payload.get("verify"):
        verification = _implicit_action_verification(action, session, result)
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
