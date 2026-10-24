from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from .errors import AdapterError


ADAPTER_NAME = "libreoffice_calc"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 120_000
DEFAULT_TIMEOUT_MS = 30_000

ACTIONS = frozenset(
    {
        "workbook.inspect",
        "workbook.read_file",
        "workbook.create_new",
        "workbook.save",
        "workbook.export",
        "workbook.convert_file",
        "sheet.create",
        "sheet.rename",
        "sheet.copy",
        "sheet.move",
        "range.read",
        "range.write",
        "cells.set_formulas",
        "range.copy",
        "range.fill_down",
        "range.text_transform",
        "range.merge",
        "range.format",
        "range.set_scaled_display",
        "range.set_decimal_separator",
        "range.set_validation",
        "table.sort",
        "table.reorder_columns",
        "rows.set_hidden",
        "chart.create",
        "pivot.create",
        "view.set_zoom",
        "view.freeze_panes",
        "view.freeze_range",
        "page.fit_to_pages",
    }
)

VERIFY_TYPES = frozenset(
    {
        "document_identity",
        "sheet_names",
        "range_values",
        "range_formulas",
        "range_display_text",
        "range_styles",
        "merged_ranges",
        "row_hidden",
        "data_validation",
        "chart_properties",
        "pivot_properties",
        "zoom",
        "freeze_panes",
        "export_file",
        "file_reopen",
    }
)

CELL_KINDS = frozenset(
    {"blank", "string", "number", "boolean", "date", "formula", "formatted_text"}
)

CELL_REFERENCE_PATTERN = re.compile(
    r"^(?:(?:[A-Za-z_][A-Za-z0-9_]*|'(?:[^']|'')+')\.)?"
    r"\$?[A-Za-z]{1,4}\$?[1-9][0-9]*$"
)

# range.read accepts one unqualified, contiguous A1 rectangle.  Separate this
# from cell references so invalid multi-area reads receive a useful Adapter
# error instead of a backend UNO exception.
A1_RANGE_PATTERN = re.compile(
    r"^\$?[A-Za-z]{1,4}\$?[1-9][0-9]*"
    r"(?::\$?[A-Za-z]{1,4}\$?[1-9][0-9]*)?$"
)


def explicit_format_ranges(value: Any) -> tuple[str, ...] | None:
    """Interpret only the declared comma-separated A1 format selection."""
    if not isinstance(value, str) or "," not in value:
        return None
    members = tuple(member.strip() for member in value.split(","))
    if all(A1_RANGE_PATTERN.fullmatch(member) for member in members):
        return members
    return None


PIVOT_DESTINATION_SCHEMA = {
    "description": (
        "One A1 anchor, or a relative anchor below an explicit range in destination_sheet. "
        "For stacked tables, use below_range from the preceding output_range and set "
        "blank_rows to the requested gap; the Adapter converts this position to A1. "
        "Use zero to place immediately below a title or another range. Table-to-table "
        "spacing does not require an extra margin between the title and the first table."
    ),
    "oneOf": [
        {"type": "string", "pattern": r"^\$?[A-Za-z]{1,4}\$?[1-9][0-9]*$"},
        {
            "type": "object",
            "properties": {
                "below_range": {
                    "type": "string",
                    "pattern": A1_RANGE_PATTERN.pattern,
                    "description": (
                        "Explicit A1 cell or rectangle in destination_sheet. Place below "
                        "its last row, aligned to its leftmost column; no content search."
                    ),
                },
                "blank_rows": {"type": "integer", "minimum": 0},
            },
            "required": ["below_range", "blank_rows"],
            "additionalProperties": False,
        },
    ],
}


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


