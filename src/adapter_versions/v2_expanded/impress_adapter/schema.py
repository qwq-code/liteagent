from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from .errors import AdapterError
from .export_contract import validate_export_destination
from .geometry_contract import (
    ATOMIC_GEOMETRY_FIELDS,
    validate_atomic_geometry_params,
    validate_optional_shape_geometry_params,
    validate_shape_geometry_params,
)
from .image_contract import validate_local_image_path
from .slide_reference import require_slide_index
from .table_contract import validate_table_placement


ADAPTER_NAME = "libreoffice_impress"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 120_000
DEFAULT_TIMEOUT_MS = 30_000

ACTIONS = frozenset(
    {
        "presentation.inspect",
        "presentation.create_summary_slide",
        "presentation.set_page_size",
        "presentation.save",
        "presentation.export",
        "slide.create",
        "slides.create_from_images",
        "slide.delete",
        "slide.duplicate",
        "slide.move",
        "slide.set_background",
        "slide.set_transition",
        "slide.set_role_text",
        "slide.format_text_roles",
        "slides.format_text_roles",
        "slide.set_notes",
        "shape.create_text",
        "shape.write_text",
        "shape.write_text_native",
        "shape.format_text",
        "shape.set_geometry",
        *ATOMIC_GEOMETRY_FIELDS,
        "shape.fit_to_slide",
        "shape.set_fill",
        "shape.insert_image",
        "shape.export_image",
        "shape.delete",
        "table.create",
        "table.replace_row",
        "table.write",
        "table.format_text",
        "audio.insert",
        "master.set_page_number",
        "settings.set",
    }
)

VERIFY_TYPES = frozenset(
    {
        "document_identity",
        "slide_count",
        "page_size",
        "slide_properties",
        "shape_properties",
        "text_properties",
        "notes",
        "background",
        "transition",
        "export_file",
        "file_reopen",
        "settings",
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


def _required_string(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-empty string"
        )
    return value


def _optional_string(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> None:
    if field in data:
        _required_string(data, field, prefix)


def _optional_bool(data: Mapping[str, Any], field: str, prefix: str = "params") -> None:
    if field in data and not isinstance(data[field], bool):
        raise AdapterError("INVALID_REQUEST", f"{prefix}.{field} must be a boolean")


def _optional_nonnegative_int(data: Mapping[str, Any], field: str) -> None:
    if field in data and (
        isinstance(data[field], bool)
        or not isinstance(data[field], int)
        or data[field] < 0
    ):
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must be a non-negative integer"
        )


TEXT_FORMAT_FIELDS = frozenset(
    {
        "color",
        "font_size",
        "font_name",
        "bold",
        "italic",
        "underline",
        "strike",
        "alignment",
    }
)
TEXT_ROLE_VALUES = frozenset({"all", "title", "content", "body", "table", "text"})
WRITABLE_TEXT_ROLE_VALUES = frozenset({"title", "content", "body", "text"})


def _validate_role_format_rule(data: Mapping[str, Any], prefix: str) -> None:
    unexpected = set(data).difference({"roles", *TEXT_FORMAT_FIELDS})
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix} has unsupported fields: {sorted(unexpected)}"
        )
    roles = data.get("roles")
    if (
        not isinstance(roles, list)
        or not roles
        or any(
            not isinstance(role, str) or role not in TEXT_ROLE_VALUES for role in roles
        )
        or len(set(roles)) != len(roles)
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.roles must be a non-empty unique array of supported semantic roles",
        )
    for field in ("bold", "italic", "underline", "strike"):
        _optional_bool(data, field, prefix)
    _optional_string(data, "font_name", prefix)
    if "font_size" in data and (
        isinstance(data["font_size"], bool)
        or not isinstance(data["font_size"], (int, float))
        or data["font_size"] <= 0
    ):
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.font_size must be a positive number"
        )
    if data.get("alignment") not in {None, "left", "center", "right", "justify"}:
        raise AdapterError("INVALID_REQUEST", f"{prefix}.alignment is unsupported")
    if not TEXT_FORMAT_FIELDS.intersection(data):
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix} requires at least one formatting field"
        )


