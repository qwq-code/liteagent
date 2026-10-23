from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import unquote, urlparse
from uuid import uuid4

from .errors import AdapterError


ADAPTER_NAME = "libreoffice_writer"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 180_000
DEFAULT_TIMEOUT_MS = 30_000
TAB_STOP_UNITS = {"mm": 100, "cm": 1000, "in": 2540}
TAB_STOP_ALIGNMENTS = ("left", "right", "center", "decimal")
TEXT_FIND_MAX_LITERAL_LENGTH = 4_096
TEXT_FIND_MAX_RESULTS = 256
TABLE_DELIMITER_PATTERN = r"^[\u0001-\u0009\u000B-\u000C\u000E-\uD7FF\uE000-\uFFFF]$"
CHARACTER_FORMAT_FIELDS = frozenset({"font_size", "bold", "italic", "script"})
RGB_COLOR_PATTERN = (
    r"^(#[0-9A-Fa-f]{6}|black|white|red|green|blue|yellow|orange|purple|"
    r"gr[ae]y|cyan|magenta)$"
)
BOOKMARK_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,39}$"
REFERENCE_DISPLAY_MODES = frozenset(
    {
        "page",
        "chapter",
        "text",
        "above_below",
        "page_style",
        "number",
        "number_no_context",
        "number_full_context",
    }
)
NAMED_RGB_COLORS = {
    "black": 0x000000,
    "white": 0xFFFFFF,
    "red": 0xFF0000,
    "green": 0x008000,
    "blue": 0x0000FF,
    "yellow": 0xFFFF00,
    "orange": 0xFFA500,
    "purple": 0x800080,
    "gray": 0x808080,
    "grey": 0x808080,
    "cyan": 0x00FFFF,
    "magenta": 0xFF00FF,
}
WRITER_IMAGE_SUFFIXES = (
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
)

ACTIONS = frozenset(
    {
        "document.inspect",
        "document.read_file",
        "document.extract_images",
        "document.save",
        "document.export_pdf",
        "document.export_file_pdf",
        "document.set_font",
        "document.transform_case",
        "document.remove_highlighting",
        "document.add_page_numbers",
        "document.insert_page_break",
        "document.append_paragraphs",
        "paragraph.set_format",
        "paragraph.clear_text",
        "paragraph.apply_numbering",
        "paragraph.replace_text",
        "paragraph.split",
        "bookmark.create",
        "cross_reference.insert",
        "text.find",
        "text.find_replace",
        "text.set_format",
        "table.read",
        "table.convert_text",
        "table.insert_at_cursor",
        "table.insert_after_text",
        "table.set_cell_text_color",
        "image.insert_at_cursor",
        "settings.set_default_font",
    }
)

VERIFY_TYPES = frozenset(
    {
        "document_identity",
        "file_saved",
        "paragraphs",
        "text_format",
        "tables",
        "images",
        "page_breaks",
        "page_numbers",
        "pdf",
        "default_font",
    }
)


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    adapter: str
    action: str
    timeout_ms: int
    document: dict[str, Any]
    params: dict[str, Any]
    verify: list[dict[str, Any]]

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "document": self.document,
            "params": self.params,
            "verify": self.verify,
        }


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", f"{field} must be an object")
    return dict(value)


def _string(data: Mapping[str, Any], field: str, prefix: str = "params") -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-empty string"
        )
    return value


def _positive_int(data: Mapping[str, Any], field: str, prefix: str = "params") -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a positive integer"
        )
    return value


def _nonnegative_int(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-negative integer"
        )
    return value