def _verification(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdapterError("INVALID_REQUEST", "verify must be an array")
    checks: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        check = _mapping(raw, f"verify[{index}]")
        check_type = check.get("type")
        if check_type not in VERIFY_TYPES:
            raise AdapterError(
                "INVALID_REQUEST",
                f"verify[{index}].type is unsupported",
                {"type": check_type},
            )
        if "tolerance" in check:
            tolerance = check["tolerance"]
            if (
                isinstance(tolerance, bool)
                or not isinstance(tolerance, (int, float))
                or tolerance < 0
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"verify[{index}].tolerance must be a non-negative number",
                )
        if check_type.startswith("range_") or check_type == "data_validation":
            _required_string(check, "sheet", prefix=f"verify[{index}]")
            _required_a1_range(check, prefix=f"verify[{index}]")
        elif check_type in {
            "chart_properties",
            "pivot_properties",
            "zoom",
            "freeze_panes",
        }:
            _required_string(check, "sheet", prefix=f"verify[{index}]")
        elif check_type == "merged_ranges":
            _required_string(check, "sheet", prefix=f"verify[{index}]")
            _string_list(check, "ranges", prefix=f"verify[{index}]")
        elif check_type == "row_hidden":
            _required_string(check, "sheet", prefix=f"verify[{index}]")
            rows = check.get("rows")
            if (
                not isinstance(rows, list)
                or not rows
                or any(
                    isinstance(row, bool) or not isinstance(row, int) or row < 1
                    for row in rows
                )
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"verify[{index}].rows must be a non-empty array of 1-based row numbers",
                )
        elif check_type in {"export_file", "file_reopen"}:
            _required_string(check, "path", prefix=f"verify[{index}]")
        if "persisted" in check:
            _optional_bool(check, "persisted", prefix=f"verify[{index}]")
        checks.append(check)
    return checks


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
            "UNSUPPORTED_OPERATION",
            "action is not supported",
            {"action": action},
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
    for field in ("url", "title"):
        if field in document:
            _required_string(document, field, prefix="document")

    request = ActionRequest(
        request_id=request_id,
        adapter=adapter,
        action=action,
        timeout_ms=timeout_ms,
        document=document,
        params=_mapping(data.get("params"), "params"),
        verify=_verification(data.get("verify")),
    )
    validate_action_params(request.action, request.params)
    return request


def _required_string(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-empty string"
        )
    return value


def _required_a1_range(
    data: Mapping[str, Any], field: str = "range", prefix: str = "params"
) -> str:
    value = _required_string(data, field, prefix=prefix)
    if not A1_RANGE_PATTERN.fullmatch(value.strip()):
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.{field} must be one contiguous A1 range such as A1 or A1:B2; "
            "do not join non-contiguous ranges with commas; use separate calls",
            {field: value},
        )
    return value


def _optional_index(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> None:
    value = data.get(field)
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-negative integer"
        )


def _optional_bool(data: Mapping[str, Any], field: str, prefix: str = "params") -> None:
    if field in data and not isinstance(data[field], bool):
        raise AdapterError("INVALID_REQUEST", f"{prefix}.{field} must be a boolean")


def _optional_string(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> None:
    if field in data:
        _required_string(data, field, prefix=prefix)


def _string_list(
    data: Mapping[str, Any],
    field: str,
    *,
    required: bool = True,
    prefix: str = "params",
) -> list[str]:
    value = data.get(field)
    if not required and (value is None or value == []):
        return []
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-empty string array"
        )
    return value


def _validate_bool_options(params: Mapping[str, Any], *fields: str) -> None:
    for field in fields:
        _optional_bool(params, field)


def _validate_plain_table(params: Mapping[str, Any]) -> None:
    has_headers = "headers" in params
    has_rows = "rows" in params
    if has_rows and not has_headers:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.rows requires params.headers",
        )
    if not has_headers:
        return
    headers = _string_list(params, "headers")
    if len(headers) > 256 or len(headers) != len(set(headers)):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.headers must contain at most 256 unique names",
        )
    if not has_rows:
        return
    rows = params["rows"]
    if not isinstance(rows, list) or len(rows) > 10_000:
        raise AdapterError(
            "INVALID_REQUEST", "params.rows must be an array of at most 10000 rows"
        )
    for row_index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(headers):
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.rows[{row_index}] must contain exactly {len(headers)} values",
            )
        for column_index, value in enumerate(row):
            valid = value is None or isinstance(value, (str, int, float, bool))
            if isinstance(value, float) and not math.isfinite(value):
                valid = False
            if not valid:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.rows[{row_index}][{column_index}] must be a JSON scalar or null",
                )