def _selector(data: Mapping[str, Any], prefix: str = "params") -> None:
    value = data.get("selector")
    if value is None:
        raise AdapterError("INVALID_REQUEST", f"{prefix}.selector is required")
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", f"{prefix}.selector must be an object")
    selector = dict(value)
    if "index" in selector:
        if (
            isinstance(selector["index"], bool)
            or not isinstance(selector["index"], int)
            or selector["index"] < 0
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"{prefix}.selector.index must be a non-negative integer",
            )
    if "path" in selector:
        path = selector["path"]
        if (
            not isinstance(path, list)
            or not path
            or any(
                isinstance(index, bool) or not isinstance(index, int) or index < 0
                for index in path
            )
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"{prefix}.selector.path must be a non-empty array of non-negative indices",
            )
    for field in ("name", "text", "placeholder", "kind"):
        if field in selector and (
            not isinstance(selector[field], str) or not selector[field].strip()
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"{prefix}.selector.{field} must be a non-empty string",
            )


def _fit_graphic_selector(data: Mapping[str, Any]) -> None:
    value = data.get("selector")
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", "params.selector must be an object")
    selector = dict(value)
    if set(selector) not in ({"path"}, {"index"}):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.selector must contain only an exact path or only an exact index",
        )
    _selector(data)


def _verify_checks(value: Any) -> list[dict[str, Any]]:
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
        if "tolerance" in check and (
            isinstance(check["tolerance"], bool)
            or not isinstance(check["tolerance"], (int, float))
            or check["tolerance"] < 0
        ):
            raise AdapterError(
                "INVALID_REQUEST", f"verify[{index}].tolerance must be non-negative"
            )
        if check["type"] in {"slide_properties", "background", "transition", "notes"}:
            _slide_index(check, f"verify[{index}]")
        if check["type"] in {"shape_properties", "text_properties"}:
            _slide_index(check, f"verify[{index}]")
            if "selector" not in check:
                raise AdapterError(
                    "INVALID_REQUEST", f"verify[{index}].selector is required"
                )
            _selector(check, f"verify[{index}]")
        if check["type"] in {"export_file", "file_reopen"}:
            _required_string(check, "path", f"verify[{index}]")
        checks.append(check)
    return checks


def _slide_index(data: Mapping[str, Any], prefix: str = "params") -> None:
    value = data.get("slide")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.slide must be a non-negative 0-based index"
        )


