from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

import jsonschema


_COORDINATE = {
    "type": "integer",
    "minimum": 0,
    "maximum": 1000,
    "description": (
        "One normalized coordinate component as a single integer. "
        "Each coordinate field is separate; never supply an [x, y] array."
    ),
}
_ELEMENT = {
    "type": "string",
    "minLength": 1,
    "description": "Detailed visual description of the target UI element",
}
_KEY = {
    "type": "string",
    "minLength": 1,
    "description": (
        "One PyAutoGUI key name, such as up, down, left, right, enter, tab, esc, "
        "space, backspace, delete, ctrl, shift, alt, or a single character. "
        "Arrow keys use up/down/left/right (for example up, not arrowup)."
    ),
}


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


HOLO_GUI_TOOLS: list[dict[str, Any]] = [
    _tool(
        "click",
        "Click a visible UI element once with the left mouse button. Optional modifiers "
        "are held during this click and released afterward.",
        {
            "element": _ELEMENT,
            "x": _COORDINATE,
            "y": _COORDINATE,
            "modifiers": {
                "type": "array",
                "items": {"type": "string", "enum": ["ctrl", "shift", "alt", "win"]},
                "maxItems": 4,
                "uniqueItems": True,
                "description": (
                    "Modifier keys to hold during this click, for example ['shift'] "
                    "or ['ctrl', 'shift']. Omit or use [] for an ordinary click."
                ),
            },
        },
        ["element", "x", "y"],
    ),
    _tool(
        "double_click",
        "Double-click a visible UI element with the left mouse button",
        {"element": _ELEMENT, "x": _COORDINATE, "y": _COORDINATE},
        ["element", "x", "y"],
    ),
    _tool(
        "right_click",
        "Right-click a visible UI element to open its context menu",
        {"element": _ELEMENT, "x": _COORDINATE, "y": _COORDINATE},
        ["element", "x", "y"],
    ),
    _tool(
        "write",
        "Type text at the cursor in the currently focused element without clicking first. "
        "Only selected text is replaced; existing unselected text is not cleared. "
        "To replace a field's contents, first focus that field and select its text "
        "(for example with hotkey ctrl+a) on separate earlier turns, then write.",
        {
            "content": {"type": "string"},
            "press_enter": {
                "type": "boolean",
                "description": "Whether to press Enter after typing",
            },
        },
        ["content", "press_enter"],
    ),
    _tool(
        "press",
        "Press one keyboard key",
        {"key": _KEY},
        ["key"],
    ),
    _tool(
        "hotkey",
        "Press a keyboard shortcut by holding the listed keys together. "
        "To press a key repeatedly, use separate press actions on successive turns; "
        "repeating a key in this array does not press and release it repeatedly.",
        {
            "keys": {
                "type": "array",
                "items": _KEY,
                "minItems": 2,
                "maxItems": 6,
            }
        },
        ["keys"],
    ),
    _tool(
        "scroll",
        "Scroll at a visible location; positive amount scrolls up and negative scrolls down",
        {
            "element": _ELEMENT,
            "x": _COORDINATE,
            "y": _COORDINATE,
            "amount": {
                "type": "integer",
                "description": (
                    "Signed mouse-wheel clicks, not pixels. Positive scrolls up; negative "
                    "scrolls down. For example, 3 scrolls up three wheel clicks and -3 "
                    "scrolls down three. Use a small number of clicks, then inspect the "
                    "new view; thousands of clicks can move far past the target."
                ),
            },
        },
        ["element", "x", "y", "amount"],
    ),
    _tool(
        "drag",
        "Drag from one normalized screenshot coordinate to another",
        {
            "element": _ELEMENT,
            "x": _COORDINATE,
            "y": _COORDINATE,
            "to_x": _COORDINATE,
            "to_y": _COORDINATE,
        },
        ["element", "x", "y", "to_x", "to_y"],
    ),
    _tool(
        "wait",
        "Wait briefly for the desktop or application to update",
        {"seconds": {"type": "number", "minimum": 0.5, "maximum": 10}},
        ["seconds"],
    ),
    _tool(
        "answer",
        "Finish only after the latest screenshot confirms that the requested desktop state is complete",
        {"content": {"type": "string", "minLength": 1}},
        ["content"],
    ),
    _tool(
        "fail",
        "Stop when the task cannot be completed in the current desktop environment",
        {"reason": {"type": "string", "minLength": 1}},
        ["reason"],
    ),
]