def _validate_format(spec: Mapping[str, Any]) -> None:
    allowed = {
        "background_color",
        "font_color",
        "bold",
        "number_format",
        "locale",
        "horizontal_alignment",
        "vertical_alignment",
    }
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise AdapterError(
            "INVALID_REQUEST", "params.format contains unsupported fields", unknown
        )
    for field in ("background_color", "font_color"):
        if field in spec:
            value = spec[field]
            valid = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= 0xFFFFFF
            )
            if isinstance(value, str):
                raw = value.removeprefix("#")
                valid = len(raw) == 6 and all(
                    character in "0123456789abcdefABCDEF" for character in raw
                )
            if not valid:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.format.{field} must be #RRGGBB or an RGB integer",
                )
    _optional_bool(spec, "bold", prefix="params.format")
    _optional_string(spec, "number_format", prefix="params.format")
    _optional_string(spec, "locale", prefix="params.format")
    choices = {
        "horizontal_alignment": {"left", "center", "right", "standard"},
        "vertical_alignment": {"top", "center", "bottom", "standard"},
    }
    for field, allowed_values in choices.items():
        if field in spec and (
            not isinstance(spec[field], str)
            or spec[field].lower() not in allowed_values
        ):
            raise AdapterError(
                "INVALID_REQUEST", f"params.format.{field} is unsupported"
            )


def _validate_pivot_fields(
    params: Mapping[str, Any], *, prefix: str = "params", require_name: bool = True
) -> None:
    if require_name:
        _required_string(params, "name", prefix=prefix)
    orientation_fields = []
    for field in ("row_fields", "column_fields", "page_fields"):
        values = _string_list(params, field, prefix=prefix, required=False)
        orientation_fields.extend(values)
    if len(orientation_fields) != len(set(orientation_fields)):
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix} pivot orientation fields must be unique"
        )
    data_fields = params.get("data_fields")
    if not isinstance(data_fields, list) or not data_fields:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.data_fields must be a non-empty array"
        )
    functions = {"sum", "count", "average", "max", "min"}
    show_types = {
        "none",
        "item_difference",
        "item_percentage",
        "item_percentage_difference",
        "running_total",
        "row_percentage",
        "column_percentage",
        "total_percentage",
        "index",
    }
    for index, spec in enumerate(data_fields):
        normalized = normalize_pivot_data_field(spec, index=index)
        if normalized["function"] not in functions:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{prefix}.data_fields[{index}].aggregation is unsupported",
            )
        if normalized["show_data_as"] not in show_types:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{prefix}.data_fields[{index}].show_data_as value is unsupported; "
                f"choose one of: {', '.join(sorted(show_types))}",
            )
        _optional_string(
            spec, "reference_field", prefix=f"{prefix}.data_fields[{index}]"
        )
        _optional_string(
            spec, "reference_item", prefix=f"{prefix}.data_fields[{index}]"
        )


