from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import jsonschema


GUI_ACTION_NAMES = (
    "click",
    "double_click",
    "type",
    "press",
    "hotkey",
    "scroll",
    "drag",
    "wait",
)

_FALLBACK_REASON = {"type": "string", "minLength": 1}
_SECONDS = {"type": "number", "minimum": 0, "maximum": 10}
_COORDINATE = {"type": "integer", "minimum": 0}
_KEY = {"type": "string", "minLength": 1}

# Qwen frequently serializes numeric GUI fields as quoted decimal tokens.  The
# public schema accepts that representation, while the execution boundary
# canonicalizes it before command construction.  Exponents, whitespace, and
# non-finite values are deliberately excluded so this remains a representation
# conversion rather than an alias or argument-repair path.
_UNSIGNED_INTEGER_STRING = r"[0-9]+"
_SIGNED_INTEGER_STRING = r"-?[0-9]+"
_DECIMAL_STRING = r"(?:0|[0-9]+(?:\.[0-9]+)?)"


def _numeric_or_string(
    numeric_schema: dict[str, Any], pattern: str, description: str
) -> dict[str, Any]:
    return {
        "anyOf": [
            copy.deepcopy(numeric_schema),
            {
                "type": "string",
                "pattern": f"^(?:{pattern})$",
                "description": description,
            },
        ]
    }


def _action_schema(
    action: str,
    properties: dict[str, dict[str, Any]],
    required: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": [action]},
            "fallback_reason": _FALLBACK_REASON,
            **properties,
        },
        "required": ["action", "fallback_reason", *required],
        "additionalProperties": False,
    }


_COORDINATE_COMPAT = _numeric_or_string(
    _COORDINATE,
    _UNSIGNED_INTEGER_STRING,
    "Non-negative decimal integer serialized as a JSON string",
)
_SECONDS_COMPAT = _numeric_or_string(
    _SECONDS,
    _DECIMAL_STRING,
    "Finite non-negative decimal number serialized as a JSON string",
)
_AMOUNT_COMPAT = _numeric_or_string(
    {"type": "integer"},
    _SIGNED_INTEGER_STRING,
    "Signed decimal integer serialized as a JSON string",
)

# The public schema keeps the original action shape and bounds, widening only
# the numeric representation observed from Qwen.  No action, field, alias, or
# default is added.
GUI_ACTION_SCHEMA: dict[str, Any] = {
    "oneOf": [
        _action_schema(
            "click",
            {
                "x": _COORDINATE_COMPAT,
                "y": _COORDINATE_COMPAT,
                "seconds": _SECONDS_COMPAT,
            },
            ("x", "y"),
        ),
        _action_schema(
            "double_click",
            {
                "x": _COORDINATE_COMPAT,
                "y": _COORDINATE_COMPAT,
                "seconds": _SECONDS_COMPAT,
            },
            ("x", "y"),
        ),
        _action_schema(
            "type",
            {"text": {"type": "string"}, "seconds": _SECONDS_COMPAT},
            ("text",),
        ),
        _action_schema(
            "press",
            {"key": _KEY, "seconds": _SECONDS_COMPAT},
            ("key",),
        ),
        _action_schema(
            "hotkey",
            {
                "keys": {
                    "type": "array",
                    "items": _KEY,
                    "minItems": 2,
                    "maxItems": 6,
                },
                "seconds": _SECONDS_COMPAT,
            },
            ("keys",),
        ),
        _action_schema(
            "scroll",
            {"amount": _AMOUNT_COMPAT, "seconds": _SECONDS_COMPAT},
            ("amount",),
        ),
        _action_schema(
            "drag",
            {
                "x": _COORDINATE_COMPAT,
                "y": _COORDINATE_COMPAT,
                "to_x": _COORDINATE_COMPAT,
                "to_y": _COORDINATE_COMPAT,
                "seconds": _SECONDS_COMPAT,
            },
            ("x", "y", "to_x", "to_y"),
        ),
        _action_schema("wait", {"seconds": _SECONDS_COMPAT}, ("seconds",)),
    ]
}

_NUMERIC_FIELDS: dict[str, dict[str, str]] = {
    "click": {"x": "coordinate", "y": "coordinate", "seconds": "seconds"},
    "double_click": {
        "x": "coordinate",
        "y": "coordinate",
        "seconds": "seconds",
    },
    "type": {"seconds": "seconds"},
    "press": {"seconds": "seconds"},
    "hotkey": {"seconds": "seconds"},
    "scroll": {"amount": "amount", "seconds": "seconds"},
    "drag": {
        "x": "coordinate",
        "y": "coordinate",
        "to_x": "coordinate",
        "to_y": "coordinate",
        "seconds": "seconds",
    },
    "wait": {"seconds": "seconds"},
}


