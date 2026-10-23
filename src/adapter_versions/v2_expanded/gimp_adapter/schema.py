from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .errors import AdapterError
from .foreground import validate_image_suffix


ADAPTER_NAME = "gimp"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 180_000
DEFAULT_TIMEOUT_MS = 45_000

ACTIONS = frozenset(
    {
        "image.inspect",
        "image.export",
        "image.convert_indexed",
        "image.adjust",
        "image.crop",
        "image.flip",
        "image.apply_alpha_mask",
        "layer.add",
        "layer.fill",
        "layer.scale",
        "layer.translate",
        "config.set",
    }
)

VERIFY_TYPES = frozenset(
    {
        "file",
        "image",
        "palette",
        "brightness_decreased",
        "saturation_increased",
        "contrast_increased",
        "mirror",
        "alpha",
        "layer",
        "config",
        "action_history",
        "window",
        "background_color",
    }
)

NON_IMAGE_DOCUMENT_SUFFIXES = frozenset(
    {
        ".docx",
        ".odp",
        ".ods",
        ".odt",
        ".pptm",
        ".pptx",
        ".ppsx",
        ".xlsm",
        ".xlsx",
        ".zip",
    }
)


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    adapter: str
    action: str
    timeout_ms: int
    target: dict[str, Any]
    params: dict[str, Any]
    verify: list[dict[str, Any]]

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "timeout_ms": self.timeout_ms,
            "target": self.target,
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


def _number(data: Mapping[str, Any], field: str, prefix: str = "params") -> float:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError("INVALID_REQUEST", f"{prefix}.{field} must be a number")
    return float(value)


def _positive_int(data: Mapping[str, Any], field: str, prefix: str = "params") -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a positive integer"
        )
    return value


def _optional_bool(data: Mapping[str, Any], field: str, prefix: str = "params") -> None:
    if field in data and not isinstance(data[field], bool):
        raise AdapterError("INVALID_REQUEST", f"{prefix}.{field} must be a boolean")


def _reject_non_image_document_path(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> None:
    value = str(data[field]).removeprefix("file://")
    suffix = Path(value).suffix.casefold()
    if suffix in NON_IMAGE_DOCUMENT_SUFFIXES:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.{field} points to an Office/archive document, not an image; "
            "extract or render an image first",
            {"field": field, "suffix": suffix},
        )


