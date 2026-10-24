from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import zipfile
from collections import defaultdict, deque
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .errors import AdapterError, error_payload
from .export_contract import validate_export_destination
from .geometry_contract import (
    edge_aligned_position,
    resolve_optional_shape_geometry,
    resolve_shape_geometry,
    validate_atomic_geometry_params,
)
from .image_contract import validate_image_path_suffixes
from .speaker_notes import set_speaker_notes, speaker_notes_text
from .slide_reference import require_slide_index
from .table_contract import is_empty_content_placeholder, may_use_content_placeholder
from .table_row_contract import replace_live_table_row, select_unique_live_table
from .text_roles import iter_shapes_for_roles, normalize_roles


# Impress' Insert Table dialog creates empty rows at 0.399 inches (1013 in
# LibreOffice's 1/100 mm coordinates). Keeping this default matters when a
# table replaces a taller content placeholder: the native UI does not stretch
# the table to the placeholder's full height.
DEFAULT_TABLE_ROW_HEIGHT = 1013


def _uno_modules():
    try:
        import uno
        from com.sun.star.beans import PropertyValue
    except ImportError as exc:
        raise AdapterError(
            "UNO_CONNECT_FAILED", "python3-uno is not available", str(exc), 503
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


def _path_from_url(url: str) -> Path | None:
    if not url:
        return None
    parsed = urlparse(url)
    if (
        parsed.scheme.casefold() != "file"
        or parsed.netloc.casefold() not in {"", "localhost"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or not unquote(parsed.path).startswith("/")
    ):
        return None
    return Path(unquote(parsed.path))


def _path_from_input(path_or_url: str) -> Path:
    """Convert a local path or encoded file URL to a system path exactly once."""
    if urlparse(path_or_url).scheme.casefold() == "file":
        path = _path_from_url(path_or_url)
        if path is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "file URL must reference the local host without params, query, or fragment",
                {"path": path_or_url},
            )
        return path.expanduser()
    parsed = urlparse(path_or_url)
    if parsed.scheme:
        raise AdapterError(
            "INVALID_REQUEST", "only local paths and file URLs are supported"
        )
    return Path(path_or_url).expanduser()


def _enum(type_name: str, value: str):
    uno, _ = _uno_modules()
    return uno.Enum(type_name, value)


def _enum_name(value: Any) -> str:
    """Return the stable symbolic part of a pyuno enum representation."""
    text = str(value)
    if "(" in text and "'" in text:
        return text.rsplit("'", 2)[-2]
    return text.rsplit(".", 1)[-1]


def _alignment_name(value: Any) -> str | None:
    name = _enum_name(getattr(value, "value", value)).casefold()
    return {
        "0": "left",
        "1": "right",
        "2": "justify",
        "3": "center",
        "4": "stretch",
        "left": "left",
        "right": "right",
        "block": "justify",
        "center": "center",
        "stretch": "stretch",
    }.get(name)


def _color(value: Any) -> int:
    if isinstance(value, bool):
        raise AdapterError("INVALID_REQUEST", "color cannot be boolean")
    if isinstance(value, int) and 0 <= value <= 0xFFFFFF:
        return value
    if isinstance(value, str):
        names = {
            "black": 0x000000,
            "white": 0xFFFFFF,
            "red": 0xFF0000,
            # LibreOffice standard palette values used by the guest UI.
            "green": 0x00A933,
            "blue": 0x0000FF,
            "yellow": 0xFFFF00,
            "orange": 0xFF8000,
            "purple": 0x800080,
            "gray": 0x808080,
            "grey": 0x808080,
            "cyan": 0x00FFFF,
            "magenta": 0xFF00FF,
            "dark red 2": 0xC9211E,
        }
        raw = " ".join(value.casefold().split()).removeprefix("#")
        if raw in names:
            return names[raw]
        if len(raw) == 6:
            try:
                return int(raw, 16)
            except ValueError:
                pass
    raise AdapterError(
        "INVALID_REQUEST", "color must be a named color, #RRGGBB, or RGB integer"
    )


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


class ImpressSession:
    def __init__(self, selector: dict[str, Any]) -> None:
        uno, _ = _uno_modules()
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local
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
        self.doc = self._select_document(selector)

    def _documents(self) -> list[Any]:
        result = []
        enum = self.desktop.getComponents().createEnumeration()
        while enum.hasMoreElements():
            component = enum.nextElement()
            try:
                if component.supportsService(
                    "com.sun.star.presentation.PresentationDocument"
                ):
                    result.append(component)
            except Exception:
                continue
        return result

    def identity(self, doc: Any | None = None) -> dict[str, str]:
        doc = doc or self.doc
        url = str(getattr(doc, "URL", "") or "")
        title = str(getattr(doc, "Title", "") or "")
        if not title:
            path = _path_from_url(url)
            title = path.name if path else ""
        return {"url": url, "title": title}

    def _select_document(self, selector: dict[str, Any]) -> Any:
        documents = self._documents()
        requested_url = selector.get("url")
        requested_title = selector.get("title")
        if requested_url:
            requested_url = _file_url(str(requested_url))
        matches = []
        for doc in documents:
            identity = self.identity(doc)
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
                    "failed to open requested Impress document",
                    {"url": requested_url, "error": str(exc)},
                    422,
                ) from exc
            if loaded is None or not loaded.supportsService(
                "com.sun.star.presentation.PresentationDocument"
            ):
                if loaded is not None:
                    try:
                        loaded.close(True)
                    except Exception:
                        loaded.dispose()
                raise AdapterError(
                    "DOCUMENT_OPEN_FAILED",
                    "requested file did not open as an Impress document",
                    {"url": requested_url},
                    422,
                )
            loaded_identity = self.identity(loaded)
            if requested_title and loaded_identity["title"] != requested_title:
                try:
                    loaded.close(True)
                except Exception:
                    loaded.dispose()
                raise AdapterError(
                    "DOCUMENT_MISMATCH",
                    "opened Impress document does not match the requested title",
                    {"selector": selector, "opened_document": loaded_identity},
                    404,
                )
            return loaded
        if not documents:
            raise AdapterError(
                "NO_IMPRESS_DOCUMENT",
                "no open Impress document was found",
                http_status=404,
            )
        if requested_url or requested_title:
            if not matches:
                raise AdapterError(
                    "DOCUMENT_MISMATCH",
                    "no open Impress document matches selector",
                    {
                        "selector": selector,
                        "open_documents": [self.identity(doc) for doc in documents],
                    },
                    404,
                )
        elif len(documents) != 1:
            raise AdapterError(
                "DOCUMENT_AMBIGUOUS",
                "document selector is required when multiple Impress documents are open",
                {"open_documents": [self.identity(doc) for doc in documents]},
                409,
            )
        else:
            matches = documents
        if len(matches) != 1:
            raise AdapterError(
                "DOCUMENT_AMBIGUOUS",
                "document selector did not identify one Impress document",
                {"matches": [self.identity(doc) for doc in matches]},
                409,
            )
        return matches[0]

    @property
    def pages(self) -> Any:
        return self.doc.getDrawPages()

    def page(self, index: int) -> Any:
        if index < 0 or index >= self.pages.getCount():
            raise AdapterError(
                "SLIDE_NOT_FOUND", f"slide index out of range: {index}", http_status=404
            )
        return self.pages.getByIndex(index)

    def master_page(self, index: int = 0) -> Any:
        masters = self.doc.getMasterPages()
        if index < 0 or index >= masters.getCount():
            raise AdapterError(
                "MASTER_NOT_FOUND",
                f"master page index out of range: {index}",
                http_status=404,
            )
        return masters.getByIndex(index)

    def shape(self, page: Any, selector: dict[str, Any]) -> Any:
        shapes = [page.getByIndex(i) for i in range(page.getCount())]
        if "path" in selector:
            path = selector["path"]
            candidate = page
            for depth, index in enumerate(path):
                try:
                    candidate = candidate.getByIndex(index)
                except Exception as exc:
                    raise AdapterError(
                        "SHAPE_NOT_FOUND",
                        f"shape path is invalid at depth {depth}: {path}",
                        http_status=404,
                    ) from exc
            if any(
                key in selector for key in ("name", "text", "kind")
            ) and not self._matches(candidate, selector):
                raise AdapterError(
                    "SHAPE_MISMATCH",
                    "shape path does not match selector",
                    http_status=409,
                )
            return candidate
        if "index" in selector:
            index = selector["index"]
            if index >= len(shapes):
                raise AdapterError(
                    "SHAPE_NOT_FOUND",
                    f"shape index out of range: {index}",
                    http_status=404,
                )
            candidate = shapes[index]
            if any(
                key in selector for key in ("name", "text", "kind")
            ) and not self._matches(candidate, selector):
                raise AdapterError(
                    "SHAPE_MISMATCH",
                    "shape index does not match selector",
                    http_status=409,
                )
            return candidate

        def descendants(container: Any):
            for index in range(container.getCount()):
                shape = container.getByIndex(index)
                yield shape
                if hasattr(shape, "getCount") and hasattr(shape, "getByIndex"):
                    yield from descendants(shape)

        matches = [
            shape for shape in descendants(page) if self._matches(shape, selector)
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise AdapterError(
                "SHAPE_NOT_FOUND",
                "no shape matches selector",
                {"selector": selector},
                404,
            )
        raise AdapterError(
            "SHAPE_AMBIGUOUS",
            "selector matches multiple shapes",
            {"selector": selector},
            409,
        )

    @staticmethod
    def _matches(shape: Any, selector: dict[str, Any]) -> bool:
        if "name" in selector and str(getattr(shape, "Name", "")) != selector["name"]:
            return False
        if "text" in selector:
            try:
                if str(shape.getText().getString()) != selector["text"]:
                    return False
            except Exception:
                return False
        if "kind" in selector:
            kind = str(
                getattr(shape, "ShapeType", "")
                or getattr(shape, "ImplementationName", "")
            )
            if selector["kind"].lower() not in kind.lower():
                return False
        if any(key in selector for key in ("name", "text", "kind")):
            return True
        return False


def _shape_text(shape: Any) -> str:
    try:
        return str(shape.getText().getString())
    except Exception:
        return ""


def _text_property(shape: Any, name: str, fallback: Any = None) -> Any:
    try:
        text = shape.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        return cursor.getPropertyValue(name)
    except Exception:
        return getattr(shape, name, fallback)


def _paragraph_summaries(shape: Any) -> list[dict[str, Any]]:
    try:
        paragraphs = shape.getText().createEnumeration()
    except Exception:
        return []
    summaries = []
    index = 0
    while paragraphs.hasMoreElements():
        paragraph = paragraphs.nextElement()
        text = str(paragraph.getString())

        def read(name: str, fallback: Any) -> Any:
            try:
                value = paragraph.getPropertyValue(name)
                return fallback if value is None else value
            except Exception:
                return fallback

        summaries.append(
            {
                "index": index,
                "text": text,
                "bullet": bool(read("NumberingIsNumber", False)),
                "level": int(read("NumberingLevel", 0)),
                "left_margin": int(read("ParaLeftMargin", 0)),
                "first_line_indent": int(read("ParaFirstLineIndent", 0)),
            }
        )
        index += 1
    return summaries


def _resolve_paragraph_indent(
    paragraphs: list[dict[str, Any]],
    target_text: str,
    reference_texts: list[str],
    *,
    match_mode: str = "exact",
    case_sensitive: bool = False,
) -> dict[str, Any]:
    def normalize(value: str) -> str:
        collapsed = " ".join(value.split())
        return collapsed if case_sensitive else collapsed.casefold()

    def matches(actual: str, requested: str) -> bool:
        actual_value = normalize(actual)
        requested_value = normalize(requested)
        if match_mode == "contains":
            return requested_value in actual_value
        return actual_value == requested_value

    def unique_index(requested: str, role: str) -> int:
        indices = [
            index
            for index, paragraph in enumerate(paragraphs)
            if matches(str(paragraph.get("text", "")), requested)
        ]
        if not indices:
            raise AdapterError(
                "TEXT_NOT_FOUND",
                f"{role} paragraph was not found in the selected shape",
                {"text": requested, "match_mode": match_mode},
                404,
            )
        if len(indices) != 1:
            raise AdapterError(
                "TEXT_AMBIGUOUS",
                f"{role} paragraph matches multiple paragraphs",
                {"text": requested, "indices": indices, "match_mode": match_mode},
                409,
            )
        return indices[0]

    target_index = unique_index(target_text, "target")
    reference_indices = [
        unique_index(reference_text, "reference") for reference_text in reference_texts
    ]
    if target_index in reference_indices:
        raise AdapterError(
            "INVALID_REQUEST",
            "target_text and reference_texts must identify different paragraphs",
        )

    fields = ("level", "left_margin", "first_line_indent")
    reference_styles = [
        {field: int(paragraphs[index][field]) for field in fields}
        for index in reference_indices
    ]
    if any(style != reference_styles[0] for style in reference_styles[1:]):
        raise AdapterError(
            "REFERENCE_STYLE_CONFLICT",
            "reference paragraphs do not have the same indentation",
            {
                "reference_texts": reference_texts,
                "reference_indices": reference_indices,
                "styles": reference_styles,
            },
            409,
        )
    return {
        "target_index": target_index,
        "reference_indices": reference_indices,
        "indent": reference_styles[0],
    }


def _resolve_paragraph_indent_shape(
    candidates: list[tuple[list[int], list[dict[str, Any]]]],
    target_text: str,
    reference_texts: list[str],
    *,
    match_mode: str = "exact",
    case_sensitive: bool = False,
) -> dict[str, Any]:
    resolved = []
    diagnostic_errors: list[AdapterError] = []
    for path, paragraphs in candidates:
        try:
            plan = _resolve_paragraph_indent(
                paragraphs,
                target_text,
                reference_texts,
                match_mode=match_mode,
                case_sensitive=case_sensitive,
            )
        except AdapterError as exc:
            if exc.code != "TEXT_NOT_FOUND":
                diagnostic_errors.append(exc)
            continue
        resolved.append({"path": path, **plan})

    if len(resolved) == 1:
        return resolved[0]
    if len(resolved) > 1:
        raise AdapterError(
            "SHAPE_AMBIGUOUS",
            "paragraph texts identify multiple shapes on the selected slide",
            {"paths": [item["path"] for item in resolved]},
            409,
        )
    if len(diagnostic_errors) == 1:
        raise diagnostic_errors[0]
    if diagnostic_errors:
        raise AdapterError(
            "SHAPE_AMBIGUOUS",
            "paragraph texts match multiple invalid or conflicting shapes",
            {"errors": [error_payload(error) for error in diagnostic_errors]},
            409,
        )
    raise AdapterError(
        "TEXT_NOT_FOUND",
        "no shape on the selected slide contains the target and every reference paragraph",
        {"target_text": target_text, "reference_texts": reference_texts},
        404,
    )


def _shapes_with_paths(container: Any, prefix: list[int] | None = None):
    base = prefix or []
    for index in range(container.getCount()):
        shape = container.getByIndex(index)
        path = [*base, index]
        yield path, shape
        if hasattr(shape, "getCount") and hasattr(shape, "getByIndex"):
            yield from _shapes_with_paths(shape, path)


def _leaf_shapes_with_parents(container: Any, prefix: list[int] | None = None):
    base = prefix or []
    for index in range(container.getCount()):
        shape = container.getByIndex(index)
        path = [*base, index]
        child_count = 0
        if hasattr(shape, "getCount") and hasattr(shape, "getByIndex"):
            try:
                child_count = int(shape.getCount())
            except Exception:
                child_count = 0
        if child_count > 0:
            yield from _leaf_shapes_with_parents(shape, path)
        else:
            yield path, shape, container


def _shape_summary(shape: Any, index: int) -> dict[str, Any]:
    return _shape_summary_at_path(shape, [index])


def _shape_fill_style(shape: Any) -> str:
    try:
        value = getattr(shape, "FillStyle", None)
    except Exception:
        return ""
    if value is None:
        return ""
    return _enum_name(value).strip().lower()


def _shape_summary_at_path(shape: Any, path: list[int]) -> dict[str, Any]:
    pos = getattr(shape, "Position", None)
    size = getattr(shape, "Size", None)
    text = _shape_text(shape)
    summary = {
        "index": path[-1],
        "path": path,
        "name": str(getattr(shape, "Name", "") or ""),
        "kind": str(
            getattr(shape, "ShapeType", "") or getattr(shape, "ImplementationName", "")
        ),
        "text": text,
        "is_text": bool(text) or hasattr(shape, "getText"),
        "x": int(getattr(pos, "X", 0)),
        "y": int(getattr(pos, "Y", 0)),
        "width": int(getattr(size, "Width", 0)),
        "height": int(getattr(size, "Height", 0)),
        "visible": bool(getattr(shape, "Visible", True)),
    }
    fill_style = _shape_fill_style(shape)
    if fill_style:
        summary["fill_style"] = fill_style
    media_url = str(getattr(shape, "MediaURL", "") or "")
    if media_url:
        summary["media_url"] = media_url
    graphic_url = str(getattr(shape, "GraphicURL", "") or "")
    if graphic_url.startswith(("file://", "http://", "https://")):
        summary["graphic_url"] = graphic_url
    if summary["is_text"]:
        bold_weight = float(_text_property(shape, "CharWeight", 0.0))
        summary["text_style"] = {
            "color": int(_text_property(shape, "CharColor", -1)),
            "font_size": float(_text_property(shape, "CharHeight", 0.0)),
            "font_name": str(_text_property(shape, "CharFontName", "") or ""),
            "bold_weight": bold_weight,
            "bold": bold_weight >= 150.0 if bold_weight > 0 else None,
            "italic": _enum_name(_text_property(shape, "CharPosture", "NONE")),
            "underline": int(_text_property(shape, "CharUnderline", 0)),
            "strike": int(_text_property(shape, "CharStrikeout", 0)),
            "alignment": _alignment_name(getattr(shape, "ParaAdjust", None)),
        }
        summary["paragraphs"] = _paragraph_summaries(shape)
    if "tableshape" in summary["kind"].casefold():
        try:
            model = shape.Model
            rows, columns = _table_dimensions(model)
            summary["table"] = {
                "rows": rows,
                "columns": columns,
                "cells": [
                    [
                        str(model.getCellByPosition(column, row).String)
                        for column in range(columns)
                    ]
                    for row in range(rows)
                ],
            }
        except Exception:
            pass
    try:
        child_count = shape.getCount()
    except Exception:
        child_count = 0
    if child_count:
        summary["children"] = [
            _shape_summary_at_path(shape.getByIndex(child_index), [*path, child_index])
            for child_index in range(child_count)
        ]
    return summary


def _graphic_descendant_count(shape: Any) -> int:
    count = int(
        "graphicobjectshape"
        in str(
            getattr(shape, "ShapeType", "") or getattr(shape, "ImplementationName", "")
        ).casefold()
    )
    try:
        child_count = shape.getCount()
    except Exception:
        child_count = 0
    return count + sum(
        _graphic_descendant_count(shape.getByIndex(index))
        for index in range(child_count)
    )


def _bitmap_fill_descendant_count(shape: Any) -> int:
    count = int(_shape_fill_style(shape) == "bitmap")
    try:
        child_count = shape.getCount()
    except Exception:
        child_count = 0
    return count + sum(
        _bitmap_fill_descendant_count(shape.getByIndex(index))
        for index in range(child_count)
    )


def _top_level_picture_containers(page: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index in range(page.getCount()):
        shape = page.getByIndex(index)
        graphic_count = _graphic_descendant_count(shape)
        bitmap_fill_count = _bitmap_fill_descendant_count(shape)
        if not graphic_count and not bitmap_fill_count:
            continue
        summary = _shape_summary_at_path(shape, [index])
        summary["graphic_count"] = graphic_count
        summary["bitmap_fill_count"] = bitmap_fill_count
        summary.pop("children", None)
        candidates.append(summary)
    return candidates


def _page_summary(session: ImpressSession, index: int) -> dict[str, Any]:
    page = session.page(index)
    notes = page.getNotesPage()
    return {
        "index": index,
        "width": int(page.Width),
        "height": int(page.Height),
        "orientation": _enum_name(page.Orientation).lower(),
        "background": _background_summary(page),
        "transition": {
            "effect": _enum_name(page.Effect),
            "type": int(page.TransitionType),
            "duration": float(page.TransitionDuration),
        },
        "notes": speaker_notes_text(notes),
        "shapes": [
            _shape_summary(page.getByIndex(i), i) for i in range(page.getCount())
        ],
    }


def _background_summary(page: Any) -> dict[str, Any]:
    try:
        fill = page.getPropertyValue("Background")
        if fill is None:
            return {"style": "none"}
        style = _enum_name(fill.FillStyle).lower()
        return {"style": style, "color": int(getattr(fill, "FillColor", 0))}
    except Exception:
        return {"style": "unknown"}


def _persist_pptx_transitions(path: Path, pages: Any) -> None:
    """Persist page effects that LibreOffice 7.3 drops in its PPTX filter.

    UNO remains the source of truth. This narrow OOXML fallback is needed for
    saved PPTX state because the guest's exporter omits ``p:transition`` even
    though ``DrawPage.Effect`` is set correctly.
    """
    if (
        path.suffix.lower() != ".pptx"
        or not path.is_file()
        or not zipfile.is_zipfile(path)
    ):
        return
    p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ET.register_namespace("p", p_ns)
    with tempfile.TemporaryDirectory(prefix="osworld-impress-pptx-") as temp_dir:
        temp_path = Path(temp_dir) / path.name
        with (
            zipfile.ZipFile(path, "r") as source,
            zipfile.ZipFile(temp_path, "w") as target,
        ):
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename.startswith(
                    "ppt/slides/slide"
                ) and info.filename.endswith(".xml"):
                    try:
                        index = int(Path(info.filename).stem.removeprefix("slide")) - 1
                        effect = _enum_name(pages.getByIndex(index).Effect).lower()
                        if effect != "none":
                            root = ET.fromstring(data)
                            for child in list(root):
                                if child.tag.rsplit("}", 1)[-1] == "transition":
                                    root.remove(child)
                            transition = ET.Element(f"{{{p_ns}}}transition")
                            element = {
                                "dissolve": "dissolve",
                                "fade_from_right": "fade",
                            }.get(effect, effect)
                            transition.append(
                                ET.SubElement(transition, f"{{{p_ns}}}{element}")
                            )
                            root.append(transition)
                            data = ET.tostring(
                                root, encoding="utf-8", xml_declaration=True
                            )
                    except (ValueError, ET.ParseError, IndexError, AttributeError):
                        pass
                target.writestr(info, data)
        shutil.move(str(temp_path), str(path))


def _persist_pptx_media(path: Path) -> None:
    """Embed audio files referenced by UNO MediaShape external relationships."""
    if (
        path.suffix.lower() != ".pptx"
        or not path.is_file()
        or not zipfile.is_zipfile(path)
    ):
        return
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    content_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    ET.register_namespace("", rel_ns)
    with tempfile.TemporaryDirectory(prefix="osworld-impress-media-") as temp_dir:
        temp_path = Path(temp_dir) / path.name
        additions: dict[str, bytes] = {}
        extensions: set[str] = set()
        target_cache: dict[str, str] = {}
        with (
            zipfile.ZipFile(path, "r") as source,
            zipfile.ZipFile(temp_path, "w") as target,
        ):
            existing = set(source.namelist())
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename.startswith(
                    "ppt/slides/_rels/"
                ) and info.filename.endswith(".rels"):
                    try:
                        root = ET.fromstring(data)
                        changed = False
                        for relationship in root.findall(f"{{{rel_ns}}}Relationship"):
                            kind = relationship.get("Type", "").rsplit("/", 1)[-1]
                            external = relationship.get("TargetMode") == "External"
                            source_path = _path_from_url(relationship.get("Target", ""))
                            if (
                                kind not in {"audio", "media"}
                                or not external
                                or not source_path
                                or not source_path.is_file()
                            ):
                                continue
                            cache_key = str(source_path.resolve())
                            archive_path = target_cache.get(cache_key)
                            if archive_path is None:
                                base = source_path.name
                                archive_path = f"ppt/media/{base}"
                                suffix = 1
                                while (
                                    archive_path in existing
                                    or archive_path in additions
                                ):
                                    archive_path = f"ppt/media/{source_path.stem}-{suffix}{source_path.suffix}"
                                    suffix += 1
                                target_cache[cache_key] = archive_path
                                additions[archive_path] = source_path.read_bytes()
                                extensions.add(
                                    source_path.suffix.lower().removeprefix(".")
                                )
                            relationship.set(
                                "Target", f"../media/{Path(archive_path).name}"
                            )
                            relationship.attrib.pop("TargetMode", None)
                            changed = True
                        if changed:
                            data = ET.tostring(
                                root, encoding="utf-8", xml_declaration=True
                            )
                    except ET.ParseError:
                        pass
                target.writestr(info, data)
            for archive_path, data in additions.items():
                target.writestr(archive_path, data)
        shutil.move(str(temp_path), str(path))

    if not extensions:
        return
    mime_types = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "m4a": "audio/mp4",
    }
    with tempfile.TemporaryDirectory(
        prefix="osworld-impress-content-types-"
    ) as temp_dir:
        temp_path = Path(temp_dir) / path.name
        with (
            zipfile.ZipFile(path, "r") as source,
            zipfile.ZipFile(temp_path, "w") as target,
        ):
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == "[Content_Types].xml":
                    root = ET.fromstring(data)
                    known = {
                        node.get("Extension", "").lower()
                        for node in root.findall(f"{{{content_ns}}}Default")
                    }
                    for extension in sorted(extensions - known):
                        ET.SubElement(
                            root,
                            f"{{{content_ns}}}Default",
                            Extension=extension,
                            ContentType=mime_types.get(
                                extension, "application/octet-stream"
                            ),
                        )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                target.writestr(info, data)
        shutil.move(str(temp_path), str(path))


def _page_number_colors(doc: Any) -> dict[int, int]:
    masters = doc.getMasterPages()
    colors: dict[int, int] = {}
    for master_index in range(masters.getCount()):
        master = masters.getByIndex(master_index)
        for shape_index in range(master.getCount()):
            shape = master.getByIndex(shape_index)
            if "<number>" not in _shape_text(shape):
                continue
            color = int(_text_property(shape, "CharColor", -1))
            if 0 <= color <= 0xFFFFFF:
                colors[master_index + 1] = color
                break
    return colors


def _persist_pptx_page_number_colors(
    path: Path,
    doc: Any,
    *,
    colors: dict[int, int] | None = None,
) -> None:
    if (
        path.suffix.lower() != ".pptx"
        or not path.is_file()
        or not zipfile.is_zipfile(path)
    ):
        return
    if colors is None:
        colors = _page_number_colors(doc)
    if not colors:
        return
    a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    with tempfile.TemporaryDirectory(prefix="osworld-impress-page-number-") as temp_dir:
        temp_path = Path(temp_dir) / path.name
        with (
            zipfile.ZipFile(path, "r") as source,
            zipfile.ZipFile(temp_path, "w") as target,
        ):
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename.startswith(
                    "ppt/slideMasters/slideMaster"
                ) and info.filename.endswith(".xml"):
                    try:
                        master_index = int(
                            Path(info.filename).stem.removeprefix("slideMaster")
                        )
                        color = colors.get(master_index)
                        if color is not None:
                            root = ET.fromstring(data)
                            changed = False
                            for field in root.findall(f".//{{{a_ns}}}fld"):
                                if field.get("type") != "slidenum":
                                    continue
                                properties = field.find(f"{{{a_ns}}}rPr")
                                if properties is None:
                                    properties = ET.SubElement(field, f"{{{a_ns}}}rPr")
                                for old_fill in list(properties):
                                    if old_fill.tag == f"{{{a_ns}}}solidFill":
                                        properties.remove(old_fill)
                                fill = ET.SubElement(properties, f"{{{a_ns}}}solidFill")
                                ET.SubElement(
                                    fill, f"{{{a_ns}}}srgbClr", val=f"{color:06X}"
                                )
                                changed = True
                            if changed:
                                data = ET.tostring(
                                    root, encoding="utf-8", xml_declaration=True
                                )
                    except (ValueError, ET.ParseError):
                        pass
                target.writestr(info, data)
        shutil.move(str(temp_path), str(path))


def _paragraph_bullet_states(pages: Any) -> list[list[tuple[str, bool]]]:
    states: list[list[tuple[str, bool]]] = []
    for page_index in range(pages.getCount()):
        page = pages.getByIndex(page_index)
        page_states: list[tuple[str, bool]] = []
        for shape_index in range(page.getCount()):
            shape = page.getByIndex(shape_index)
            try:
                paragraphs = shape.getText().createEnumeration()
            except Exception:
                continue
            while paragraphs.hasMoreElements():
                paragraph = paragraphs.nextElement()
                text = str(paragraph.getString())
                if not text:
                    continue
                try:
                    enabled = bool(paragraph.getPropertyValue("NumberingIsNumber"))
                except Exception:
                    continue
                page_states.append((text, enabled))
        states.append(page_states)
    return states


def _persist_pptx_disabled_bullets(
    path: Path, states: list[list[tuple[str, bool]]]
) -> None:
    """Preserve disabled bullets that LibreOffice 7.3 restores on PPTX save."""
    if (
        path.suffix.lower() != ".pptx"
        or not path.is_file()
        or not zipfile.is_zipfile(path)
    ):
        return
    a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ET.register_namespace("a", a_ns)
    ET.register_namespace("p", p_ns)
    bullet_tags = {
        f"{{{a_ns}}}buChar",
        f"{{{a_ns}}}buAutoNum",
        f"{{{a_ns}}}buBlip",
        f"{{{a_ns}}}buNone",
    }
    with tempfile.TemporaryDirectory(prefix="osworld-impress-bullets-") as temp_dir:
        temp_path = Path(temp_dir) / path.name
        changed_archive = False
        with (
            zipfile.ZipFile(path, "r") as source,
            zipfile.ZipFile(temp_path, "w") as target,
        ):
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename.startswith(
                    "ppt/slides/slide"
                ) and info.filename.endswith(".xml"):
                    try:
                        page_index = (
                            int(Path(info.filename).stem.removeprefix("slide")) - 1
                        )
                        text_states: dict[str, deque[bool]] = defaultdict(deque)
                        for text, enabled in states[page_index]:
                            text_states[text].append(enabled)
                        root = ET.fromstring(data)
                        changed = False
                        for paragraph in root.findall(f".//{{{a_ns}}}p"):
                            text = "".join(
                                node.text or ""
                                for node in paragraph.findall(f".//{{{a_ns}}}t")
                            )
                            if not text or not text_states[text]:
                                continue
                            enabled = text_states[text].popleft()
                            if enabled:
                                continue
                            properties = paragraph.find(f"{{{a_ns}}}pPr")
                            if properties is None:
                                properties = ET.Element(f"{{{a_ns}}}pPr")
                                paragraph.insert(0, properties)
                            children = list(properties)
                            bullet_indices = [
                                index
                                for index, child in enumerate(children)
                                if child.tag in bullet_tags
                            ]
                            if (
                                len(bullet_indices) == 1
                                and children[bullet_indices[0]].tag
                                == f"{{{a_ns}}}buNone"
                            ):
                                continue
                            insert_at = (
                                bullet_indices[0] if bullet_indices else len(children)
                            )
                            for child in children:
                                if child.tag in bullet_tags:
                                    properties.remove(child)
                            properties.insert(
                                insert_at, ET.Element(f"{{{a_ns}}}buNone")
                            )
                            changed = True
                        if changed:
                            data = ET.tostring(
                                root, encoding="utf-8", xml_declaration=True
                            )
                            changed_archive = True
                    except (ValueError, IndexError, ET.ParseError):
                        pass
                target.writestr(info, data)
        if changed_archive:
            shutil.move(str(temp_path), str(path))


def _text_spans(text: str, params: dict[str, Any]) -> list[tuple[int, int]]:
    if "match_text" in params:
        needle = str(params["match_text"])
        if not needle:
            raise AdapterError("INVALID_REQUEST", "match_text must not be empty")
        matches = []
        start = 0
        while True:
            index = text.find(needle, start)
            if index < 0:
                break
            matches.append((index, len(needle)))
            start = index + len(needle)
        if not matches:
            raise AdapterError(
                "TEXT_NOT_FOUND",
                "match_text was not found in the shape",
                {"match_text": needle},
                404,
            )
        return matches
    if "lines" in params:
        requested = params["lines"]
        if not isinstance(requested, list) or not requested:
            raise AdapterError(
                "INVALID_REQUEST",
                "lines must be a non-empty array of zero-based indices",
            )
        spans = []
        offset = 0
        line_values = text.splitlines(keepends=True)
        for index, value in enumerate(line_values):
            content_length = len(value.rstrip("\r\n"))
            if index in requested:
                spans.append((offset, content_length))
            offset += len(value)
        if len(spans) != len(set(requested)):
            raise AdapterError(
                "INVALID_REQUEST", "one or more line indices are out of range"
            )
        return spans
    return [(0, len(text))]


def _set_text_properties(
    text: Any, props: dict[str, Any], params: dict[str, Any] | None = None
) -> None:
    for start, length in _text_spans(str(text.getString()), params or {}):
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        if start:
            cursor.goRight(start, False)
        cursor.goRight(length, True)
        for key, value in props.items():
            if value is not None:
                cursor.setPropertyValue(key, value)


def _set_cursor_properties(
    shape: Any, props: dict[str, Any], params: dict[str, Any] | None = None
) -> None:
    _set_text_properties(shape.getText(), props, params)


def _text_format_properties(params: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    if "color" in params:
        properties["CharColor"] = _color(params["color"])
    if "font_size" in params:
        properties["CharHeight"] = float(params["font_size"])
    if "font_name" in params:
        properties["CharFontName"] = params["font_name"]
    if "bold" in params:
        properties["CharWeight"] = _font_weight(params["bold"])
    if "italic" in params:
        properties["CharPosture"] = _enum(
            "com.sun.star.awt.FontSlant",
            "ITALIC" if params["italic"] else "NONE",
        )
    if "underline" in params:
        properties["CharUnderline"] = 1 if params["underline"] else 0
    if "strike" in params:
        properties["CharStrikeout"] = 1 if params["strike"] else 0
    return properties


def _dispatch_for_selection(
    session: ImpressSession, selection: Any, command: str
) -> None:
    controller = session.doc.getCurrentController()
    try:
        controller.select(selection)
        dispatcher = session.service_manager.createInstanceWithContext(
            "com.sun.star.frame.DispatchHelper", session.context
        )
        dispatcher.executeDispatch(controller.getFrame(), command, "", 0, ())
    except Exception as exc:
        raise AdapterError(
            "UNSUPPORTED_OPERATION",
            f"LibreOffice dispatch failed: {command}",
            str(exc),
        ) from exc


def _set_bullet(
    session: ImpressSession, shape: Any, enabled: bool, params: dict[str, Any]
) -> None:
    # DefaultBullet follows the same code path as the Impress toolbar and
    # preserves a level-zero bullet in PPTX. Directly selecting the first UNO
    # NumberingRules entry produces a different outline level in LO 7.3.
    if enabled and "match_text" not in params and "lines" not in params:
        _dispatch_for_selection(session, shape, ".uno:DefaultBullet")
        return

    text = shape.getText()
    for start, length in _text_spans(str(text.getString()), params):
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        if start:
            cursor.goRight(start, False)
        cursor.goRight(length, True)
        level = int(params.get("level", 0))
        rules = cursor.getPropertyValue("NumberingRules")
        if enabled:
            template = None
            for candidate in range(rules.getCount()):
                properties = rules.getByIndex(candidate)
                numbering_type = next(
                    (prop.Value for prop in properties if prop.Name == "NumberingType"),
                    5,
                )
                if numbering_type == 6:
                    template = properties
                    break
            if template is None:
                raise AdapterError(
                    "UNSUPPORTED_OPERATION",
                    "presentation does not expose a bullet numbering rule",
                )
            level = candidate
        cursor.setPropertyValue("NumberingLevel", level)
        cursor.setPropertyValue("NumberingIsNumber", enabled)


def _font_weight(value: Any):
    if isinstance(value, bool):
        # com.sun.star.awt.FontWeight is a float property, not a UNO enum.
        return 150.0 if value else 100.0
    if isinstance(value, (int, float)):
        return float(value)
    raise AdapterError("INVALID_REQUEST", "bold must be boolean or UNO font weight")


def _fill_properties(
    session: ImpressSession,
    color: Any = None,
    bitmap: str | None = None,
    existing: Any | None = None,
) -> Any:
    # A page's Background property is a FillProperties struct.  Mutating that
    # struct preserves the implementation-specific bitmap fields exposed by
    # LibreOffice; the standalone FillProperties service does not expose all
    # of them on LibreOffice 7.3.
    fill = existing
    if fill is None:
        fill = session.service_manager.createInstanceWithContext(
            "com.sun.star.drawing.FillProperties", session.context
        )
    if bitmap:
        fill.FillStyle = _enum("com.sun.star.drawing.FillStyle", "BITMAP")
        bitmap_url = _file_url(bitmap)
        bitmap_name = "osworld-" + hashlib.sha256(bitmap_url.encode()).hexdigest()[:16]
        bitmap_table = session.doc.createInstance("com.sun.star.drawing.BitmapTable")
        if bitmap_table.hasByName(bitmap_name):
            bitmap_table.replaceByName(bitmap_name, bitmap_url)
        else:
            bitmap_table.insertByName(bitmap_name, bitmap_url)
        fill.FillBitmapName = bitmap_name
        fill.FillBitmapMode = _enum("com.sun.star.drawing.BitmapMode", "STRETCH")
    else:
        fill.FillStyle = _enum("com.sun.star.drawing.FillStyle", "SOLID")
        fill.FillColor = _color(color)
    return fill


def _inspect(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    indices = params.get("slides", list(range(session.pages.getCount())))
    return {
        "identity": session.identity(),
        "slide_count": session.pages.getCount(),
        "inspected_slides": list(indices),
        "slides": [_page_summary(session, i) for i in indices],
    }


def _page_size_state(session: ImpressSession) -> dict[str, Any]:
    return {
        name: [
            {
                "width": int(pages.getByIndex(i).Width),
                "height": int(pages.getByIndex(i).Height),
            }
            for i in range(pages.getCount())
        ]
        for name, pages in (
            ("slides", session.pages), ("masters", session.doc.getMasterPages())
        )
    }


def _set_page_size(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    before = _page_size_state(session)
    for pages in (session.pages, session.doc.getMasterPages()):
        for index in range(pages.getCount()):
            page = pages.getByIndex(index)
            page.Width = params["width"]
            page.Height = params["height"]
    return {"unit": "1/100 mm", "before": before, "after": _page_size_state(session)}


def _save(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    bullet_states = _paragraph_bullet_states(session.pages)
    page_number_colors = _page_number_colors(session.doc)
    url = params.get("url")
    if url:
        path = _path_from_input(str(url))
        filter_name = params.get("filter_name") or (
            "Impress MS PowerPoint 2007 XML"
            if path.suffix.lower() == ".pptx"
            else "impress8"
        )
        session.doc.storeAsURL(
            _file_url(str(path)),
            (_property("FilterName", filter_name), _property("Overwrite", True)),
        )
    else:
        if not session.doc.hasLocation():
            raise AdapterError("SAVE_FAILED", "presentation has no save location")
        session.doc.store()
    saved_path = _path_from_url(str(session.doc.URL))
    if saved_path:
        _persist_pptx_transitions(saved_path, session.pages)
        _persist_pptx_media(saved_path)
        _persist_pptx_page_number_colors(
            saved_path,
            session.doc,
            colors=page_number_colors,
        )
        _persist_pptx_disabled_bullets(saved_path, bullet_states)
    return {
        "url": str(session.doc.URL),
        "title": str(session.doc.Title),
        "size": saved_path.stat().st_size if saved_path and saved_path.is_file() else 0,
    }


def _export(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    format_name = params["format"].lower()
    validate_export_destination(format_name, params["url"])
    path = _path_from_input(str(params["url"]))
    filters = {
        "pptx": "Impress MS PowerPoint 2007 XML",
        "odp": "impress8",
        "pdf": "impress_pdf_Export",
        "png": "impress_png_Export",
        "jpg": "impress_jpg_Export",
    }
    filter_name = filters.get(format_name)
    if not filter_name:
        raise AdapterError(
            "INVALID_REQUEST", f"unsupported export format: {format_name}"
        )
    pixel_width = params.get("pixel_width")
    pixel_height = params.get("pixel_height")
    try:
        if format_name in {"png", "jpg"} and pixel_width is not None:
            page = session.page(int(params.get("slide", 0)))
            export_filter = session.service_manager.createInstanceWithContext(
                "com.sun.star.drawing.GraphicExportFilter", session.context
            )
            export_filter.setSourceDocument(page)
            media_type = "image/png" if format_name == "png" else "image/jpeg"
            succeeded = export_filter.filter(
                (
                    _property("URL", _file_url(str(path))),
                    _property("MediaType", media_type),
                    # GraphicExportFilter uses Width/Height for pixel dimensions;
                    # PixelWidth/PixelHeight are ignored by LibreOffice 7.3.
                    _property("Width", int(pixel_width)),
                    _property("Height", int(pixel_height)),
                )
            )
            if not succeeded:
                raise AdapterError(
                    "EXPORT_FAILED",
                    "LibreOffice graphic export filter returned false",
                )
        else:
            session.doc.storeToURL(
                _file_url(str(path)),
                (
                    _property("FilterName", filter_name),
                    _property("Overwrite", True),
                ),
            )
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "EXPORT_FAILED",
            "LibreOffice export failed",
            str(exc),
        ) from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise AdapterError("EXPORT_FAILED", "export did not create a non-empty file")
    return {
        "format": format_name,
        "path": str(path),
        "size": path.stat().st_size,
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
        "slide": int(params.get("slide", 0)) if format_name in {"png", "jpg"} else None,
    }


def _export_shape_image(
    session: ImpressSession, params: dict[str, Any]
) -> dict[str, Any]:
    page = session.page(int(params["slide"]))
    selector = dict(params["selector"])
    shape = session.shape(page, selector)
    kind = str(
        getattr(shape, "ShapeType", "") or getattr(shape, "ImplementationName", "")
    )
    graphic = getattr(shape, "Graphic", None)
    if graphic is None or "graphicobjectshape" not in kind.casefold():
        raise AdapterError(
            "NOT_AN_IMAGE_SHAPE",
            "selected shape is not an embedded picture",
            {
                "slide": int(params["slide"]),
                "selector": selector,
                "name": str(getattr(shape, "Name", "") or ""),
                "kind": kind,
            },
            422,
        )

    output_url = _file_url(params["output_path"])
    output_path = _path_from_url(output_url)
    if output_path is None:
        raise AdapterError(
            "INVALID_REQUEST",
            "output_path must be a local path or file URL",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overwrite = bool(params.get("overwrite", True))
    if output_path.exists() and not overwrite:
        raise AdapterError(
            "FILE_EXISTS",
            f"output file already exists: {output_path}",
            http_status=409,
        )

    suffix = output_path.suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    provider = session.service_manager.createInstanceWithContext(
        "com.sun.star.graphic.GraphicProvider", session.context
    )
    try:
        provider.storeGraphic(
            graphic,
            (
                _property("URL", output_url),
                _property("MimeType", media_type),
            ),
        )
    except Exception as exc:
        raise AdapterError(
            "EXPORT_FAILED",
            "LibreOffice failed to export the selected embedded picture",
            str(exc),
        ) from exc
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise AdapterError(
            "EXPORT_FAILED", "image export did not create a non-empty file"
        )
    return {
        "slide": int(params["slide"]),
        "selector": selector,
        "shape": {
            "name": str(getattr(shape, "Name", "") or ""),
            "kind": kind,
        },
        "output_path": str(output_path),
        "format": suffix.removeprefix(".").replace("jpeg", "jpg"),
        "size": output_path.stat().st_size,
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
    }


def _create_slide(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    index = params.get("index", session.pages.getCount())
    if index > session.pages.getCount():
        raise AdapterError("INVALID_REQUEST", "slide index is past the end")
    page = session.pages.insertNewByIndex(index)
    if "layout" in params:
        page.Layout = int(params["layout"])
    return {
        "index": index,
        "count": session.pages.getCount(),
        "layout": int(page.Layout),
    }


def _presentation_slide_title(page: Any) -> str:
    candidates: list[tuple[int, int, str]] = []
    for index in range(page.getCount()):
        shape = page.getByIndex(index)
        text = _shape_text(shape).strip()
        if not text:
            continue
        kind = str(getattr(shape, "ShapeType", ""))
        position = getattr(shape, "Position", None)
        y = int(getattr(position, "Y", 0))
        is_title = "titletextshape" in kind.casefold()
        candidates.append((0 if is_title else 1, y, text.splitlines()[0].strip()))
    if not candidates:
        return ""
    return min(candidates)[2]


def _presentation_create_summary_slide(
    session: ImpressSession, params: dict[str, Any]
) -> dict[str, Any]:
    source_titles = []
    for index in params["slides"]:
        title = _presentation_slide_title(session.page(index))
        if title:
            source_titles.append({"slide": index, "title": title})
    if not source_titles:
        raise AdapterError(
            "NO_SLIDE_TITLES",
            "none of the selected slides contains a non-empty title or text heading",
            {"slides": params["slides"]},
            422,
        )

    index = params.get("index", session.pages.getCount())
    if index > session.pages.getCount():
        raise AdapterError("INVALID_REQUEST", "summary slide index is past the end")
    page = session.pages.insertNewByIndex(index)
    try:
        page.Layout = 20
        uno, _ = _uno_modules()
        title_shape = session.doc.createInstance("com.sun.star.drawing.TextShape")
        # UNO initializes the text object when the shape joins a page. Text
        # assigned to an unattached shape can be discarded by page.add().
        page.add(title_shape)
        title_shape.Position = uno.createUnoStruct(
            "com.sun.star.awt.Point", 900, 500
        )
        title_shape.Size = uno.createUnoStruct(
            "com.sun.star.awt.Size", int(page.Width) - 1800, max(1200, int(page.Height * 0.16))
        )
        title_shape.String = params.get("title", "Summary Slide")
        title_shape.CharHeight = 28.0
        title_shape.CharWeight = 150.0

        body_shape = session.doc.createInstance("com.sun.star.drawing.TextShape")
        page.add(body_shape)
        body_shape.Position = uno.createUnoStruct(
            "com.sun.star.awt.Point", 1200, max(1900, int(page.Height * 0.2))
        )
        body_shape.Size = uno.createUnoStruct(
            "com.sun.star.awt.Size", int(page.Width) - 2400, int(page.Height * 0.72)
        )
        body_text = "\n".join(
            f"{item['slide'] + 1}. {item['title']}" for item in source_titles
        )
        body_shape.String = body_text
        body_shape.CharHeight = 20.0
        observed = [_shape_text(page.getByIndex(i)) for i in range(page.getCount())]
        if params.get("title", "Summary Slide") not in observed or body_text not in observed:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "summary slide content did not read back exactly",
                {"expected_title": params.get("title", "Summary Slide"), "expected_items": body_text, "observed": observed},
                422,
            )
    except Exception:
        session.pages.remove(page)
        raise
    return {
        "slide": index,
        "slide_count": session.pages.getCount(),
        "title": params.get("title", "Summary Slide"),
        "source_titles": source_titles,
        "verification_passed": True,
    }


def _clear_page_shapes(page: Any) -> None:
    while page.getCount():
        page.remove(page.getByIndex(0))


def _create_slides_from_images(
    session: ImpressSession, params: dict[str, Any]
) -> dict[str, Any]:
    validate_image_path_suffixes(params["image_paths"])
    paths = [Path(path).expanduser() for path in params["image_paths"]]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise AdapterError(
            "FILE_NOT_FOUND", "one or more image paths do not exist", missing, 404
        )

    old_count = session.pages.getCount()
    replace_existing = bool(params["replace_existing_slides"])
    insert_at = old_count
    fit_mode = params.get("fit_mode", "original")
    created: list[dict[str, Any]] = []
    try:
        for _path in paths:
            page = session.pages.insertNewByIndex(insert_at)
            page.Layout = 20
            _clear_page_shapes(page)
            insert_at += 1

        # Populate the staged pages while every original page is still intact.
        # If insertion or fitting fails, the cleanup below removes only staged pages.
        for offset, path in enumerate(paths):
            staged_slide = old_count + offset
            image = _insert_image(session, {"slide": staged_slide, "path": str(path)})
            if fit_mode != "original":
                image = _fit_to_slide(
                    session,
                    {
                        "slide": staged_slide,
                        "selector": {"index": image["index"]},
                        "mode": fit_mode,
                    },
                )
            created.append(
                {
                    "slide": offset if replace_existing else staged_slide,
                    "path": str(path),
                    "shape_index": int(image["index"]),
                    "fit_mode": fit_mode,
                }
            )
    except Exception:
        while session.pages.getCount() > old_count:
            session.pages.remove(session.pages.getByIndex(old_count))
        raise

    if replace_existing:
        for _ in range(old_count):
            session.pages.remove(session.pages.getByIndex(0))

    return {
        "slides": created,
        "slide_count": session.pages.getCount(),
        "replace_existing_slides": replace_existing,
        "removed_slide_count": old_count if replace_existing else 0,
    }


def _delete_slide(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    page = session.page(params["slide"])
    if session.pages.getCount() <= 1:
        raise AdapterError("CONFLICT", "cannot delete the only slide")
    session.pages.remove(page)
    return {"count": session.pages.getCount()}


def _dispatch(session: ImpressSession, command: str) -> None:
    controller = session.doc.getCurrentController()
    frame = controller.getFrame()
    dispatcher = session.service_manager.createInstanceWithContext(
        "com.sun.star.frame.DispatchHelper", session.context
    )
    dispatcher.executeDispatch(frame, command, "", 0, ())


def _duplicate_slide(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    source = params["slide"]
    session.page(source)
    session.doc.getCurrentController().setCurrentPage(session.page(source))
    _dispatch(session, ".uno:DuplicatePage")
    created = source + 1
    target = params.get("index", created)
    while created > target:
        session.doc.getCurrentController().setCurrentPage(session.page(created))
        _dispatch(session, ".uno:MovePageUp")
        created -= 1
    while created < target:
        session.doc.getCurrentController().setCurrentPage(session.page(created))
        _dispatch(session, ".uno:MovePageDown")
        created += 1
    return {"source": source, "index": target, "count": session.pages.getCount()}


def _move_slide(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    source = params["slide"]
    target = params["index"]
    session.page(source)
    if target >= session.pages.getCount():
        raise AdapterError("INVALID_REQUEST", "target slide index is past the end")
    while source > target:
        session.doc.getCurrentController().setCurrentPage(session.page(source))
        _dispatch(session, ".uno:MovePageUp")
        source -= 1
    while source < target:
        session.doc.getCurrentController().setCurrentPage(session.page(source))
        _dispatch(session, ".uno:MovePageDown")
        source += 1
    return {"index": source, "count": session.pages.getCount()}


def _set_background(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    slide_indices = (
        list(range(session.pages.getCount()))
        if params.get("all_slides") is True
        else [params["slide"]]
    )
    backgrounds = []
    for slide in slide_indices:
        page = session.page(slide)
        existing = page.getPropertyValue("Background")
        fill = _fill_properties(
            session,
            color=params.get("color"),
            bitmap=params.get("image_path"),
            existing=existing,
        )
        page.setPropertyValue("Background", fill)
        backgrounds.append({"slide": slide, "background": _background_summary(page)})
    if params.get("all_slides") is True:
        result = {"all_slides": True, "count": len(backgrounds), "slides": backgrounds}
    else:
        result = backgrounds[0]
    result.update(
        saved_by_action=False,
        guidance=(
            "The background was changed in the open presentation. Call presentation.save "
            "to write the changes to the file, then inspect the presentation and screenshot. "
            "This action does not save."
        ),
    )
    return result


def _set_transition(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    mapping = {"dissolve": "DISSOLVE", "fade": "FADE_FROM_RIGHT", "none": "NONE"}
    transition = params["transition"].lower()
    if transition not in mapping:
        raise AdapterError(
            "UNSUPPORTED_OPERATION", f"unsupported transition: {transition}"
        )
    page = session.page(params["slide"])
    page.Effect = _enum("com.sun.star.presentation.FadeEffect", mapping[transition])
    return {"slide": params["slide"], "effect": str(page.Effect)}


def _set_notes(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    notes = session.page(params["slide"]).getNotesPage()
    observed = set_speaker_notes(
        notes,
        params["text"],
        create_instance=session.doc.createInstance,
    )
    return {"slide": params["slide"], "text": observed}


def _create_text(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    uno, _ = _uno_modules()
    page = session.page(params["slide"])
    shape = session.doc.createInstance("com.sun.star.drawing.TextShape")
    page.add(shape)
    shape.Position = uno.createUnoStruct(
        "com.sun.star.awt.Point", int(params.get("x", 1000)), int(params.get("y", 1000))
    )
    shape.Size = uno.createUnoStruct(
        "com.sun.star.awt.Size",
        int(params.get("width", 10000)),
        int(params.get("height", 2000)),
    )
    shape.String = params["text"]
    if "name" in params:
        shape.Name = str(params["name"])
    return _shape_summary(shape, page.getCount() - 1)


def _write_text(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    shape = session.shape(session.page(params["slide"]), params["selector"])
    shape.String = params["text"]
    return {"text": _shape_text(shape), "selector": params["selector"]}


def _set_role_text(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    page = session.page(params["slide"])
    matches = list(iter_shapes_for_roles(page, [params["role"]]))
    if not matches:
        raise AdapterError(
            "ROLE_NOT_FOUND",
            "no text-bearing shape matches the requested semantic role",
            {"slide": params["slide"], "role": params["role"]},
            404,
        )
    if len(matches) != 1:
        raise AdapterError(
            "ROLE_AMBIGUOUS",
            "more than one text-bearing shape matches the requested semantic role",
            {
                "slide": params["slide"],
                "role": params["role"],
                "paths": [path for path, _shape, _role in matches],
            },
            409,
        )
    path, shape, resolved_role = matches[0]
    before = _shape_text(shape)
    shape.getText().setString(params["text"])
    observed = _shape_text(shape)
    if observed != params["text"]:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "semantic role text replacement did not persist",
            {"expected": params["text"], "observed": observed, "path": path},
            422,
        )
    formatting = {
        key: params[key]
        for key in (
            "color",
            "font_size",
            "font_name",
            "bold",
            "italic",
            "underline",
            "strike",
            "alignment",
        )
        if key in params
    }
    formatted = _format_role_shape_text(shape, formatting) if formatting else None
    return {
        "slide": params["slide"],
        "requested_role": params["role"],
        "resolved_role": resolved_role,
        "path": path,
        "previous_text": before,
        "text": observed,
        "properties": formatted["properties"] if formatted is not None else {},
    }


def _write_text_native(
    session: ImpressSession, params: dict[str, Any]
) -> dict[str, Any]:
    page = session.page(params["slide"])
    shape = session.shape(page, params["selector"])
    before = _shape_text(shape)
    replace = bool(params.get("replace", False))
    kind = str(
        getattr(shape, "ShapeType", "") or getattr(shape, "ImplementationName", "")
    )
    if "presentation." not in kind or not hasattr(shape, "getText"):
        raise AdapterError(
            "UNSUPPORTED_OPERATION",
            "shape.write_text_native requires a presentation text placeholder",
            {"kind": kind, "selector": params["selector"]},
            422,
        )
    if before and not replace:
        raise AdapterError(
            "CONFLICT",
            "target placeholder is not empty; pass replace=true to replace it",
            {"text": before, "selector": params["selector"]},
            409,
        )

    try:
        import pyautogui
    except Exception as exc:
        raise AdapterError(
            "GUI_FALLBACK_UNAVAILABLE",
            "pyautogui is required for native placeholder text entry",
            str(exc),
            503,
        ) from exc

    controller = session.doc.getCurrentController()
    controller.setCurrentPage(page)
    controller.select(shape)
    try:
        controller.getFrame().getContainerWindow().setFocus()
    except Exception:
        pass

    clipboard_module = None
    previous_clipboard = None
    try:
        import pyperclip

        clipboard_module = pyperclip
        previous_clipboard = pyperclip.paste()
        pyperclip.copy(params["text"])
    except Exception:
        clipboard_module = None

    try:
        time.sleep(0.2)
        pyautogui.press("f2")
        time.sleep(0.2)
        if replace:
            pyautogui.hotkey("ctrl", "a")
        if clipboard_module is not None:
            pyautogui.hotkey("ctrl", "v")
        else:
            try:
                params["text"].encode("ascii")
            except UnicodeEncodeError as exc:
                raise AdapterError(
                    "GUI_FALLBACK_UNAVAILABLE",
                    "Unicode native text entry requires pyperclip",
                    str(exc),
                    503,
                ) from exc
            pyautogui.write(params["text"], interval=0.01)
        time.sleep(0.2)
        pyautogui.press("esc")
        time.sleep(0.2)
    finally:
        if clipboard_module is not None and previous_clipboard is not None:
            try:
                clipboard_module.copy(previous_clipboard)
            except Exception:
                pass

    observed = _shape_text(shape)
    if observed != params["text"]:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "native placeholder text entry did not produce the requested text",
            {
                "expected": params["text"],
                "observed": observed,
                "selector": params["selector"],
            },
            422,
        )
    return {
        "text": observed,
        "previous_text": before,
        "selector": params["selector"],
        "kind": kind,
        "entry_mode": "native_text_edit",
    }


def _format_text(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    shape = session.shape(session.page(params["slide"]), params["selector"])
    cursor_props = _text_format_properties(params)
    _set_cursor_properties(shape, cursor_props, params)
    if "alignment" in params:
        values = {
            "left": "LEFT",
            "center": "CENTER",
            "right": "RIGHT",
            "justify": "BLOCK",
        }
        if params["alignment"] not in values:
            raise AdapterError("INVALID_REQUEST", "unsupported text alignment")
        shape.ParaAdjust = _enum(
            "com.sun.star.style.ParagraphAdjust", values[params["alignment"]]
        )
    if "level" in params:
        _set_cursor_properties(shape, {"NumberingLevel": int(params["level"])}, params)
    if "bullet" in params:
        _set_bullet(session, shape, bool(params["bullet"]), params)
    paragraph_props: dict[str, Any] = {}
    if "left_margin" in params:
        paragraph_props["ParaLeftMargin"] = int(params["left_margin"])
    if "first_line_indent" in params:
        paragraph_props["ParaFirstLineIndent"] = int(params["first_line_indent"])
    if paragraph_props:
        _set_cursor_properties(shape, paragraph_props, params)
    observed: dict[str, Any] = {}
    if cursor_props:
        text = shape.getText()
        scoped = "lines" in params or "match_text" in params
        for span in _text_spans(str(text.getString()), params):
            observed = _read_text_properties(
                text, list(cursor_props), span=span if scoped else None
            )
            mismatches = {
                name: {"expected": str(expected), "observed": str(observed[name])}
                for name, expected in cursor_props.items()
                if not _text_property_equivalent(name, observed[name], expected, 0.01)
            }
            if mismatches:
                raise AdapterError(
                    "VERIFICATION_FAILED",
                    "native text formatting read-back did not match the requested values; "
                    "partial changes may remain",
                    {
                        "mismatches": mismatches,
                        "selector": params["selector"],
                        "span": {"start": span[0], "length": span[1]},
                        "state_may_have_changed": True,
                    },
                    422,
                )
    return {
        "text": _shape_text(shape),
        "properties": {key: str(value) for key, value in observed.items()},
        "alignment": _alignment_name(getattr(shape, "ParaAdjust", None)),
        "paragraphs": _paragraph_summaries(shape),
    }


def _role_text_properties(params: dict[str, Any]) -> dict[str, Any]:
    properties = _text_format_properties(params)
    if "alignment" in params:
        values = {
            "left": "LEFT",
            "center": "CENTER",
            "right": "RIGHT",
            "justify": "BLOCK",
        }
        properties["ParaAdjust"] = _enum(
            "com.sun.star.style.ParagraphAdjust", values[params["alignment"]]
        )
    return properties


_PARAGRAPH_ADJUST_CODES = {
    "LEFT": 0,
    "RIGHT": 1,
    "BLOCK": 2,
    "CENTER": 3,
    "STRETCH": 4,
}


def _paragraph_adjust_code(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer():
        return int(value)
    name = _enum_name(value).strip().upper()
    if name == "JUSTIFY":
        name = "BLOCK"
    if name in _PARAGRAPH_ADJUST_CODES:
        return _PARAGRAPH_ADJUST_CODES[name]
    try:
        return int(name)
    except ValueError:
        return None


def _text_property_equivalent(
    name: str, actual: Any, expected: Any, tolerance: float
) -> bool:
    if name == "ParaAdjust":
        actual_code = _paragraph_adjust_code(actual)
        expected_code = _paragraph_adjust_code(expected)
        if actual_code is not None and expected_code is not None:
            return actual_code == expected_code
    return _equivalent(actual, expected, tolerance)


def _format_role_shape_text(shape: Any, params: dict[str, Any]) -> dict[str, Any]:
    properties = _role_text_properties(params)
    text = shape.getText()
    _set_text_properties(text, properties)
    observed = _read_text_properties(text, list(properties))
    mismatches = {
        name: {"expected": str(expected), "observed": str(observed[name])}
        for name, expected in properties.items()
        if not _text_property_equivalent(name, observed[name], expected, 0.01)
    }
    if mismatches:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "role-based text formatting did not persist",
            {"mismatches": mismatches},
            422,
        )
    return {
        "text": str(text.getString()),
        "properties": {name: str(value) for name, value in observed.items()},
    }


def _format_text_roles(
    session: ImpressSession, params: dict[str, Any]
) -> dict[str, Any]:
    slide_indices = [params["slide"]] if "slide" in params else list(params["slides"])
    pages = [(slide, session.page(slide)) for slide in slide_indices]
    rules = [
        {
            key: value
            for key, value in params.items()
            if key not in {"slide", "slides", "overrides"}
        },
        *params.get("overrides", []),
    ]
    plans = []
    for slide, page in pages:
        slide_rules = []
        for rule_index, rule in enumerate(rules):
            requested_roles = list(rule["roles"])
            matches = list(iter_shapes_for_roles(page, requested_roles))
            if not matches:
                raise AdapterError(
                    "ROLE_NOT_FOUND",
                    "no text-bearing shape matches the requested semantic roles",
                    {
                        "slide": slide,
                        "roles": requested_roles,
                        "normalized_roles": list(normalize_roles(requested_roles)),
                    },
                    404,
                )
            slide_rules.append((rule_index, rule, requested_roles, matches))
        plans.append((slide, slide_rules))

    slide_results = []
    for slide, slide_rules in plans:
        applied_rules = []
        for rule_index, rule, requested_roles, matches in slide_rules:
            formatted = []
            for path, shape, role in matches:
                result = (
                    _format_table_shape_text(shape, rule)
                    if role == "table"
                    else _format_role_shape_text(shape, rule)
                )
                formatted.append({"path": path, "role": role, **result})
            applied_rules.append(
                {
                    "index": rule_index,
                    "requested_roles": requested_roles,
                    "normalized_roles": list(normalize_roles(requested_roles)),
                    "formatted": formatted,
                }
            )
        slide_results.append({"slide": slide, "rules": applied_rules})

    if "slide" in params:
        return slide_results[0]
    return {
        "slides": slide_results,
        "formatted_slide_count": len(slide_results),
    }


def _match_paragraph_indent(
    session: ImpressSession, params: dict[str, Any]
) -> dict[str, Any]:
    page = session.page(params["slide"])
    candidates = [
        (path, paragraphs)
        for path, shape in _shapes_with_paths(page)
        if (paragraphs := _paragraph_summaries(shape))
    ]
    plan = _resolve_paragraph_indent_shape(
        candidates,
        params["target_text"],
        params["reference_texts"],
        match_mode=params.get("match_mode", "exact"),
        case_sensitive=bool(params.get("case_sensitive", False)),
    )
    shape = session.shape(page, {"path": plan["path"]})
    target_selection = {"lines": [plan["target_index"]]}
    if "bullet" in params:
        _set_bullet(session, shape, bool(params["bullet"]), target_selection)
    indent_properties = {
        "NumberingLevel": plan["indent"]["level"],
        "ParaLeftMargin": plan["indent"]["left_margin"],
        "ParaFirstLineIndent": plan["indent"]["first_line_indent"],
    }
    _set_cursor_properties(shape, indent_properties, target_selection)

    after = _paragraph_summaries(shape)
    target = after[plan["target_index"]]
    observed_indent = {
        field: target[field] for field in ("level", "left_margin", "first_line_indent")
    }
    bullet_matches = "bullet" not in params or target["bullet"] == params["bullet"]
    if observed_indent != plan["indent"] or not bullet_matches:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "target paragraph indentation did not match the requested reference",
            {
                "expected_indent": plan["indent"],
                "observed": target,
                "requested_bullet": params.get("bullet"),
            },
            422,
        )
    return {
        "selector": {"path": plan["path"]},
        "target": target,
        "reference_indices": plan["reference_indices"],
        "copied_indent": plan["indent"],
        "verification_passed": True,
        "paragraphs": after,
    }


def _set_geometry(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    slide_index = require_slide_index(params, allow_consistent_pair=True)
    page = session.page(slide_index)
    shape = session.shape(page, params["selector"])
    edge = params.get("edge")
    resolved_geometry = {} if edge is not None else resolve_shape_geometry(params)
    if edge is not None:
        target = edge_aligned_position(
            edge=edge,
            slide_width=int(page.Width),
            slide_height=int(page.Height),
            x=int(shape.Position.X),
            y=int(shape.Position.Y),
            width=int(shape.Size.Width),
            height=int(shape.Size.Height),
        )
        position = shape.Position
        position.X = target["x"]
        position.Y = target["y"]
        shape.Position = position
    elif "x" in resolved_geometry or "y" in resolved_geometry:
        pos = shape.Position
        pos.X = resolved_geometry.get("x", int(pos.X))
        pos.Y = resolved_geometry.get("y", int(pos.Y))
        shape.Position = pos
    if "width" in resolved_geometry or "height" in resolved_geometry:
        size = shape.Size
        size.Width = resolved_geometry.get("width", int(size.Width))
        size.Height = resolved_geometry.get("height", int(size.Height))
        shape.Size = size
    summary_path = params["selector"].get("path")
    result = (
        _shape_summary_at_path(shape, summary_path)
        if isinstance(summary_path, list)
        else _shape_summary(shape, params["selector"].get("index", -1))
    )
    result.update(
        {
            "slide": slide_index,
            "display_slide_number": slide_index + 1,
        }
    )
    if edge is not None:
        result.update(
            {
                "edge": edge,
                "slide_width": int(page.Width),
                "slide_height": int(page.Height),
                "verification_passed": (
                    result["x"] == target["x"] and result["y"] == target["y"]
                ),
            }
        )
    else:
        result.update(
            {
                "requested_measurements": {
                    field: params[field]
                    for field in ("width_measurement", "height_measurement")
                    if field in params
                },
                "resolved_geometry": resolved_geometry,
                "verification_passed": all(
                    result[field] == value for field, value in resolved_geometry.items()
                ),
            }
        )
    return result


def _geometry_atom(
    session: ImpressSession, params: dict[str, Any], *, action: str,
) -> dict[str, Any]:
    validate_atomic_geometry_params(action, params)
    page = session.page(require_slide_index(params, allow_consistent_pair=True))
    shape = session.shape(page, params["selector"])
    before = {"x": int(shape.Position.X), "y": int(shape.Position.Y),
              "width": int(shape.Size.Width), "height": int(shape.Size.Height)}
    if action == "shape.align_to_slide":
        changed_fields = {"x"} if params["edge"] in {"left", "right"} else {"y"}
    else:
        changed_fields = {field.removesuffix("_measurement") for field in params
                          if field in {"x", "y", "width", "height", "width_measurement", "height_measurement"}}
    result = _set_geometry(session, params)
    unchanged = {field: value for field, value in before.items() if field not in changed_fields}
    result.update({
        "operation": action,
        "before_geometry": before,
        "preserved_geometry": unchanged,
        "verification_passed": bool(result.get("verification_passed"))
        and all(result.get(field) == value for field, value in unchanged.items()),
    })
    return result


def _align_to_slide(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    return _geometry_atom(session, params, action="shape.align_to_slide")


def _move_shape(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    return _geometry_atom(session, params, action="shape.move")


def _resize_shape(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    return _geometry_atom(session, params, action="shape.resize")


def _fit_to_slide(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    page = session.page(params["slide"])
    requested_selector = dict(params["selector"])
    resolved_selector = requested_selector
    shape = session.shape(page, resolved_selector)
    mode = params["mode"]
    page_width, page_height = int(page.Width), int(page.Height)
    width, height = int(shape.Size.Width), int(shape.Size.Height)
    if width <= 0 or height <= 0:
        raise AdapterError("CONFLICT", "shape has invalid dimensions")
    if mode == "stretch":
        target_width, target_height = page_width, page_height
    else:
        scale = (max if mode == "cover" else min)(
            page_width / width, page_height / height
        )
        target_width, target_height = round(width * scale), round(height * scale)
    position = shape.Position
    size = shape.Size
    position.X = round((page_width - target_width) / 2)
    position.Y = round((page_height - target_height) / 2)
    size.Width, size.Height = target_width, target_height
    shape.Position, shape.Size = position, size
    summary_path = resolved_selector.get("path")
    summary = (
        _shape_summary_at_path(shape, summary_path)
        if isinstance(summary_path, list)
        else _shape_summary(shape, resolved_selector["index"])
    )
    return {
        **summary,
        "slide": params["slide"],
        "mode": mode,
        "requested_selector": requested_selector,
        "resolved_selector": resolved_selector,
        "selection_basis": "exact_observed_selector",
        "slide_width": page_width,
        "slide_height": page_height,
        "verification_passed": (
            int(shape.Position.X) == round((page_width - target_width) / 2)
            and int(shape.Position.Y) == round((page_height - target_height) / 2)
            and int(shape.Size.Width) == target_width
            and int(shape.Size.Height) == target_height
        ),
    }


def _set_fill(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    shape = session.shape(session.page(params["slide"]), params["selector"])
    shape.FillStyle = _enum("com.sun.star.drawing.FillStyle", "SOLID")
    shape.FillColor = _color(params["color"])
    if "transparency" in params:
        shape.FillTransparence = int(params["transparency"])
    return {"color": int(shape.FillColor), "transparency": int(shape.FillTransparence)}


def _insert_image(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    path = _path_from_input(params["path"])
    if not path.is_file():
        raise AdapterError(
            "FILE_NOT_FOUND", f"image does not exist: {path}", http_status=404
        )
    slide_index = require_slide_index(params, allow_consistent_pair=True)
    page = session.page(slide_index)
    resolved_geometry = resolve_optional_shape_geometry(params)
    shape = session.doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
    page.add(shape)
    shape.Name = path.name
    graphic_url = _file_url(str(path))
    shape.GraphicURL = graphic_url
    uno, _ = _uno_modules()
    shape.Position = uno.createUnoStruct(
        "com.sun.star.awt.Point",
        resolved_geometry.get("x", 0),
        resolved_geometry.get("y", 0),
    )
    shape.Size = uno.createUnoStruct(
        "com.sun.star.awt.Size",
        resolved_geometry.get("width", 2000),
        resolved_geometry.get("height", 2000),
    )
    result = _shape_summary(shape, page.getCount() - 1)
    source_loaded = bool(str(getattr(shape, "GraphicURL", "") or ""))
    result.update(
        {
            "slide": slide_index,
            "display_slide_number": slide_index + 1,
            "requested_path": params["path"],
            "source_path": str(path.resolve()),
            "source_loaded": source_loaded,
            "requested_measurements": {
                field: params[field]
                for field in ("width_measurement", "height_measurement")
                if field in params
            },
            "resolved_geometry": resolved_geometry,
            "verification_passed": (
                source_loaded
                and result.get("name") == path.name
                and "graphicobjectshape" in str(result.get("kind", "")).casefold()
                and all(
                    result.get(field) == value
                    for field, value in resolved_geometry.items()
                )
            ),
        }
    )
    return result


def _delete_shape(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    slide = params["slide"]
    page = session.page(slide)
    shape = session.shape(page, params["selector"])
    path = next(
        (path for path, candidate in _shapes_with_paths(page) if candidate == shape),
        None,
    )
    deleted_shape = {
        "name": str(getattr(shape, "Name", "") or ""),
        "kind": str(
            getattr(shape, "ShapeType", "") or getattr(shape, "ImplementationName", "")
        ),
        "text": _shape_text(shape),
    }
    if path is not None:
        deleted_shape.update({"index": path[-1], "path": path})
    page.remove(shape)
    return {
        "slide": slide,
        "display_slide_number": slide + 1,
        "requested_selector": dict(params["selector"]),
        "deleted_shape": deleted_shape,
        "count": page.getCount(),
        "guidance": (
            "Deleted shape identity describes the object before removal. Remaining "
            "shape indices and paths may have shifted; inspect again before reusing them."
        ),
    }


def _create_table(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    page = session.page(params["slide"])
    placement = params.get("placement", "auto")
    candidates: list[tuple[int, Any]] = []
    if may_use_content_placeholder(params):
        for index in range(page.getCount()):
            shape = page.getByIndex(index)
            if is_empty_content_placeholder(shape, _shape_text(shape)):
                candidates.append((index, shape))
    if placement == "content_placeholder" and len(candidates) != 1:
        code = "PLACEHOLDER_NOT_FOUND" if not candidates else "PLACEHOLDER_AMBIGUOUS"
        raise AdapterError(
            code,
            "table placement requires exactly one empty content placeholder",
            {"candidate_indices": [index for index, _shape in candidates]},
            404 if not candidates else 409,
        )

    placeholder_index: int | None = None
    placeholder = None
    if len(candidates) == 1:
        placeholder_index, placeholder = candidates[0]

    if placeholder is not None:
        x = int(placeholder.Position.X)
        y = int(placeholder.Position.Y)
        width = int(placeholder.Size.Width)
        resolved_placement = "content_placeholder"
    else:
        x = int(params.get("x", 1000))
        y = int(params.get("y", 1000))
        width = int(params.get("width", 10000))
        resolved_placement = "custom"
    height = int(params.get("height", params["rows"] * DEFAULT_TABLE_ROW_HEIGHT))

    table = session.doc.createInstance("com.sun.star.drawing.TableShape")
    page.add(table)
    try:
        model = table.Model
        if params["columns"] > 1:
            model.Columns.insertByIndex(1, params["columns"] - 1)
        if params["rows"] > 1:
            model.Rows.insertByIndex(1, params["rows"] - 1)
        uno, _ = _uno_modules()
        table.Position = uno.createUnoStruct("com.sun.star.awt.Point", x, y)
        table.Size = uno.createUnoStruct("com.sun.star.awt.Size", width, height)
    except Exception:
        page.remove(table)
        raise

    replaced_placeholder = None
    if placeholder is not None:
        replaced_placeholder = {
            "index": placeholder_index,
            "name": str(getattr(placeholder, "Name", "") or ""),
            "kind": str(getattr(placeholder, "ShapeType", "") or ""),
        }
        page.remove(placeholder)

    # UNO may return a fresh Python proxy for the same shape on every collection read.
    # The new table is appended last, and placeholder removal preserves that ordering.
    shape_index = page.getCount() - 1
    return {
        "shape_index": shape_index,
        "rows": model.RowCount,
        "columns": model.ColumnCount,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "placement": resolved_placement,
        "replaced_placeholder": replaced_placeholder,
    }


def _write_table(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    page = session.page(params["slide"])
    shape = session.shape(
        page, params.get("selector", {"index": params.get("shape", 0)})
    )
    model = shape.Model
    written = []
    for cell in params["cells"]:
        if not isinstance(cell, dict):
            raise AdapterError("INVALID_REQUEST", "each table cell must be an object")
        row, column = int(cell["row"]), int(cell["column"])
        target = model.getCellByPosition(column, row)
        target.String = str(cell.get("text", ""))
        if "color" in cell:
            target.CharColor = _color(cell["color"])
        written.append({"row": row, "column": column, "text": target.String})
    return {"cells": written}


def _replace_table_row(
    session: ImpressSession, params: dict[str, Any]
) -> dict[str, Any]:
    slide = require_slide_index(params)
    table = select_unique_live_table(session.page(slide))
    result = replace_live_table_row(
        table,
        row_number=params["row_number"],
        values=params["values"],
    )
    return {
        "slide": slide,
        "display_slide_number": slide + 1,
        **result,
    }


def _table_dimensions(model: Any) -> tuple[int, int]:
    rows = int(getattr(model, "RowCount", model.Rows.getCount()))
    columns = int(getattr(model, "ColumnCount", model.Columns.getCount()))
    return rows, columns


def _table_cell_text(cell: Any) -> Any:
    if hasattr(cell, "getText"):
        return cell.getText()
    text = getattr(cell, "Text", None)
    if text is not None:
        return text
    if hasattr(cell, "createTextCursor") and hasattr(cell, "getString"):
        return cell
    raise AdapterError(
        "UNSUPPORTED_OPERATION",
        "LibreOffice table cell does not expose editable text",
    )


def _read_text_properties(
    text: Any, names: list[str], *, span: tuple[int, int] | None = None
) -> dict[str, Any]:
    cursor = text.createTextCursor()
    cursor.gotoStart(False)
    if span is None:
        cursor.gotoEnd(True)
    else:
        start, length = span
        if start:
            cursor.goRight(start, False)
        cursor.goRight(length, True)
    return {name: cursor.getPropertyValue(name) for name in names}


def _format_table_text(
    session: ImpressSession, params: dict[str, Any]
) -> dict[str, Any]:
    page = session.page(params["slide"])
    shape = session.shape(page, params["selector"])
    return _format_table_shape_text(shape, params)


def _format_table_shape_text(shape: Any, params: dict[str, Any]) -> dict[str, Any]:
    model = getattr(shape, "Model", None)
    if model is None or not hasattr(model, "getCellByPosition"):
        raise AdapterError(
            "UNSUPPORTED_OPERATION",
            "table.format_text requires a table shape",
            {"selector": params["selector"]},
            422,
        )
    rows, columns = _table_dimensions(model)
    requested_cells = params.get("cells")
    coordinates = (
        [(int(cell["row"]), int(cell["column"])) for cell in requested_cells]
        if requested_cells is not None
        else [(row, column) for row in range(rows) for column in range(columns)]
    )
    properties = _text_format_properties(params)
    if "alignment" in params:
        values = {
            "left": "LEFT",
            "center": "CENTER",
            "right": "RIGHT",
            "justify": "BLOCK",
        }
        properties["ParaAdjust"] = _enum(
            "com.sun.star.style.ParagraphAdjust", values[params["alignment"]]
        )

    formatted = []
    for row, column in coordinates:
        if row >= rows or column >= columns:
            raise AdapterError(
                "TABLE_CELL_NOT_FOUND",
                "table cell is outside the table bounds",
                {"row": row, "column": column, "rows": rows, "columns": columns},
                404,
            )
        cell = model.getCellByPosition(column, row)
        text = _table_cell_text(cell)
        _set_text_properties(text, properties)
        observed = _read_text_properties(text, list(properties))
        mismatches = {
            name: {"expected": str(expected), "observed": str(observed[name])}
            for name, expected in properties.items()
            if not _text_property_equivalent(name, observed[name], expected, 0.01)
        }
        if mismatches:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "table text formatting did not persist",
                {"row": row, "column": column, "mismatches": mismatches},
                422,
            )
        formatted.append(
            {
                "row": row,
                "column": column,
                "text": str(text.getString()),
                "properties": {name: str(value) for name, value in observed.items()},
            }
        )
    return {"rows": rows, "columns": columns, "cells": formatted}


def _insert_audio(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    path = _path_from_input(str(params["path"]))
    if not path.is_file():
        raise AdapterError(
            "FILE_NOT_FOUND", f"audio does not exist: {path}", http_status=404
        )
    page = session.page(params["slide"])
    media = session.doc.createInstance("com.sun.star.presentation.MediaShape")
    page.add(media)
    media.MediaURL = _file_url(str(path))
    uno, _ = _uno_modules()
    media.Position = uno.createUnoStruct(
        "com.sun.star.awt.Point", int(params.get("x", 0)), int(params.get("y", 0))
    )
    media.Size = uno.createUnoStruct(
        "com.sun.star.awt.Size",
        int(params.get("width", 4000)),
        int(params.get("height", 2000)),
    )
    return {
        "shape_index": page.getCount() - 1,
        "media_url": media.MediaURL,
        "source_path": str(path),
    }


def _set_page_number(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    masters = session.doc.getMasterPages()
    indices = (
        [int(params["master"])]
        if "master" in params
        else list(range(masters.getCount()))
    )
    requested_color = _color(params["color"]) if "color" in params else None
    results = []
    for master_index in indices:
        master = session.master_page(master_index)
        target = None
        for i in range(master.getCount()):
            shape = master.getByIndex(i)
            if hasattr(shape, "getText") and "<number>" in _shape_text(shape):
                target = shape
                break
        if target is None:
            uno, _ = _uno_modules()
            target = session.doc.createInstance("com.sun.star.drawing.TextShape")
            master.add(target)
            target.Position = uno.createUnoStruct(
                "com.sun.star.awt.Point", 100, max(100, int(master.Height) - 700)
            )
            target.Size = uno.createUnoStruct("com.sun.star.awt.Size", 2500, 500)
            cursor = target.getText().createTextCursor()
            field = session.doc.createInstance("com.sun.star.text.TextField.PageNumber")
            target.getText().insertTextContent(cursor, field, False)
        if requested_color is not None:
            text = target.getText()
            cursor = text.createTextCursor()
            cursor.gotoStart(False)
            cursor.gotoEnd(True)
            cursor.setPropertyValue("CharColor", requested_color)
            paragraphs = target.getText().createEnumeration()
            while paragraphs.hasMoreElements():
                portions = paragraphs.nextElement().createEnumeration()
                while portions.hasMoreElements():
                    portion = portions.nextElement()
                    if getattr(portion, "TextPortionType", "") == "TextField":
                        portion.CharColor = requested_color
        if "visible" in params:
            target.Visible = bool(params["visible"])
        results.append(
            {
                "master": master_index,
                "text": _shape_text(target),
                "color": int(_text_property(target, "CharColor", -1)),
                "visible": bool(getattr(target, "Visible", True)),
            }
        )
    return {"found": bool(results), "masters": results}


def _wait_profile_setting(
    node_path: str, property_name: str, expected: str, timeout: float = 5.0
) -> dict[str, Any]:
    profile = Path.home() / ".config/libreoffice/4/user/registrymodifications.xcu"
    deadline = time.monotonic() + timeout
    observed: str | None = None
    while time.monotonic() < deadline:
        try:
            root = ET.parse(profile).getroot()
            registry = "http://openoffice.org/2001/registry"
            for item in root.findall(".//item"):
                if item.get(f"{{{registry}}}path") != node_path:
                    continue
                for prop in item.findall("prop"):
                    if prop.get(f"{{{registry}}}name") == property_name:
                        value = prop.find("value")
                        observed = value.text if value is not None else None
            if observed == expected:
                return {
                    "path": str(profile),
                    "property": property_name,
                    "value": observed,
                    "persisted": True,
                }
        except (OSError, ET.ParseError):
            pass
        time.sleep(0.1)
    raise AdapterError(
        "VERIFICATION_FAILED",
        f"LibreOffice profile did not persist {property_name}",
        {"path": str(profile), "expected": expected, "observed": observed},
    )


def _slides_view_visible() -> bool:
    try:
        import pyatspi
    except ImportError as exc:
        raise AdapterError(
            "GUI_FALLBACK_UNAVAILABLE",
            "pyatspi is required to verify the Impress slide pane",
            str(exc),
            503,
        ) from exc

    desktop = pyatspi.Registry.getDesktop(0)
    stack = [desktop]
    visited = 0
    while stack and visited < 20_000:
        node = stack.pop()
        visited += 1
        try:
            if node.getRoleName() == "document frame" and node.name == "Slides View":
                return True
            stack.extend(node[i] for i in range(node.childCount))
        except Exception:
            continue
    return False


def _set_left_panel(session: ImpressSession, enabled: bool) -> dict[str, Any]:
    before = _slides_view_visible()
    if before == enabled:
        return {
            "key": "left_panel",
            "enabled": enabled,
            "already_set": True,
            "verified": True,
        }
    try:
        import pyautogui
    except ImportError as exc:
        raise AdapterError(
            "GUI_FALLBACK_UNAVAILABLE",
            "pyautogui is required to toggle the Impress slide pane",
            str(exc),
            503,
        ) from exc
    try:
        session.doc.getCurrentController().getFrame().getContainerWindow().toFront()
    except Exception:
        pass
    # LibreOffice 7.3: View menu -> Slide Pane. The sequence mirrors the
    # version-pinned guest menu and is used only after the stable interfaces
    # proved unable to expose this view setting.
    pyautogui.press("esc")
    pyautogui.press("f10")
    pyautogui.press("right", presses=2, interval=0.1)
    pyautogui.press("down", presses=11, interval=0.1)
    pyautogui.press("enter")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        observed = _slides_view_visible()
        if observed == enabled:
            return {
                "key": "left_panel",
                "enabled": observed,
                "already_set": False,
                "verified": True,
                "fallback": "gui_menu",
            }
        time.sleep(0.1)
    raise AdapterError(
        "VERIFICATION_FAILED",
        "Impress slide pane did not reach the requested state",
        {"expected": enabled, "observed": _slides_view_visible()},
    )


def _settings(session: ImpressSession, params: dict[str, Any]) -> dict[str, Any]:
    key = params.get("key")
    value = params.get("value")
    provider = session.service_manager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", session.context
    )
    if key == "auto_save":
        prop = _property("nodepath", "/org.openoffice.Office.Common/Save/Document")
        access = provider.createInstanceWithArguments(
            "com.sun.star.configuration.ConfigurationUpdateAccess", (prop,)
        )
        access.setPropertyValue("AutoSave", bool(value))
        access.setPropertyValue("AutoSaveTimeIntervall", int(params.get("minutes", 1)))
        access.commitChanges()
        persisted = _wait_profile_setting(
            "/org.openoffice.Office.Common/Save/Document",
            "AutoSaveTimeIntervall",
            str(int(params.get("minutes", 1))),
        )
        return {
            "key": key,
            "enabled": bool(value),
            "minutes": int(params.get("minutes", 1)),
            "profile": persisted,
        }
    if key == "presenter_screen":
        prop = _property("nodepath", "/org.openoffice.Office.Impress/Misc/Start")
        access = provider.createInstanceWithArguments(
            "com.sun.star.configuration.ConfigurationUpdateAccess", (prop,)
        )
        access.setPropertyValue("EnablePresenterScreen", bool(value))
        access.commitChanges()
        persisted = _wait_profile_setting(
            "/org.openoffice.Office.Impress/Misc/Start",
            "EnablePresenterScreen",
            str(bool(value)).lower(),
        )
        return {"key": key, "enabled": bool(value), "profile": persisted}
    if key == "left_panel":
        return _set_left_panel(session, bool(value))
    raise AdapterError("UNSUPPORTED_OPERATION", f"unsupported settings key: {key}")


ACTIONS = {
    "presentation.inspect": _inspect,
    "presentation.create_summary_slide": _presentation_create_summary_slide,
    "presentation.set_page_size": _set_page_size,
    "presentation.save": _save,
    "presentation.export": _export,
    "slide.create": _create_slide,
    "slides.create_from_images": _create_slides_from_images,
    "slide.delete": _delete_slide,
    "slide.duplicate": _duplicate_slide,
    "slide.move": _move_slide,
    "slide.set_background": _set_background,
    "slide.set_transition": _set_transition,
    "slide.set_notes": _set_notes,
    "shape.create_text": _create_text,
    "shape.write_text": _write_text,
    "shape.write_text_native": _write_text_native,
    "shape.format_text": _format_text,
    "slide.set_role_text": _set_role_text,
    "slide.format_text_roles": _format_text_roles,
    "slides.format_text_roles": _format_text_roles,
    "shape.set_geometry": _set_geometry,
    "shape.align_to_slide": _align_to_slide,
    "shape.move": _move_shape,
    "shape.resize": _resize_shape,
    "shape.fit_to_slide": _fit_to_slide,
    "shape.set_fill": _set_fill,
    "shape.insert_image": _insert_image,
    "shape.export_image": _export_shape_image,
    "shape.delete": _delete_shape,
    "table.create": _create_table,
    "table.replace_row": _replace_table_row,
    "table.write": _write_table,
    "table.format_text": _format_table_text,
    "audio.insert": _insert_audio,
    "master.set_page_number": _set_page_number,
    "settings.set": _settings,
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


def _observed(session: ImpressSession, check: dict[str, Any]) -> Any:
    kind = check["type"]
    if kind == "document_identity":
        return session.identity()
    if kind == "slide_count":
        return session.pages.getCount()
    if kind == "page_size":
        return _page_size_state(session)
    if kind in {"slide_properties", "background", "transition", "notes"}:
        summary = _page_summary(session, check["slide"])
        return summary if kind == "slide_properties" else summary[kind]
    if kind in {"shape_properties", "text_properties"}:
        shape = session.shape(session.page(check["slide"]), check["selector"])
        summary = _shape_summary(shape, check["selector"].get("index", -1))
        if kind == "text_properties":
            summary["text"] = _shape_text(shape)
            weight = _text_property(
                shape, "CharWeight", getattr(shape, "CharWeight", 0)
            )
            summary.update(
                {
                    "font_name": str(_text_property(shape, "CharFontName", "")),
                    "font_size": float(_text_property(shape, "CharHeight", 0)),
                    "color": int(_text_property(shape, "CharColor", 0)),
                    "bold": float(weight) >= 150,
                    "underline": _enum_name(
                        _text_property(shape, "CharUnderline", "NONE")
                    ),
                    "strike": _enum_name(
                        _text_property(shape, "CharStrikeout", "NONE")
                    ),
                }
            )
        return summary
    if kind in {"export_file", "file_reopen"}:
        path = Path(check["path"]).expanduser()
        return {
            "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else 0,
            "valid_zip": zipfile.is_zipfile(path) if path.is_file() else False,
        }
    if kind == "settings":
        return {"key": check.get("key"), "path": check.get("path")}
    raise AdapterError("UNSUPPORTED_OPERATION", f"unsupported verifier: {kind}")


def _verify(
    session: ImpressSession, checks: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    results, observed_state, expected_state = [], {}, {}
    all_passed = True
    for index, check in enumerate(checks):
        observed = _observed(session, check)
        expected = check.get("expected")
        passed = expected is None or _equivalent(
            observed, expected, float(check.get("tolerance", 0))
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
        "details": None if all_passed else "one or more checks did not match",
    }


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action not in ACTIONS:
        raise AdapterError("UNSUPPORTED_OPERATION", f"unsupported action: {action}")
    session = ImpressSession(payload.get("document") or {})
    started = time.monotonic()
    params = payload.get("params") or {}
    result = ACTIONS[action](session, params)
    if result.get("verification_passed") is False:
        raise AdapterError(
            "VERIFICATION_FAILED",
            f"{action}: native read-back did not match the requested result. "
            "Partial changes may remain; inspect the selected object and current state before retrying.",
            {
                "action": action,
                "selector": params.get("selector"),
                "observed": result,
                "state_may_have_changed": True,
            },
            422,
        )
    checks = list(payload.get("verify") or [])
    if action == "audio.insert":
        checks.append({
            "type": "shape_properties",
            "slide": params["slide"],
            "selector": {"index": result["shape_index"]},
            "expected": {"media_url": _file_url(str(_path_from_input(params["path"])))},
        })
    if action == "presentation.set_page_size":
        checks.append({
            "type": "page_size",
            "expected": {
                name: [
                    {"width": params["width"], "height": params["height"]}
                    for _ in sizes
                ]
                for name, sizes in result["before"].items()
            },
        })
    verification = _verify(session, checks)
    if action == "audio.insert" and not verification["passed"]:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "audio.insert: native read-back did not match the requested audio. "
            "The inserted object may remain; inspect it before retrying.",
            {
                "action": action,
                "slide": params["slide"],
                "selector": {"index": result["shape_index"]},
                "observed": result,
                "verification": verification,
                "state_may_have_changed": True,
            },
            422,
        )
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