# Holo is a visual grounder in the hybrid path, not an episode controller.
# Keep terminal tools available to the native diagnostic runner above, but
# never expose them to a delegated Qwen turn.
HOLO_GROUNDING_TOOLS: list[dict[str, Any]] = [
    copy.deepcopy(item)
    for item in HOLO_GUI_TOOLS
    if item["function"]["name"] not in {"answer", "fail"}
]
HOLO_GROUNDING_TOOL_NAMES = frozenset(
    item["function"]["name"] for item in HOLO_GROUNDING_TOOLS
)


_SCHEMAS = {
    item["function"]["name"]: item["function"]["parameters"] for item in HOLO_GUI_TOOLS
}


@dataclass(frozen=True)
class PreparedAction:
    name: str
    model_arguments: dict[str, Any]
    pixel_arguments: dict[str, Any]
    command: str | None
    settle_seconds: float
    terminal: str | None = None


def _pixel(value: int, extent: int) -> int:
    if extent <= 0:
        raise ValueError("screenshot extent must be positive")
    return min(extent - 1, int((value / 1000) * extent))


def _validate(name: str, arguments: dict[str, Any]) -> None:
    try:
        schema = _SCHEMAS[name]
    except KeyError as exc:
        raise ValueError(f"unsupported Holo tool: {name}") from exc
    jsonschema.validate(arguments, schema)


def validate_grounding_action(name: str, arguments: dict[str, Any]) -> None:
    """Validate one non-terminal action returned by the Holo grounder."""
    if name not in HOLO_GROUNDING_TOOL_NAMES:
        raise ValueError(f"Holo grounding must return a GUI action, got {name!r}")
    _validate(name, arguments)


def prepare_action(
    name: str,
    arguments: dict[str, Any],
    *,
    screenshot_width: int,
    screenshot_height: int,
    default_settle_seconds: float,
) -> PreparedAction:
    """Translate a validated Holo call without changing model-facing arguments."""
    _validate(name, arguments)
    model_arguments = dict(arguments)
    pixels: dict[str, Any] = {}

    def point(x_name: str, y_name: str) -> tuple[int, int]:
        x = _pixel(arguments[x_name], screenshot_width)
        y = _pixel(arguments[y_name], screenshot_height)
        pixels.update({x_name: x, y_name: y})
        return x, y

    if name in {"click", "double_click", "right_click"}:
        x, y = point("x", "y")
        method = {
            "click": "click",
            "double_click": "doubleClick",
            "right_click": "rightClick",
        }[name]
        suffix = ", interval=0.15" if name == "double_click" else ""
        command = f"pyautogui.{method}({x}, {y}{suffix})"
        if name == "click" and "modifiers" in arguments:
            modifiers = list(arguments["modifiers"])
            pixels["modifiers"] = modifiers
            if modifiers:
                # The controller prefixes a semicolon-terminated import line.
                # Start the compound statement on its own line; hold releases
                # the selected keys even if the click raises.
                command = f"\nwith pyautogui.hold({modifiers!r}):\n    {command}"
    elif name == "write":
        content = arguments["content"]
        if not content.isascii():
            raise ValueError("write currently supports ASCII text only")
        command = f"pyautogui.write({content!r}, interval=0.03)"
        if arguments["press_enter"]:
            command += "\npyautogui.press('enter')"
    elif name == "press":
        command = f"pyautogui.press({arguments['key']!r})"
    elif name == "hotkey":
        keys = ", ".join(repr(key) for key in arguments["keys"])
        command = f"pyautogui.hotkey({keys})"
    elif name == "scroll":
        x, y = point("x", "y")
        command = f"pyautogui.moveTo({x}, {y}); pyautogui.scroll({arguments['amount']})"
    elif name == "drag":
        x, y = point("x", "y")
        to_x, to_y = point("to_x", "to_y")
        command = (
            f"pyautogui.moveTo({x}, {y}); "
            f"pyautogui.dragTo({to_x}, {to_y}, duration=0.8)"
        )
    elif name == "wait":
        command = "WAIT"
    elif name in {"answer", "fail"}:
        return PreparedAction(
            name=name,
            model_arguments=model_arguments,
            pixel_arguments=pixels,
            command=None,
            settle_seconds=0.0,
            terminal="DONE" if name == "answer" else "FAIL",
        )
    else:  # pragma: no cover - schema and dispatch must stay in lockstep
        raise AssertionError(name)

    settle = (
        float(arguments["seconds"]) if name == "wait" else float(default_settle_seconds)
    )
    return PreparedAction(
        name=name,
        model_arguments=model_arguments,
        pixel_arguments=pixels,
        command=command,
        settle_seconds=settle,
    )