def validate_action_params(action: str, params: Mapping[str, Any]) -> None:
    """Validate the stable action surface before starting a UNO subprocess."""
    if action not in ACTIONS:
        raise AdapterError(
            "UNSUPPORTED_OPERATION",
            "action is not supported",
            {"action": action},
        )

    range_actions = {
        "range.read",
        "range.write",
        "range.merge",
        "range.format",
        "range.set_scaled_display",
        "range.set_decimal_separator",
        "range.set_validation",
    }
    if action in range_actions:
        _required_string(params, "sheet")
        if action == "range.read":
            _required_a1_range(params)
        else:
            _required_string(params, "range")

    if action == "range.write":
        validate_typed_matrix(params.get("values"))
    elif action == "cells.set_formulas":
        _required_string(params, "sheet")
        writes = params.get("writes")
        if not isinstance(writes, list) or not 1 <= len(writes) <= 256:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.writes must be an array of 1 to 256 explicit cell formulas",
            )
        seen_cells: set[str] = set()
        for index, raw_write in enumerate(writes):
            write = _mapping(raw_write, f"params.writes[{index}]")
            if set(write) != {"cell", "formula"}:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.writes[{index}] must contain only cell and formula",
                )
            cell = write.get("cell")
            if not isinstance(cell, str) or not re.fullmatch(
                r"\$?[A-Za-z]{1,4}\$?[1-9][0-9]*", cell.strip()
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.writes[{index}].cell must be one unqualified A1 cell",
                )
            normalized_cell = cell.replace("$", "").upper()
            if normalized_cell in seen_cells:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.writes[{index}].cell duplicates an earlier cell",
                )
            seen_cells.add(normalized_cell)
            formula = write.get("formula")
            if not isinstance(formula, str) or not formula.startswith("="):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.writes[{index}].formula must start with '='",
                )
    elif action == "workbook.read_file":
        path = _required_string(params, "path")
        if not path.startswith(("/", "~/", "file:///")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.path must be an absolute local path, a ~/ path, or a file URL",
            )
        suffix = path.lower().rsplit(".", 1)[-1] if "." in path else ""
        if suffix not in {"csv", "ods", "xlsx"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.path must end in .csv, .ods, or .xlsx"
            )
        _optional_string(params, "sheet")
        _optional_string(params, "range")
        for field, maximum in (
            ("start_row", 1_048_576),
            ("start_column", 16_384),
            ("max_rows", 1_000),
            ("max_columns", 256),
            ("max_sheets", 32),
        ):
            if field not in params:
                continue
            value = params[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= maximum
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be an integer from 1 to {maximum}",
                )
        if "range" in params and any(
            field in params for field in ("start_row", "start_column")
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.range cannot be combined with params.start_row or params.start_column",
            )
    elif action == "workbook.create_new":
        output_path = _required_string(params, "output_path")
        if not output_path.startswith(("/", "~/", "file:///")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.output_path must be an absolute local path, a ~/ path, or a file URL",
            )
        suffix = output_path.lower().rsplit(".", 1)[-1] if "." in output_path else ""
        if suffix not in {"ods", "xlsx"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.output_path must end in .ods or .xlsx"
            )
        _optional_string(params, "sheet_name")
        _optional_bool(params, "overwrite")
        _validate_plain_table(params)
    elif action == "workbook.save":
        _optional_string(params, "url")
        _optional_string(params, "filter_name")
        if "url" in params and not re.fullmatch(
            r"(?:/|~/|file:///).+\.(?:ods|xlsx)", params["url"], re.IGNORECASE
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.url must be an absolute local .ods or .xlsx path, ~/ path, "
                "or file URL; omit url to save the current file",
            )
    elif action == "workbook.convert_file":
        input_path = _required_string(params, "input_path")
        output_path = _required_string(params, "output_path")
        for field, value in (("input_path", input_path), ("output_path", output_path)):
            if not value.startswith(("/", "~/", "file:///")):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be an absolute local path, a ~/ path, or a file URL",
                )
            suffix = value.lower().rsplit(".", 1)[-1] if "." in value else ""
            if suffix not in {"csv", "ods", "xlsx"}:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must end in .csv, .ods, or .xlsx",
                )
        if input_path == output_path:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.input_path and params.output_path must identify different files",
            )
    elif action == "range.copy":
        _required_string(params, "source_sheet")
        _required_string(params, "source_range")
        _required_string(params, "destination_sheet")
        _required_string(params, "destination")
        _validate_bool_options(params, "transpose", "preserve_format")
    elif action == "range.set_scaled_display":
        divisor = params.get("divisor")
        if isinstance(divisor, bool) or not isinstance(divisor, int) or divisor < 1:
            raise AdapterError(
                "INVALID_REQUEST", "params.divisor must be a positive integer"
            )
        scaled = divisor
        while scaled > 1 and scaled % 1000 == 0:
            scaled //= 1000
        if scaled != 1:
            raise AdapterError(
                "INVALID_REQUEST", "params.divisor must be an integer power of 1000"
            )
        decimal_places = params.get("decimal_places")
        if (
            isinstance(decimal_places, bool)
            or not isinstance(decimal_places, int)
            or not 0 <= decimal_places <= 12
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.decimal_places must be an integer between 0 and 12",
            )
        unit = _required_string(params, "unit")
        if '"' in unit:
            raise AdapterError(
                "INVALID_REQUEST", "params.unit must not contain a double quote"
            )
        separator = params.get("separator", "space")
        legacy_literal = isinstance(separator, str) and separator in {"", " "}
        if (
            not isinstance(separator, str)
            or (isinstance(separator, str) and '"' in separator)
            or (separator not in {"space", "none"} and not legacy_literal)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.separator must be space or none; legacy callers may pass one literal space or an empty string",
            )
        if params.get("rounding_mode", "half_up") != "half_up":
            raise AdapterError(
                "INVALID_REQUEST",
                "params.rounding_mode currently supports only half_up",
            )
        _optional_string(params, "locale")
    elif action == "range.fill_down":
        _required_string(params, "sheet")
        _required_string(params, "range")
        if params.get("mode") not in {"previous_nonblank", "formula_pattern"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.mode must be previous_nonblank or formula_pattern",
            )
        source_rows = params.get("source_rows", 1)
        if (
            isinstance(source_rows, bool)
            or not isinstance(source_rows, int)
            or source_rows < 1
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.source_rows must be a positive integer"
            )
        if params.get("mode") != "formula_pattern" and "source_rows" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.source_rows is valid only for formula_pattern mode",
            )
        _validate_bool_options(params, "only_blank", "preserve_format")
    elif action == "range.text_transform":
        _required_string(params, "source_sheet")
        _required_string(params, "source_range")
        _required_string(params, "destination_sheet")
        _required_string(params, "destination")
        if "operations" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "range.text_transform accepts one operation; use separate calls for multiple transforms",
            )
        operation = _required_string(params, "operation")
        if operation not in {"trim", "collapse_whitespace", "title_case", "lowercase", "uppercase"}:
            raise AdapterError("INVALID_REQUEST", "params.operation is not a supported text transform")
        _optional_bool(params, "skip_blank")
    elif action == "sheet.create":
        _required_string(params, "name")
        _optional_index(params, "index")
    elif action == "sheet.rename":
        _required_string(params, "sheet")
        _required_string(params, "new_name")
    elif action == "sheet.copy":
        _required_string(params, "sheet")
        _required_string(params, "new_name")
        _optional_index(params, "index")
    elif action == "sheet.move":
        _required_string(params, "sheet")
        _optional_index(params, "index")
        if "index" not in params:
            raise AdapterError("INVALID_REQUEST", "params.index is required")
    elif action == "range.merge":
        if "merge" in params and not isinstance(params["merge"], bool):
            raise AdapterError("INVALID_REQUEST", "params.merge must be a boolean")
    elif action == "range.format":
        if not isinstance(params.get("format"), Mapping) or not params["format"]:
            raise AdapterError(
                "INVALID_REQUEST", "params.format must be a non-empty object"
            )
        _validate_format(params["format"])
    elif action == "range.set_decimal_separator":
        if params.get("separator") not in {"comma", "dot"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.separator must be comma or dot"
            )
    elif action == "range.set_validation":
        _string_list(params, "values")
        _validate_bool_options(params, "allow_blank", "show_error")
    elif action == "table.sort":
        _required_string(params, "sheet")
        _required_string(params, "range")
        keys = params.get("keys")
        if not isinstance(keys, list) or not keys:
            raise AdapterError(
                "INVALID_REQUEST", "params.keys must be a non-empty array"
            )
        for index, raw in enumerate(keys):
            if not isinstance(raw, Mapping):
                raise AdapterError(
                    "INVALID_REQUEST", f"params.keys[{index}] must be an object"
                )
            column = raw.get("column")
            if isinstance(column, bool) or not isinstance(column, int) or column < 0:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.keys[{index}].column must be a non-negative integer",
                )
            for field in ("ascending", "case_sensitive"):
                _optional_bool(raw, field, prefix=f"params.keys[{index}]")
            if raw.get("type", "automatic") not in {
                "automatic",
                "alphanumeric",
                "numeric",
            }:
                raise AdapterError(
                    "INVALID_REQUEST", f"params.keys[{index}].type is unsupported"
                )
        _optional_bool(params, "contains_header")
    elif action == "table.reorder_columns":
        _required_string(params, "sheet")
        _required_string(params, "range")
        order = _string_list(params, "headers")
        if len(order) != len(set(order)):
            raise AdapterError("INVALID_REQUEST", "params.headers must be unique")
    elif action == "rows.set_hidden":
        _required_string(params, "sheet")
        rows = params.get("rows")
        if (
            not isinstance(rows, list)
            or not rows
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in rows)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.rows must be a non-empty array of 1-based row numbers",
            )
        if "hidden" in params and not isinstance(params["hidden"], bool):
            raise AdapterError("INVALID_REQUEST", "params.hidden must be a boolean")
    elif action == "chart.create":
        _required_string(params, "sheet")
        if "source_sheet" in params:
            _required_string(params, "source_sheet")
        _required_string(params, "name")
        source_ranges = params.get("source_ranges")
        if (
            not isinstance(source_ranges, list)
            or not source_ranges
            or any(not isinstance(v, str) for v in source_ranges)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.source_ranges must be a non-empty string array",
            )
        for index, source_range in enumerate(source_ranges):
            if not A1_RANGE_PATTERN.fullmatch(source_range.strip()):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.source_ranges[{index}] must be one contiguous A1 range "
                    "such as A1 or A1:B2; do not join areas with commas",
                    {"source_range": source_range},
                )
        if params.get("type") not in {"column", "bar", "line"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.type must be column, bar, or line"
            )
        if params.get("data_row_source", "auto") not in {
            "auto",
            "rows",
            "columns",
        }:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.data_row_source must be auto, rows, or columns",
            )
        _validate_bool_options(params, "column_headers", "row_headers", "replace")
        _optional_string(params, "title")
        position = params.get("position")
        if position is not None:
            if not isinstance(position, Mapping):
                raise AdapterError(
                    "INVALID_REQUEST", "params.position must be an object"
                )
            unknown = sorted(set(position) - {"x", "y", "width", "height"})
            if unknown:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.position contains unsupported fields",
                    unknown,
                )
            for field in ("x", "y", "width", "height"):
                if field not in position:
                    continue
                value = position[field]
                if isinstance(value, bool) or not isinstance(value, int):
                    raise AdapterError(
                        "INVALID_REQUEST", f"params.position.{field} must be an integer"
                    )
                if field in {"width", "height"} and value <= 0:
                    raise AdapterError(
                        "INVALID_REQUEST", f"params.position.{field} must be positive"
                    )
    elif action == "pivot.create":
        _required_string(params, "source_sheet")
        _required_string(params, "source_range")
        _required_string(params, "destination_sheet")
        destination = params.get("destination")
        if isinstance(destination, Mapping):
            if set(destination) != {"below_range", "blank_rows"}:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.destination requires exactly below_range and blank_rows",
                )
            _required_a1_range(destination, "below_range", prefix="params.destination")
            gap = destination["blank_rows"]
            if isinstance(gap, bool) or not isinstance(gap, int) or gap < 0:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.destination.blank_rows must be a non-negative integer",
                )
        else:
            _required_string(params, "destination")
        _validate_pivot_fields(params)
        _validate_bool_options(params, "replace", "show_filter_button")
    elif action == "view.set_zoom":
        _required_string(params, "sheet")
        zoom = params.get("zoom")
        if isinstance(zoom, bool) or not isinstance(zoom, int) or not 20 <= zoom <= 600:
            raise AdapterError(
                "INVALID_REQUEST", "params.zoom must be an integer between 20 and 600"
            )
    elif action == "view.freeze_panes":
        _required_string(params, "sheet")
        for field in ("columns", "rows"):
            value = params.get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AdapterError(
                    "INVALID_REQUEST", f"params.{field} must be a non-negative integer"
                )
    elif action == "view.freeze_range":
        _required_string(params, "sheet")
        _required_string(params, "range")
    elif action == "page.fit_to_pages":
        _required_string(params, "sheet")
        _optional_string(params, "print_range")
        for field in ("pages_wide", "pages_tall"):
            value = params.get(field, 1)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AdapterError(
                    "INVALID_REQUEST", f"params.{field} must be a positive integer"
                )
    elif action == "workbook.export":
        if params.get("format") not in {"csv", "pdf"}:
            raise AdapterError("INVALID_REQUEST", "params.format must be csv or pdf")
        _required_string(params, "url")
        _optional_string(params, "sheet")
        _optional_string(params, "filter_options")