def _text_range_mismatch(
    start: int, end: int, expected: Any, *, nonempty: bool = False
) -> AdapterError:
    text_length = len(expected) if isinstance(expected, str) else None
    guidance = (
        "Offsets are zero-based and end-exclusive; use text.find and copy its "
        "paragraph_index, start_offset, end_offset, and matched_text unchanged "
        "(matched_text becomes expected_text)."
    )
    return AdapterError(
        "INVALID_REQUEST",
        "params offsets must describe the exact "
        + ("nonempty " if nonempty else "")
        + "params.expected_text range. "
        + f"start_offset = {start}; end_offset = {end}; "
        + f"end_offset - start_offset = {end - start}; "
        + f"expected_text length = {text_length if text_length is not None else 'not a string'}. "
        + guidance,
        {
            "start_offset": start,
            "end_offset": end,
            "range_length": end - start,
            "text_length": text_length,
            "offset_basis": "zero_based_end_exclusive",
            "guidance": guidance,
        },
    )


def _number(data: Mapping[str, Any], field: str, prefix: str = "params") -> float:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError("INVALID_REQUEST", f"{prefix}.{field} must be a number")
    return float(value)


def _validate_character_format(params: Any, prefix: str = "params") -> None:
    if not isinstance(params, dict) or not params:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix} requires at least one formatting field"
        )
    unexpected = sorted(set(params) - CHARACTER_FORMAT_FIELDS)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix} received unsupported formatting fields",
            {"unexpected": unexpected, "allowed": sorted(CHARACTER_FORMAT_FIELDS)},
        )
    if "font_size" in params:
        size = _number(params, "font_size", prefix)
        if not math.isfinite(size) or not 1 <= size <= 1000:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{prefix}.font_size must be between 1 and 1000 points",
            )
    for field in ("bold", "italic"):
        if field in params and not isinstance(params[field], bool):
            raise AdapterError("INVALID_REQUEST", f"{prefix}.{field} must be boolean")
    if "script" in params and (
        not isinstance(params["script"], str)
        or params["script"] not in {"normal", "subscript", "superscript"}
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.script must be normal, subscript or superscript",
        )


def parse_rgb_color(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise AdapterError("INVALID_REQUEST", f"{field} must be an RGB color")
    if isinstance(value, int) and 0 <= value <= 0xFFFFFF:
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in NAMED_RGB_COLORS:
            return NAMED_RGB_COLORS[normalized]
        if re.fullmatch(r"#[0-9a-f]{6}", normalized):
            return int(normalized[1:], 16)
    raise AdapterError(
        "INVALID_REQUEST",
        f"{field} must be a common color name, #RRGGBB, or RGB integer",
    )


def _indices(
    data: Mapping[str, Any], field: str = "indices", prefix: str = "params"
) -> None:
    if field not in data:
        return
    value = data[field]
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 0
        for item in value
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.{field} must be an array of non-negative integers",
        )


def _positive_indices(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> None:
    if field not in data:
        return
    value = data[field]
    if (
        not isinstance(value, list)
        or not value
        or len(set(value)) != len(value)
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1
            for item in value
        )
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.{field} must be a non-empty array of unique positive integers",
        )


def _validate_paragraph_spacing_mode(
    paragraphs: list[str], blank_paragraphs_between: int
) -> None:
    if blank_paragraphs_between == 0 or all(value.strip() for value in paragraphs):
        return
    raise AdapterError(
        "INVALID_REQUEST",
        (
            "choose one paragraph-spacing representation: use only non-blank "
            "params.paragraphs strings with positive params.blank_paragraphs_between, "
            "or set params.blank_paragraphs_between to 0 when params.paragraphs "
            "contains blank strings"
        ),
        {
            "conflicting_fields": ["paragraphs", "blank_paragraphs_between"],
            "allowed_modes": [
                {
                    "mode": "automatic_spacing",
                    "paragraphs": "non_blank_strings",
                    "blank_paragraphs_between": "positive_integer",
                },
                {
                    "mode": "explicit_spacing",
                    "paragraphs": "blank_strings_allowed",
                    "blank_paragraphs_between": 0,
                },
            ],
        },
    )