def validate_action_params(action: str, params: Mapping[str, Any]) -> None:
    if action == "presentation.create_summary_slide":
        allowed = {"slides", "index", "title"}
        if set(params).difference(allowed):
            raise AdapterError(
                "INVALID_REQUEST",
                "presentation.create_summary_slide received unsupported parameters",
                {"unexpected": sorted(set(params).difference(allowed))},
            )
        slides = params.get("slides")
        if (
            not isinstance(slides, list)
            or not slides
            or len(slides) > 100
            or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in slides)
            or len(set(slides)) != len(slides)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.slides must contain 1 to 100 distinct zero-based slide indices",
            )
        _optional_nonnegative_int(params, "index")
        if "title" in params:
            _required_string(params, "title")
    if action == "slides.create_from_images":
        allowed = {"image_paths", "replace_existing_slides", "fit_mode"}
        unexpected = set(params).difference(allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "slides.create_from_images received unsupported parameters",
                {"unexpected": sorted(unexpected)},
            )
        paths = params.get("image_paths")
        if (
            not isinstance(paths, list)
            or not 1 <= len(paths) <= 100
            or any(not isinstance(path, str) or not path.strip() for path in paths)
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.image_paths must contain 1 to 100 paths"
            )
        if "replace_existing_slides" not in params:
            raise AdapterError(
                "INVALID_REQUEST", "params.replace_existing_slides is required"
            )
        _optional_bool(params, "replace_existing_slides")
        if params.get("fit_mode", "original") not in {"original", "cover", "contain", "stretch"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.fit_mode must be original, cover, contain, or stretch",
            )
        for path in paths:
            validate_local_image_path(path)
    if action == "presentation.inspect":
        if set(params).difference({"slides"}):
            raise AdapterError(
                "INVALID_REQUEST", "presentation.inspect accepts only optional slides"
            )
        if "slides" in params:
            slides = params["slides"]
            if (
                not isinstance(slides, list)
                or not 1 <= len(slides) <= 100
                or any(
                    isinstance(index, bool) or not isinstance(index, int) or index < 0
                    for index in slides
                )
                or len(set(slides)) != len(slides)
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.slides must contain 1 to 100 distinct zero-based slide indices",
                )
    if action in {
        "slide.delete",
        "slide.duplicate",
        "slide.move",
        "slide.set_transition",
        "slide.set_notes",
    }:
        _slide_index(params)
    if action in {
        "shape.write_text",
        "shape.write_text_native",
        "shape.format_text",
        "shape.set_fill",
        "shape.export_image",
        "shape.delete",
        "table.format_text",
    }:
        _slide_index(params)
        _selector(params)
    if action == "shape.fit_to_slide":
        _slide_index(params)
        _fit_graphic_selector(params)
    if action == "shape.set_geometry" or action in ATOMIC_GEOMETRY_FIELDS:
        require_slide_index(params, allow_consistent_pair=True)
        _selector(params)
    if action in {
        "table.create",
        "table.write",
        "shape.create_text",
        "audio.insert",
    }:
        _slide_index(params)
    if action == "shape.insert_image":
        require_slide_index(params, allow_consistent_pair=True)
        unexpected = set(params).difference(
            {
                "slide",
                "slide_number",
                "path",
                "x",
                "y",
                "width",
                "height",
                "width_measurement",
                "height_measurement",
            }
        )
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                f"shape.insert_image has unsupported params: {sorted(unexpected)}",
            )
    if action in {"slide.create", "slide.duplicate", "slide.move"}:
        _optional_nonnegative_int(params, "index")
    if action == "presentation.export":
        _required_string(params, "format")
        _required_string(params, "url")
        format_name = params["format"].lower()
        if format_name not in {"pptx", "odp", "pdf", "png", "jpg"}:
            raise AdapterError("INVALID_REQUEST", "params.format is unsupported")
        validate_export_destination(format_name, params["url"])
        dimensions = ("pixel_width", "pixel_height")
        supplied_dimensions = [field for field in dimensions if field in params]
        if supplied_dimensions and format_name not in {"png", "jpg"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "pixel dimensions are only supported for PNG and JPEG exports",
            )
        if supplied_dimensions and len(supplied_dimensions) != 2:
            raise AdapterError(
                "INVALID_REQUEST",
                "pixel_width and pixel_height must be supplied together",
            )
        for field in supplied_dimensions:
            value = params[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AdapterError(
                    "INVALID_REQUEST", f"params.{field} must be a positive integer"
                )
        if "slide" in params:
            _slide_index(params)
    if action == "presentation.save":
        _optional_string(params, "url")
        _optional_string(params, "filter_name")
    if action == "presentation.set_page_size":
        if set(params) != {"width", "height"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "presentation.set_page_size requires only width and height, in 1/100 mm",
            )
        for field in ("width", "height"):
            value = params[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 2147483647
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be an integer from 1 to 2147483647, in 1/100 mm",
                )
    if action == "slide.set_transition":
        _required_string(params, "transition")
        if params["transition"].lower() not in {"none", "fade", "dissolve"}:
            raise AdapterError("INVALID_REQUEST", "params.transition is unsupported")
    if action == "slide.set_notes":
        if "text" not in params or not isinstance(params["text"], str):
            raise AdapterError("INVALID_REQUEST", "params.text must be a string")
    if action in {"shape.write_text", "shape.write_text_native"}:
        if "text" not in params or not isinstance(params["text"], str):
            raise AdapterError("INVALID_REQUEST", "params.text must be a string")
    if action == "slide.set_role_text":
        unexpected = set(params).difference(
            {"slide", "role", "text", *TEXT_FORMAT_FIELDS}
        )
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                f"slide.set_role_text has unsupported params: {sorted(unexpected)}",
            )
        _slide_index(params)
        if params.get("role") not in WRITABLE_TEXT_ROLE_VALUES:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.role must be title, content, body, or text",
            )
        _required_string(params, "text")
        formatting = {key: params[key] for key in TEXT_FORMAT_FIELDS if key in params}
        if formatting:
            _validate_role_format_rule(
                {"roles": [params["role"]], **formatting}, "params"
            )
    if action == "shape.write_text_native":
        _optional_bool(params, "replace")
    if action in {"slide.format_text_roles", "slides.format_text_roles"}:
        location_field = "slide" if action.startswith("slide.") else "slides"
        unexpected = set(params).difference(
            {location_field, "roles", "overrides", *TEXT_FORMAT_FIELDS}
        )
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{action} has unsupported params: {sorted(unexpected)}",
            )
        if location_field not in params:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{action} requires params.{location_field}",
            )
        if location_field == "slide":
            _slide_index(params)
        else:
            slides = params["slides"]
            if (
                not isinstance(slides, list)
                or not slides
                or len(slides) > 100
                or any(
                    isinstance(slide, bool) or not isinstance(slide, int) or slide < 0
                    for slide in slides
                )
                or len(set(slides)) != len(slides)
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.slides must be an array of 1 to 100 unique non-negative integers",
                )
        base_rule = {
            key: value
            for key, value in params.items()
            if key not in {location_field, "overrides"}
        }
        _validate_role_format_rule(base_rule, "params")
        if "overrides" in params:
            overrides = params["overrides"]
            if (
                not isinstance(overrides, list)
                or not overrides
                or len(overrides) > 8
                or any(not isinstance(override, Mapping) for override in overrides)
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.overrides must be an array of 1 to 8 role-format objects",
                )
            for index, override in enumerate(overrides):
                _validate_role_format_rule(override, f"params.overrides[{index}]")
    if action in {"shape.format_text", "table.format_text"}:
        for field in ("bold", "italic", "underline", "strike", "bullet"):
            _optional_bool(params, field)
        _optional_string(params, "font_name")
        _optional_string(params, "match_text")
        if "font_size" in params and (
            isinstance(params["font_size"], bool)
            or not isinstance(params["font_size"], (int, float))
            or params["font_size"] <= 0
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.font_size must be a positive number"
            )
        if params.get("alignment") not in {None, "left", "center", "right", "justify"}:
            raise AdapterError("INVALID_REQUEST", "params.alignment is unsupported")
        if "lines" in params:
            lines = params["lines"]
            if (
                not isinstance(lines, list)
                or not lines
                or any(
                    isinstance(line, bool) or not isinstance(line, int) or line < 0
                    for line in lines
                )
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.lines must be a non-empty array of zero-based indices",
                )
    if action == "shape.format_text":
        for field in ("level", "left_margin"):
            _optional_nonnegative_int(params, field)
        if "first_line_indent" in params and (
            isinstance(params["first_line_indent"], bool)
            or not isinstance(params["first_line_indent"], int)
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.first_line_indent must be an integer"
            )
        formatting_fields = {
            "color",
            "font_size",
            "font_name",
            "bold",
            "italic",
            "underline",
            "strike",
            "bullet",
            "alignment",
            "level",
            "left_margin",
            "first_line_indent",
        }
        if not formatting_fields.intersection(params):
            raise AdapterError(
                "INVALID_REQUEST",
                "shape.format_text requires at least one formatting field",
            )
    if action == "table.format_text":
        if "bullet" in params or "match_text" in params or "lines" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "table.format_text does not support bullet, match_text, or lines",
            )
        formatting_fields = {
            "color",
            "font_size",
            "font_name",
            "bold",
            "italic",
            "underline",
            "strike",
            "alignment",
        }
        if not formatting_fields.intersection(params):
            raise AdapterError(
                "INVALID_REQUEST",
                "table.format_text requires at least one formatting field",
            )
        if "cells" in params:
            cells = params["cells"]
            if not isinstance(cells, list) or not cells:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.cells must be a non-empty array when supplied",
                )
            for index, cell in enumerate(cells):
                if not isinstance(cell, Mapping):
                    raise AdapterError(
                        "INVALID_REQUEST",
                        f"params.cells[{index}] must be an object",
                    )
                for field in ("row", "column"):
                    value = cell.get(field)
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, int)
                        or value < 0
                    ):
                        raise AdapterError(
                            "INVALID_REQUEST",
                            f"params.cells[{index}].{field} must be a non-negative integer",
                        )
    if action == "shape.set_geometry":
        validate_shape_geometry_params(params)
    if action in ATOMIC_GEOMETRY_FIELDS:
        validate_atomic_geometry_params(action, params)
    if action == "shape.create_text":
        if "text" not in params or not isinstance(params["text"], str):
            raise AdapterError("INVALID_REQUEST", "params.text must be a string")
    if action == "shape.fit_to_slide" and params.get("mode") not in {
        "cover",
        "contain",
        "stretch",
    }:
        raise AdapterError(
            "INVALID_REQUEST", "params.mode must be cover, contain, or stretch"
        )
    if action == "shape.insert_image":
        image_path = _required_string(params, "path")
        validate_local_image_path(image_path)
        validate_optional_shape_geometry_params(params)
    if action == "shape.export_image":
        output_path = _required_string(params, "output_path")
        suffix = output_path.removeprefix("file://").lower().rsplit(".", 1)
        if len(suffix) != 2 or suffix[-1] not in {"png", "jpg", "jpeg"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.output_path must end in .png, .jpg, or .jpeg",
            )
        _optional_bool(params, "overwrite")
    if action == "audio.insert":
        _required_string(params, "path")
    if action == "table.create":
        for field in ("rows", "columns"):
            value = params.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AdapterError(
                    "INVALID_REQUEST", f"params.{field} must be a positive integer"
                )
        validate_table_placement(params)
    if action == "table.write":
        if not isinstance(params.get("cells"), list):
            raise AdapterError("INVALID_REQUEST", "params.cells must be an array")
    if action == "table.replace_row":
        unexpected = set(params).difference({"slide_number", "row_number", "values"})
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                f"table.replace_row has unsupported params: {sorted(unexpected)}",
            )
        if "slide_number" not in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "table.replace_row requires a one-based params.slide_number",
            )
        require_slide_index(params)
        row_number = params.get("row_number")
        if (
            isinstance(row_number, bool)
            or not isinstance(row_number, int)
            or row_number < 1
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.row_number must be a positive one-based integer",
            )
        values = params.get("values")
        if (
            not isinstance(values, list)
            or not values
            or len(values) > 100
            or any(not isinstance(value, str) for value in values)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.values must be an array of 1 to 100 strings",
            )
    if action == "slide.set_background":
        has_slide = "slide" in params
        has_all_slides = "all_slides" in params
        if has_slide == has_all_slides:
            raise AdapterError(
                "INVALID_REQUEST",
                "params must contain exactly one of slide or all_slides",
            )
        if has_slide:
            _slide_index(params)
        elif params.get("all_slides") is not True:
            raise AdapterError("INVALID_REQUEST", "params.all_slides must be true")
        if "color" not in params and "image_path" not in params:
            raise AdapterError(
                "INVALID_REQUEST", "params.color or params.image_path is required"
            )
        _optional_string(params, "image_path")
    if action == "shape.set_fill" and "color" not in params:
        raise AdapterError("INVALID_REQUEST", "params.color is required")
    if action == "settings.set":
        key = params.get("key")
        if key not in {"auto_save", "presenter_screen", "left_panel"}:
            raise AdapterError("INVALID_REQUEST", "params.key is unsupported")
        if not isinstance(params.get("value"), bool):
            raise AdapterError("INVALID_REQUEST", "params.value must be a boolean")
        if key == "auto_save" and "minutes" in params:
            minutes = params["minutes"]
            if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
                raise AdapterError(
                    "INVALID_REQUEST", "params.minutes must be a positive integer"
                )


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
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"timeout_ms must be an integer between {MIN_TIMEOUT_MS} and {MAX_TIMEOUT_MS}",
        )
    document = _mapping(data.get("document"), "document")
    for field in ("url", "title"):
        if field in document:
            _required_string(document, field, "document")
    params = _mapping(data.get("params"), "params")
    validate_action_params(action, params)
    return ActionRequest(
        request_id,
        adapter,
        action,
        timeout_ms,
        document,
        params,
        _verify_checks(data.get("verify")),
    )