def _typed_cell(value: Any, *, prefix: str) -> dict[str, Any]:
    """Represent a public literal without interpreting or changing its value."""
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {"kind": "blank"}
    if isinstance(value, str):
        return {"kind": "string", "value": value}
    if isinstance(value, bool):
        return {"kind": "boolean", "value": value}
    if isinstance(value, (int, float)) and not (
        isinstance(value, float) and not math.isfinite(value)
    ):
        return {"kind": "number", "value": value}
    raise AdapterError(
        "INVALID_REQUEST",
        f"{prefix} must be a typed cell or a finite JSON scalar or null",
    )


def validate_typed_matrix(value: Any) -> list[list[dict[str, Any]]]:
    if not isinstance(value, list) or not value:
        raise AdapterError("INVALID_REQUEST", "values must be a non-empty array")
    flat = all(not isinstance(item, list) for item in value)
    if flat:
        raw_rows: list[Any] = [value]
    elif all(isinstance(item, list) for item in value):
        raw_rows = value
    else:
        raise AdapterError(
            "INVALID_REQUEST",
            "values must be either a flat cell list or a rectangular matrix",
        )
    width: int | None = None
    result: list[list[dict[str, Any]]] = []
    for row_index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, list) or not raw_row:
            raise AdapterError(
                "INVALID_REQUEST", f"values[{row_index}] must be a non-empty array"
            )
        if width is None:
            width = len(raw_row)
        elif len(raw_row) != width:
            raise AdapterError("INVALID_REQUEST", "values must be rectangular", {
                "row_index": row_index, "expected_columns": width,
                "actual_columns": len(raw_row),
                "guidance": "Each matrix row must have the same width. A formula occupies one cell; "
                "do not split '=' and the expression into separate cells. Use the documented typed "
                "formula value or cells.set_formulas. No cells were written.",
            })
        row: list[dict[str, Any]] = []
        for column_index, raw_cell in enumerate(raw_row):
            cell = _typed_cell(
                raw_cell, prefix=f"values[{row_index}][{column_index}]"
            )
            kind = cell.get("kind")
            if kind not in CELL_KINDS:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "cell kind is unsupported",
                    {"row": row_index, "column": column_index, "kind": kind},
                )
            if kind != "blank" and "value" not in cell:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "non-blank cells require value",
                    {"row": row_index, "column": column_index},
                )
            value = cell.get("value")
            if kind in {"string", "date"} and not isinstance(value, str):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"{kind} cell values must be strings",
                    {"row": row_index, "column": column_index},
                )
            if kind == "formula" and (
                not isinstance(value, str) or not value.startswith("=")
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "formula cell values must start with '='",
                    {"row": row_index, "column": column_index},
                )
            if kind == "number" and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "number cell values must be numeric",
                    {"row": row_index, "column": column_index},
                )
            if kind == "boolean" and not isinstance(value, bool):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "boolean cell values must be booleans",
                    {"row": row_index, "column": column_index},
                )
            if kind == "formatted_text":
                _validate_formatted_text_value(
                    value, prefix=f"values[{row_index}][{column_index}].value"
                )
            _optional_string(
                cell,
                "number_format",
                prefix=f"values[{row_index}][{column_index}]",
            )
            _optional_string(
                cell, "locale", prefix=f"values[{row_index}][{column_index}]"
            )
            row.append(cell)
        result.append(row)
    return result