def _table_rows(data: Mapping[str, Any], field: str = "rows") -> None:
    rows = data.get(field)
    if not isinstance(rows, list) or not rows or len(rows) > 200:
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must contain from 1 to 200 rows"
        )
    column_count: int | None = None
    for row_index, row in enumerate(rows):
        if not isinstance(row, list) or not row or len(row) > 100:
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.{field}[{row_index}] must contain from 1 to 100 cells",
            )
        if column_count is None:
            column_count = len(row)
        elif len(row) != column_count:
            raise AdapterError("INVALID_REQUEST", f"params.{field} must be rectangular")
        for column_index, value in enumerate(row):
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field}[{row_index}][{column_index}] must be a scalar or null",
                )


def _validate_document(document: Mapping[str, Any]) -> None:
    for field in ("url", "title"):
        if field in document:
            _string(document, field, "document")


def _local_path(value: str, field: str) -> str:
    if value.startswith(("/", "~/")):
        return value
    parsed = urlparse(value)
    if (
        parsed.scheme == "file"
        and parsed.netloc in {"", "localhost"}
        and unquote(parsed.path).startswith("/")
    ):
        return unquote(parsed.path)
    raise AdapterError(
        "INVALID_REQUEST",
        f"{field} must be an absolute, ~/, or local file URL path",
    )


def _create_from_spreadsheet_params(params: Mapping[str, Any]) -> None:
    allowed = {
        "source_path",
        "sheet",
        "range",
        "output_path",
        "preserve_format",
        "trim_trailing_blank",
        "overwrite",
    }
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "document.create_from_spreadsheet received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    source = _local_path(
        _string(params, "source_path"), "params.source_path"
    ).casefold()
    output = _local_path(
        _string(params, "output_path"), "params.output_path"
    ).casefold()
    if not source.endswith((".csv", ".ods", ".xls", ".xlsx")):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.source_path must identify a CSV, ODS, XLS, or XLSX file",
        )
    if not output.endswith(".docx"):
        raise AdapterError("INVALID_REQUEST", "params.output_path must end in .docx")
    _string(params, "sheet")
    range_ref = _string(params, "range")
    if not re.fullmatch(
        r"\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?",
        range_ref.strip(),
    ):
        raise AdapterError(
            "INVALID_REQUEST", "params.range must be an explicit A1 cell or range"
        )
    for field in ("preserve_format", "trim_trailing_blank", "overwrite"):
        if field in params and not isinstance(params[field], bool):
            raise AdapterError("INVALID_REQUEST", f"params.{field} must be a boolean")


def _create_from_image_params(params: Mapping[str, Any]) -> None:
    allowed = {"source_path", "output_path", "overwrite"}
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "document.create_from_image received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    source = _local_path(
        _string(params, "source_path"), "params.source_path"
    ).casefold()
    output = _local_path(
        _string(params, "output_path"), "params.output_path"
    ).casefold()
    if not source.endswith(WRITER_IMAGE_SUFFIXES):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.source_path must identify a supported raster image",
            {"supported_suffixes": list(WRITER_IMAGE_SUFFIXES)},
        )
    if not output.endswith(".docx"):
        raise AdapterError("INVALID_REQUEST", "params.output_path must end in .docx")
    if "overwrite" in params and not isinstance(params["overwrite"], bool):
        raise AdapterError("INVALID_REQUEST", "params.overwrite must be a boolean")