def _coerce_numeric_string(value: Any, *, field: str, kind: str) -> Any:
    if not isinstance(value, str):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"GUI field {field!r} must be finite")
        return value
    if kind == "coordinate":
        pattern = _UNSIGNED_INTEGER_STRING
    elif kind == "amount":
        pattern = _SIGNED_INTEGER_STRING
    elif kind == "seconds":
        pattern = _DECIMAL_STRING
    else:  # pragma: no cover - the field table is module-local and exhaustive
        raise AssertionError(f"unknown GUI numeric kind: {kind}")
    if re.fullmatch(pattern, value) is None:
        raise ValueError(
            f"GUI field {field!r} must be a finite decimal {kind}, got {value!r}"
        )
    if kind in {"coordinate", "amount"}:
        try:
            return int(value, 10)
        except ValueError as exc:  # pragma: no cover - regex guards this path
            raise ValueError(f"GUI field {field!r} is not a valid integer") from exc
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - regex guards this path
        raise ValueError(f"GUI field {field!r} is not a valid decimal") from exc
    if not decimal.is_finite() or decimal < 0 or decimal > 10:
        raise ValueError(
            f"GUI field {field!r} must be between 0 and 10 seconds, got {value!r}"
        )
    return float(decimal)


def normalize_gui_arguments(
    arguments: Mapping[str, Any], *, validate: bool = True
) -> dict[str, Any]:
    """Return canonical GUI arguments without mutating the model payload.

    ``validate=True`` is used at the direct GUI execution boundary.  No fields
    are added, removed, or inferred by the conversion.
    """
    if not isinstance(arguments, Mapping):
        raise TypeError("GUI arguments must be an object")
    original = dict(arguments)
    if validate:
        jsonschema.validate(original, GUI_ACTION_SCHEMA)
    action = original.get("action")
    fields = _NUMERIC_FIELDS.get(str(action), {})
    normalized = copy.deepcopy(original)
    for field, kind in fields.items():
        if field in normalized:
            normalized[field] = _coerce_numeric_string(
                normalized[field], field=field, kind=kind
            )
    if validate:
        jsonschema.validate(normalized, GUI_ACTION_SCHEMA)
    return normalized


# A delegated GUI turn deliberately contains no coordinates.  Qwen supplies a
# visual intent and Holo grounds that intent against the current screenshot.
# Keep this schema separate from ``GUI_ACTION_SCHEMA`` so a configured hybrid
# agent cannot accidentally expose the coordinate-bearing fallback directly.
GUI_REQUEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2000,
            "description": (
                "Describe the one visible UI operation to ground, including the "
                "target label or visual relation when useful. The grounder receives "
                "only this request and the screenshot, not your earlier tool results. "
                "For typing, include the exact literal text in this request. A paste "
                "shortcut uses the current system clipboard; it does not compose or "
                "copy text from earlier results. For content longer than this request "
                "can hold, search for an Adapter text-writing action."
            ),
        },
        "fallback_reason": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000,
            "description": "Why a deterministic Adapter action cannot perform this operation",
        },
    },
    "required": ["intent"],
    "additionalProperties": False,
}


def build_gui_command(arguments: dict[str, Any]) -> str:
    """Validate one model-selected GUI action and translate it without defaults."""
    normalized = normalize_gui_arguments(arguments)
    action = normalized["action"]
    if action == "click":
        return f"pyautogui.click({normalized['x']}, {normalized['y']})"
    if action == "double_click":
        return f"pyautogui.doubleClick({normalized['x']}, {normalized['y']}, interval=0.15)"
    if action == "type":
        return f"pyautogui.write({normalized['text']!r}, interval=0.02)"
    if action == "press":
        return f"pyautogui.press({normalized['key']!r})"
    if action == "hotkey":
        keys = ", ".join(repr(key) for key in normalized["keys"])
        return f"pyautogui.hotkey({keys})"
    if action == "scroll":
        return f"pyautogui.scroll({normalized['amount']})"
    if action == "drag":
        return (
            f"pyautogui.moveTo({normalized['x']}, {normalized['y']}); "
            f"pyautogui.dragTo({normalized['to_x']}, {normalized['to_y']}, duration=0.5)"
        )
    if action == "wait":
        return "WAIT"
    raise AssertionError(f"validated unsupported GUI action: {action}")