def _layer_selector(params: Mapping[str, Any]) -> None:
    if "layer_index" not in params and "layer_name" not in params:
        raise AdapterError(
            "INVALID_REQUEST", "params requires layer_index or layer_name"
        )
    if "layer_index" in params:
        value = params["layer_index"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AdapterError(
                "INVALID_REQUEST", "params.layer_index must be a non-negative integer"
            )
    if "layer_name" in params:
        _string(params, "layer_name")


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
        checks.append(check)
    return checks


def validate_action_params(action: str, params: Mapping[str, Any]) -> None:
    if action == "image.inspect":
        _string(params, "path")
    elif action == "image.export":
        _string(params, "input_path")
        _string(params, "output_path")
        if "quality" in params:
            quality = _number(params, "quality")
            if not 0 <= quality <= 1:
                raise AdapterError(
                    "INVALID_REQUEST", "params.quality must be between 0 and 1"
                )
        if "loader" in params and params["loader"] not in {"auto", "jpeg"}:
            raise AdapterError("INVALID_REQUEST", "params.loader must be auto or jpeg")
    elif action == "image.convert_indexed":
        _string(params, "input_path")
        _string(params, "output_path")
        if "colors" in params:
            colors = _positive_int(params, "colors")
            if colors > 256:
                raise AdapterError(
                    "INVALID_REQUEST", "params.colors must not exceed 256"
                )
        _optional_bool(params, "open_in_gui")
    elif action == "image.adjust":
        _string(params, "input_path")
        _string(params, "output_path")
        _reject_non_image_document_path(params, "input_path")
        if not any(key in params for key in ("brightness", "contrast", "saturation")):
            raise AdapterError("INVALID_REQUEST", "image.adjust requires an adjustment")
        for field, minimum, maximum in (
            ("brightness", -127, 127),
            ("contrast", -127, 127),
            ("saturation", -100, 100),
        ):
            if field in params:
                value = _number(params, field)
                if not minimum <= value <= maximum:
                    raise AdapterError(
                        "INVALID_REQUEST",
                        f"params.{field} must be between {minimum} and {maximum}",
                    )
        _optional_bool(params, "open_in_gui")
    elif action == "image.crop":
        allowed = {
            "input_path",
            "output_path",
            "unit",
            "top",
            "right",
            "bottom",
            "left",
            "overwrite",
        }
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "image.crop received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        _string(params, "input_path")
        _string(params, "output_path")
        _reject_non_image_document_path(params, "input_path")
        _reject_non_image_document_path(params, "output_path")
        validate_image_suffix(params["input_path"], "params.input_path")
        validate_image_suffix(params["output_path"], "params.output_path")
        unit = params.get("unit")
        if unit not in {"percent", "pixels"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.unit must be percent or pixels"
            )
        values = []
        for field in ("top", "right", "bottom", "left"):
            if field not in params:
                values.append(0.0)
                continue
            value = _number(params, field)
            if value < 0 or (unit == "percent" and value > 100):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be non-negative and no more than 100 in percent mode",
                )
            if unit == "pixels" and not value.is_integer():
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be an integer in pixels mode",
                )
            values.append(value)
        if not any(value > 0 for value in values):
            raise AdapterError(
                "INVALID_REQUEST", "image.crop requires a positive edge amount"
            )
        if unit == "percent" and (
            values[0] + values[2] >= 100 or values[1] + values[3] >= 100
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "opposing percent crop amounts must total less than 100",
            )
        _optional_bool(params, "overwrite")
    elif action == "image.flip":
        _string(params, "input_path")
        _string(params, "output_path")
        if params.get("direction", "horizontal") not in {"horizontal", "vertical"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.direction must be horizontal or vertical"
            )
        _optional_bool(params, "open_in_gui")
    elif action == "image.apply_alpha_mask":
        _string(params, "input_path")
        _string(params, "mask_path")
        _string(params, "output_path")
        _optional_bool(params, "open_in_gui")
    elif action == "layer.add":
        _string(params, "input_path")
        _string(params, "output_path")
        _string(params, "name")
        for field in ("width", "height"):
            if field in params:
                _positive_int(params, field)
        _optional_bool(params, "open_in_gui")
    elif action == "layer.fill":
        _string(params, "input_path")
        _string(params, "output_path")
        _layer_selector(params)
        color = params.get("color")
        if not isinstance(color, list) or len(color) not in {3, 4}:
            raise AdapterError(
                "INVALID_REQUEST", "params.color must be an RGB or RGBA array"
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 255
            for value in color
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.color values must be integers from 0 to 255"
            )
        _optional_bool(params, "open_in_gui")
    elif action == "layer.scale":
        _string(params, "input_path")
        _string(params, "output_path")
        _layer_selector(params)
        if "width" not in params and "height" not in params:
            raise AdapterError(
                "INVALID_REQUEST", "layer.scale requires width or height"
            )
        for field in ("width", "height"):
            if field in params:
                _positive_int(params, field)
        _optional_bool(params, "keep_aspect")
        _optional_bool(params, "open_in_gui")
    elif action == "layer.translate":
        _string(params, "input_path")
        _string(params, "output_path")
        _layer_selector(params)
        _number(params, "x")
        _number(params, "y")
        _optional_bool(params, "open_in_gui")
    elif action == "config.set":
        if params.get("file", "gimprc") not in {"gimprc", "sessionrc"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.file must be gimprc or sessionrc"
            )
        _string(params, "key")
        if "value" not in params or isinstance(params["value"], (dict, list)):
            raise AdapterError("INVALID_REQUEST", "params.value must be a scalar")
        _optional_bool(params, "restart")


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
            "UNSUPPORTED_ACTION", "action is not supported", {"action": action}
        )
    timeout_ms = data.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
        raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
    if not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS:
        raise AdapterError(
            "INVALID_REQUEST",
            f"timeout_ms must be between {MIN_TIMEOUT_MS} and {MAX_TIMEOUT_MS}",
        )
    target = _mapping(data.get("target"), "target")
    params = _mapping(data.get("params"), "params")
    validate_action_params(action, params)
    return ActionRequest(
        request_id=request_id,
        adapter=adapter,
        action=action,
        timeout_ms=timeout_ms,
        target=target,
        params=params,
        verify=_verification(data.get("verify")),
    )