def _create_from_text_files_params(params: Mapping[str, Any]) -> None:
    allowed = {
        "input_paths",
        "output_path",
        "separator",
        "font_size",
        "overwrite",
    }
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "document.create_from_text_files received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    input_paths = params.get("input_paths")
    if (
        not isinstance(input_paths, list)
        or not 1 <= len(input_paths) <= 256
        or any(not isinstance(path, str) or not path.strip() for path in input_paths)
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.input_paths must contain from 1 to 256 non-empty paths",
        )
    for index, path in enumerate(input_paths):
        _local_path(path, f"params.input_paths[{index}]")
    output = _local_path(
        _string(params, "output_path"), "params.output_path"
    ).casefold()
    if not output.endswith(".docx"):
        raise AdapterError("INVALID_REQUEST", "params.output_path must end in .docx")
    separator = params.get("separator")
    if not isinstance(separator, str) or len(separator) > 10_000:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.separator must be a string of at most 10000 characters",
        )
    font_size = params.get("font_size")
    if (
        isinstance(font_size, bool)
        or not isinstance(font_size, (int, float))
        or not 1 <= float(font_size) <= 1000
    ):
        raise AdapterError(
            "INVALID_REQUEST", "params.font_size must be a number from 1 to 1000"
        )
    if "overwrite" in params and not isinstance(params["overwrite"], bool):
        raise AdapterError("INVALID_REQUEST", "params.overwrite must be a boolean")


def _extract_images_params(params: Mapping[str, Any]) -> None:
    allowed = {"source_path", "output_directory", "selection", "overwrite"}
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "document.extract_images received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    source = _local_path(
        _string(params, "source_path"), "params.source_path"
    ).casefold()
    _local_path(_string(params, "output_directory"), "params.output_directory")
    if not source.endswith((".docx", ".odt")):
        raise AdapterError(
            "INVALID_REQUEST", "params.source_path must end in .docx or .odt"
        )
    if params.get("selection", "all") not in {"first", "all"}:
        raise AdapterError("INVALID_REQUEST", "params.selection must be first or all")
    if "overwrite" in params and not isinstance(params["overwrite"], bool):
        raise AdapterError("INVALID_REQUEST", "params.overwrite must be a boolean")


def _create_from_presentation_params(params: Mapping[str, Any]) -> None:
    allowed = {
        "source_path",
        "output_path",
        "include_notes",
        "include_auto_fields",
        "overwrite",
    }
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "document.create_from_presentation received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    source = _local_path(
        _string(params, "source_path"), "params.source_path"
    ).casefold()
    output = _local_path(
        _string(params, "output_path"), "params.output_path"
    ).casefold()
    if not source.endswith((".odp", ".ppt", ".pptx")):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.source_path must identify an ODP, PPT, or PPTX presentation",
        )
    if not output.endswith(".docx"):
        raise AdapterError("INVALID_REQUEST", "params.output_path must end in .docx")
    for field in ("include_notes", "include_auto_fields", "overwrite"):
        if field in params and not isinstance(params[field], bool):
            raise AdapterError("INVALID_REQUEST", f"params.{field} must be a boolean")


def _validate_verify(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdapterError("INVALID_REQUEST", "verify must be an array")
    checks = []
    for index, raw in enumerate(value):
        check = _mapping(raw, f"verify[{index}]")
        if check.get("type") not in VERIFY_TYPES:
            raise AdapterError(
                "INVALID_REQUEST", f"verify[{index}].type is unsupported"
            )
        checks.append(check)
    return checks


PARAGRAPH_FORMAT_FIELDS = frozenset(
    {"line_spacing", "alignment", "font_size", "strikethrough", "tab_stops"}
)


def _validate_tab_stops(value: Any, prefix: str) -> None:
    if not isinstance(value, list):
        raise AdapterError("INVALID_REQUEST", f"{prefix} must be an array")
    for index, raw in enumerate(value):
        field = f"{prefix}[{index}]"
        stop = _mapping(raw, field)
        allowed = {"position", "alignment", "decimal_character", "fill_character"}
        if not {"position", "alignment"}.issubset(stop) or set(stop) - allowed:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field} requires position and alignment; optional fields are "
                "decimal_character and fill_character",
            )
        position = _mapping(stop["position"], f"{field}.position")
        if set(position) != {"value", "unit"}:
            raise AdapterError(
                "INVALID_REQUEST", f"{field}.position requires value and unit"
            )
        unit = position["unit"]
        if not isinstance(unit, str) or unit not in TAB_STOP_UNITS:
            raise AdapterError(
                "INVALID_REQUEST", f"{field}.position.unit must be mm, cm, or in"
            )
        number = _number(position, "value", f"{field}.position")
        if (
            not math.isfinite(number)
            or not 0 <= number * TAB_STOP_UNITS[unit] <= 2**31 - 1
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field}.position must be finite, non-negative, and fit Writer's position range",
            )
        if stop["alignment"] not in TAB_STOP_ALIGNMENTS:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field}.alignment must be left, right, center, or decimal",
            )
        for name in ("decimal_character", "fill_character"):
            if name in stop and (
                not isinstance(stop[name], str) or len(stop[name]) != 1
            ):
                raise AdapterError(
                    "INVALID_REQUEST", f"{field}.{name} must be one character"
                )