def orient_typed_values(
    value: Any, *, target_rows: int, target_columns: int
) -> list[list[dict[str, Any]]]:
    """Orient the public flat form from target geometry inside the Adapter."""
    matrix = validate_typed_matrix(value)
    is_flat = not isinstance(value[0], list)
    if is_flat:
        cells = matrix[0]
        if target_rows == 1 and len(cells) == target_columns:
            return [cells]
        if target_columns == 1 and len(cells) == target_rows:
            return [[cell] for cell in cells]
        raise AdapterError(
            "RANGE_INVALID",
            "flat values require a one-row or one-column target of the same length. "
            "To write one value into merged cells, target only the top-left cell.",
            {
                "target_rows": target_rows,
                "target_columns": target_columns,
                "value_count": len(cells),
            },
        )
    value_rows = len(matrix)
    value_columns = len(matrix[0])
    if value_rows != target_rows or value_columns != target_columns:
        raise AdapterError(
            "RANGE_INVALID",
            "typed matrix dimensions do not match the target range. "
            "To write one value into merged cells, target only the top-left cell.",
            {
                "target_rows": target_rows,
                "target_columns": target_columns,
                "value_rows": value_rows,
                "value_columns": value_columns,
            },
        )
    return matrix


def _validate_formatted_text_value(value: Any, *, prefix: str) -> None:
    spec = _mapping(value, prefix)
    unknown = sorted(set(spec) - {"parts"})
    if unknown:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix} contains unsupported fields", unknown
        )
    parts = spec.get("parts")
    if not isinstance(parts, list) or not parts:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.parts must be a non-empty array"
        )
    has_cell = False
    for index, raw_part in enumerate(parts):
        part_prefix = f"{prefix}.parts[{index}]"
        part = _mapping(raw_part, part_prefix)
        unknown = sorted(set(part) - {"text", "cell", "decimal_places"})
        if unknown:
            raise AdapterError(
                "INVALID_REQUEST", f"{part_prefix} contains unsupported fields", unknown
            )
        text_part = "text" in part
        cell_part = "cell" in part
        if text_part == cell_part:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{part_prefix} must contain exactly one of text or cell",
            )
        if text_part:
            if not isinstance(part["text"], str):
                raise AdapterError(
                    "INVALID_REQUEST", f"{part_prefix}.text must be a string"
                )
            if "decimal_places" in part:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"{part_prefix}.decimal_places is valid only for a cell part",
                )
            continue
        has_cell = True
        reference = part["cell"]
        if not isinstance(reference, str) or not CELL_REFERENCE_PATTERN.fullmatch(
            reference.strip()
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"{part_prefix}.cell must be one A1 cell reference, optionally sheet-qualified",
            )
        if "decimal_places" in part:
            decimal_places = part["decimal_places"]
            if (
                isinstance(decimal_places, bool)
                or not isinstance(decimal_places, int)
                or not 0 <= decimal_places <= 12
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"{part_prefix}.decimal_places must be an integer between 0 and 12",
                )
    if not has_cell:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.parts must contain at least one cell part. "
            "For literal text, use kind=string and put the text directly in value; "
            "use range.format for fonts and colors. Do not add a cell reference "
            "just to style literal text.",
        )