def _validate_paragraph_format_fields(data: Mapping[str, Any], prefix: str) -> None:
    if not PARAGRAPH_FORMAT_FIELDS.intersection(data):
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix} requires at least one format field"
        )
    if "line_spacing" in data and _number(data, "line_spacing", prefix) <= 0:
        raise AdapterError("INVALID_REQUEST", f"{prefix}.line_spacing must be positive")
    if "alignment" in data and data["alignment"] not in {
        "left",
        "center",
        "right",
        "justify",
    }:
        raise AdapterError("INVALID_REQUEST", f"{prefix}.alignment is unsupported")
    if "font_size" in data and _number(data, "font_size", prefix) <= 0:
        raise AdapterError("INVALID_REQUEST", f"{prefix}.font_size must be positive")
    if "strikethrough" in data and not isinstance(data["strikethrough"], bool):
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.strikethrough must be a boolean"
        )
    if "tab_stops" in data:
        _validate_tab_stops(data["tab_stops"], f"{prefix}.tab_stops")


def validate_action_params(action: str, params: Mapping[str, Any]) -> None:
    if action == "document.inspect":
        if "paragraph_start" in params:
            _nonnegative_int(params, "paragraph_start")
        if "paragraph_limit" in params:
            if _positive_int(params, "paragraph_limit") > 12:
                raise AdapterError(
                    "INVALID_REQUEST", "params.paragraph_limit must be at most 12"
                )
    elif action == "document.read_file":
        unexpected = set(params).difference({"path", "start_char", "max_chars"})
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "document.read_file received unsupported parameters",
                {"unsupported": sorted(unexpected)},
            )
        _local_path(_string(params, "path"), "params.path")
        if "start_char" in params:
            _nonnegative_int(params, "start_char")
        if "max_chars" in params and _positive_int(params, "max_chars") > 12000:
            raise AdapterError(
                "INVALID_REQUEST", "params.max_chars must be at most 12000"
            )
    elif action == "document.extract_images":
        _extract_images_params(params)
    elif action == "document.export_file_pdf":
        allowed = {"source_path", "output_path", "preserve_soft_wrap_spaces"}
        if set(params) - allowed:
            raise AdapterError(
                "INVALID_REQUEST", "document.export_file_pdf received unsupported parameters"
            )
        _local_path(_string(params, "source_path"), "params.source_path")
        output = _string(params, "output_path")
        _local_path(output, "params.output_path")
        if not output.lower().endswith(".pdf"):
            raise AdapterError("INVALID_REQUEST", "params.output_path must end in .pdf")
        if "preserve_soft_wrap_spaces" in params and not isinstance(
            params["preserve_soft_wrap_spaces"], bool
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.preserve_soft_wrap_spaces must be a boolean"
            )
    elif action == "document.export_pdf":
        has_path = "path" in params
        has_same_basename = "same_basename" in params
        if has_path == has_same_basename:
            raise AdapterError(
                "INVALID_REQUEST",
                "document.export_pdf requires exactly one of params.path or "
                "params.same_basename",
            )
        if has_path:
            path = _string(params, "path")
            if not path.lower().endswith(".pdf"):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.path must be a PDF destination ending in .pdf; "
                    "keep the source document path separate, or use "
                    "params.same_basename=true to export beside the active document",
                )
        elif params["same_basename"] is not True:
            raise AdapterError("INVALID_REQUEST", "params.same_basename must be true")
        if "preserve_soft_wrap_spaces" in params and not isinstance(
            params["preserve_soft_wrap_spaces"], bool
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.preserve_soft_wrap_spaces must be a boolean",
            )
    elif action == "document.set_font":
        _string(params, "font_name")
    elif action == "document.transform_case":
        if params.get("mode") not in {"lower", "title"}:
            raise AdapterError("INVALID_REQUEST", "params.mode must be lower or title")
    elif action == "document.add_page_numbers":
        if params.get("position", "bottom_left") not in {
            "bottom_left",
            "bottom_center",
            "bottom_right",
        }:
            raise AdapterError("INVALID_REQUEST", "params.position is unsupported")
    elif action == "paragraph.set_format":
        _indices(params)
        _positive_indices(params, "nonempty_ordinals")
        if "indices" in params and "nonempty_ordinals" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "paragraph.set_format accepts either params.indices or "
                "params.nonempty_ordinals, not both",
            )
        _validate_paragraph_format_fields(params, "params")
    elif action == "paragraph.clear_text":
        if set(params) != {"indices"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "paragraph.clear_text requires only params.indices; "
                "select every paragraph explicitly",
            )
        _indices(params)
        indices = params["indices"]
        if not indices or len(set(indices)) != len(indices):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.indices must be a non-empty array of unique raw paragraph indices",
            )
    elif action == "paragraph.apply_numbering":
        allowed = {"source_index", "target_index", "level", "restart", "start_value"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "paragraph.apply_numbering received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        source_index = _nonnegative_int(params, "source_index")
        target_index = _nonnegative_int(params, "target_index")
        if source_index == target_index:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.source_index and params.target_index must be different",
            )
        level = _nonnegative_int(params, "level")
        if level > 9:
            raise AdapterError(
                "INVALID_REQUEST", "params.level must be an integer from 0 to 9"
            )
        restart = params.get("restart")
        if not isinstance(restart, bool):
            raise AdapterError("INVALID_REQUEST", "params.restart must be a boolean")
        if restart:
            _positive_int(params, "start_value")
        elif "start_value" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.start_value is only valid when params.restart is true",
            )
    elif action == "paragraph.replace_text":
        _nonnegative_int(params, "index")
        paragraphs = params.get("paragraphs")
        if (
            not isinstance(paragraphs, list)
            or not paragraphs
            or len(paragraphs) > 256
            or any(not isinstance(value, str) for value in paragraphs)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.paragraphs must contain 1 to 256 explicit strings",
            )
        blank_between = params.get("blank_paragraphs_between", 0)
        if (
            isinstance(blank_between, bool)
            or not isinstance(blank_between, int)
            or not 0 <= blank_between <= 10
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.blank_paragraphs_between must be an integer from 0 to 10",
            )
        _validate_paragraph_spacing_mode(paragraphs, blank_between)
    elif action == "paragraph.split":
        allowed = {"index", "after_text", "blank_paragraphs_between"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "paragraph.split received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        _nonnegative_int(params, "index")
        after_text = params.get("after_text")
        anchors = [after_text] if isinstance(after_text, str) else after_text
        if (
            not isinstance(anchors, list)
            or not 1 <= len(anchors) <= 32
            or any(
                not isinstance(anchor, str)
                or not 1 <= len(anchor) <= TEXT_FIND_MAX_LITERAL_LENGTH
                for anchor in anchors
            )
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.after_text must be one literal or an ordered list of 1 to 32 "
                "literals, each containing 1 to 4096 characters",
            )
        blank_between = params.get("blank_paragraphs_between", 0)
        if (
            isinstance(blank_between, bool)
            or not isinstance(blank_between, int)
            or not 0 <= blank_between <= 10
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.blank_paragraphs_between must be an integer from 0 to 10",
            )
    elif action == "text.set_format":
        allowed = {
            "paragraph_index",
            "start_offset",
            "end_offset",
            "expected_text",
        } | CHARACTER_FORMAT_FIELDS
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "text.set_format received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        _nonnegative_int(params, "paragraph_index")
        start = _nonnegative_int(params, "start_offset")
        end = _nonnegative_int(params, "end_offset")
        expected = params.get("expected_text")
        if (
            not isinstance(expected, str)
            or end <= start
            or len(expected) != end - start
        ):
            raise _text_range_mismatch(start, end, expected, nonempty=True)
        _validate_character_format(
            {key: params[key] for key in CHARACTER_FORMAT_FIELDS if key in params}
        )
    elif action == "bookmark.create":
        allowed = {
            "name",
            "paragraph_index",
            "start_offset",
            "end_offset",
            "expected_text",
        }
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "bookmark.create received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        name = _string(params, "name")
        if re.fullmatch(BOOKMARK_NAME_PATTERN, name) is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.name must be a portable Writer bookmark name",
            )
        _nonnegative_int(params, "paragraph_index")
        start_offset = _nonnegative_int(params, "start_offset")
        end_offset = _nonnegative_int(params, "end_offset")
        expected_text = params.get("expected_text")
        if not isinstance(expected_text, str):
            raise AdapterError(
                "INVALID_REQUEST", "params.expected_text must be a string"
            )
        if end_offset < start_offset or len(expected_text) != end_offset - start_offset:
            raise _text_range_mismatch(start_offset, end_offset, expected_text)
    elif action == "cross_reference.insert":
        allowed = {
            "bookmark_name",
            "paragraph_index",
            "start_offset",
            "end_offset",
            "expected_text",
            "display",
        }
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "cross_reference.insert received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        bookmark_name = _string(params, "bookmark_name")
        if re.fullmatch(BOOKMARK_NAME_PATTERN, bookmark_name) is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.bookmark_name must be a portable Writer bookmark name",
            )
        _nonnegative_int(params, "paragraph_index")
        start_offset = _nonnegative_int(params, "start_offset")
        end_offset = _nonnegative_int(params, "end_offset")
        expected_text = params.get("expected_text")
        if not isinstance(expected_text, str):
            raise AdapterError(
                "INVALID_REQUEST", "params.expected_text must be a string"
            )
        if end_offset < start_offset or len(expected_text) != end_offset - start_offset:
            raise _text_range_mismatch(start_offset, end_offset, expected_text)
        if params.get("display") not in REFERENCE_DISPLAY_MODES:
            raise AdapterError("INVALID_REQUEST", "params.display is unsupported")
    elif action == "text.find":
        allowed = {"literal", "case_sensitive", "max_results", "format"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "text.find received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        if "literal" not in params and "format" not in params:
            raise AdapterError(
                "INVALID_REQUEST", "params requires literal or format search criteria"
            )
        if "literal" in params:
            literal = params["literal"]
            if not isinstance(literal, str) or not literal:
                raise AdapterError(
                    "INVALID_REQUEST", "params.literal must be a non-empty string"
                )
            if len(literal) > TEXT_FIND_MAX_LITERAL_LENGTH:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.literal must contain at most {TEXT_FIND_MAX_LITERAL_LENGTH} characters",
                )
        if ("literal" in params or "case_sensitive" in params) and not isinstance(
            params.get("case_sensitive"), bool
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.case_sensitive must be a boolean"
            )
        if "format" in params:
            _validate_character_format(params["format"], "params.format")
        if _positive_int(params, "max_results") > TEXT_FIND_MAX_RESULTS:
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.max_results must not exceed {TEXT_FIND_MAX_RESULTS}",
            )
    elif action == "text.find_replace":
        _string(params, "find")
        if not isinstance(params.get("replacement"), str):
            raise AdapterError("INVALID_REQUEST", "params.replacement must be a string")
        for field in ("replace_all", "case_sensitive"):
            if not isinstance(params.get(field), bool):
                raise AdapterError(
                    "INVALID_REQUEST", f"params.{field} must be a boolean"
                )
    elif action == "table.convert_text":
        allowed = {"start_index", "end_index", "delimiter"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "table.convert_text received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        start_index = _nonnegative_int(params, "start_index")
        end_index = _nonnegative_int(params, "end_index")
        if end_index < start_index:
            raise AdapterError(
                "INVALID_REQUEST", "params.end_index must not precede params.start_index"
            )
        delimiter = params.get("delimiter")
        if not isinstance(delimiter, str) or re.fullmatch(TABLE_DELIMITER_PATTERN, delimiter) is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.delimiter must be one BMP character other than NUL or a paragraph break",
            )
    elif action == "table.insert_at_cursor":
        _positive_int(params, "rows")
        _positive_int(params, "columns")
        if "fallback_to_last_paragraph" in params and not isinstance(
            params["fallback_to_last_paragraph"], bool
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.fallback_to_last_paragraph must be a boolean",
            )
    elif action == "table.insert_after_text":
        allowed = {"anchor_text", "rows", "match_mode", "case_sensitive"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "table.insert_after_text received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        _string(params, "anchor_text")
        _table_rows(params)
        if params.get("match_mode", "exact") not in {"exact", "contains"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.match_mode must be exact or contains"
            )
        if "case_sensitive" in params and not isinstance(
            params["case_sensitive"], bool
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.case_sensitive must be a boolean"
            )
    elif action == "table.read":
        _string(params, "name")
    elif action == "table.set_cell_text_color":
        _string(params, "name")
        cells = params.get("cells")
        if (
            not isinstance(cells, list)
            or not cells
            or len(cells) > 1024
            or any(not isinstance(value, str) or not value.strip() for value in cells)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cells must contain 1 to 1024 nonempty table cell names",
            )
        parse_rgb_color(params.get("color"), "params.color")
    elif action == "image.insert_at_cursor":
        _string(params, "path")
    elif action == "document.append_paragraphs":
        paragraphs = params.get("paragraphs")
        if (
            not isinstance(paragraphs, list)
            or not paragraphs
            or len(paragraphs) > 256
            or any(not isinstance(value, str) for value in paragraphs)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.paragraphs must contain 1 to 256 explicit strings",
            )
        for field in ("blank_paragraphs_before", "blank_paragraphs_between"):
            value = params.get(field, 0)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= 10
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be an integer from 0 to 10",
                )
        _validate_paragraph_spacing_mode(
            paragraphs, params.get("blank_paragraphs_between", 0)
        )
    elif action == "settings.set_default_font":
        _string(params, "font_name")