def normalize_pivot_data_field(value: Any, *, index: int = 0) -> dict[str, Any]:
    prefix = f"params.data_fields[{index}]"
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", f"{prefix} must be an object")
    spec = dict(value)
    allowed = {
        "field",
        "name",
        "aggregation",
        "function",
        "show_data_as",
        "reference_field",
        "reference_item",
    }
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix} contains unsupported fields", unknown
        )
    field = spec.get("field", spec.get("name"))
    if not isinstance(field, str) or not field.strip():
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.field must be a non-empty source header string",
        )
    if "field" in spec and "name" in spec and spec["field"] != spec["name"]:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.field and legacy name disagree"
        )
    aggregation = spec.get("aggregation", spec.get("function", "sum"))
    if not isinstance(aggregation, str) or not aggregation.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.aggregation must be a non-empty string"
        )
    if (
        "aggregation" in spec
        and "function" in spec
        and str(spec["aggregation"]).casefold() != str(spec["function"]).casefold()
    ):
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.aggregation and legacy function disagree"
        )
    show_data_as = spec.get("show_data_as", "none")
    if not isinstance(show_data_as, str) or not show_data_as.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.show_data_as must be a non-empty string"
        )
    normalized = {
        "name": field.strip(),
        "function": aggregation.casefold(),
        "show_data_as": show_data_as.casefold(),
    }
    for optional in ("reference_field", "reference_item"):
        _optional_string(spec, optional, prefix=prefix)
        if optional in spec:
            normalized[optional] = spec[optional]
    if show_data_as.casefold() == "none" and any(
        optional in spec for optional in ("reference_field", "reference_item")
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.reference_field/reference_item require a non-none show_data_as",
        )
    return normalized