def parse_action_request(payload: Any) -> ActionRequest:
    data = _mapping(payload, "request")
    request_id = data.get("request_id") or str(uuid4())
    if not isinstance(request_id, str) or not request_id.strip():
        raise AdapterError("INVALID_REQUEST", "request_id must be a non-empty string")
    adapter = data.get("adapter", ADAPTER_NAME)
    if adapter != ADAPTER_NAME:
        raise AdapterError(
            "INVALID_REQUEST",
            "adapter does not match this service",
            {"expected": ADAPTER_NAME, "actual": adapter},
        )
    action = data.get("action")
    if action not in ACTIONS:
        raise AdapterError(
            "UNSUPPORTED_OPERATION", "action is not supported", {"action": action}
        )
    timeout_ms = data.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
        raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
    if not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS:
        raise AdapterError(
            "INVALID_REQUEST",
            f"timeout_ms must be between {MIN_TIMEOUT_MS} and {MAX_TIMEOUT_MS}",
        )
    document = _mapping(data.get("document"), "document")
    _validate_document(document)
    params = _mapping(data.get("params"), "params")
    validate_action_params(action, params)
    verify = _validate_verify(data.get("verify"))
    return ActionRequest(
        request_id, adapter, action, timeout_ms, document, params, verify
    )
