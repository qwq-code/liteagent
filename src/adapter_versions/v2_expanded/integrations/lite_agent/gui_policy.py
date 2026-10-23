from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from .gui_actions import normalize_gui_arguments


GUI_HISTORY_LIMIT = 12
POINTER_TOLERANCE_PX = 16


def _normalized_gui_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    # Direct GUI actions may carry bounded numeric fields as JSON strings.  Use
    # the same representation conversion as execution for duplicate detection,
    # but retain the original event payload elsewhere for audit fidelity.  A
    # delegated ``gui_request`` has a different coordinate-free schema and is
    # left untouched by the normalizer.
    if arguments.get("action") in {
        "click",
        "double_click",
        "type",
        "press",
        "hotkey",
        "scroll",
        "drag",
        "wait",
    }:
        try:
            arguments = normalize_gui_arguments(arguments, validate=False)
        except (TypeError, ValueError):
            # Validation remains the execution boundary's responsibility.  If
            # a malformed proposal reaches policy, compare its raw shape so
            # repeated-error blocking remains fail-closed.
            pass
    return {
        key: value
        for key, value in arguments.items()
        if key not in {"fallback_reason", "command"}
    }


def _near(left: Any, right: Any) -> bool:
    return bool(
        isinstance(left, int)
        and not isinstance(left, bool)
        and isinstance(right, int)
        and not isinstance(right, bool)
        and abs(left - right) <= POINTER_TOLERANCE_PX
    )


def _same_gui_action(
    previous_arguments: Mapping[str, Any], current_arguments: Mapping[str, Any]
) -> bool:
    previous = _normalized_gui_arguments(previous_arguments)
    current = _normalized_gui_arguments(current_arguments)
    if previous.get("action") != current.get("action"):
        return False
    pointer_fields = {
        "click": ("x", "y"),
        "double_click": ("x", "y"),
        "drag": ("x", "y", "to_x", "to_y"),
    }.get(str(current.get("action")), ())
    if pointer_fields:
        return all(
            _near(previous.get(field), current.get(field)) for field in pointer_fields
        )
    return previous == current


def _event_gui_arguments(
    event: Any, *, request_layer: bool = False
) -> Mapping[str, Any]:
    """Select the matching layer for direct or delegated GUI events."""
    proposed = getattr(event, "proposed", {})
    if not isinstance(proposed, dict):
        return {}
    if request_layer:
        request = proposed.get("gui_request_arguments")
        if isinstance(request, Mapping):
            return request
    grounded = proposed.get("gui_arguments")
    if isinstance(grounded, Mapping):
        return grounded
    arguments = proposed.get("arguments")
    return arguments if isinstance(arguments, Mapping) else {}


def _recent_gui_events(events: Iterable[Any]) -> list[Any]:
    recent = []
    for previous in reversed(list(events)):
        kind = previous.proposed.get("kind")
        if kind == "adapter" and previous.executed:
            break
        if kind != "gui":
            continue
        recent.append(previous)
        if len(recent) >= GUI_HISTORY_LIMIT:
            break
    return recent


def repeated_gui_action_error(
    events: Iterable[Any],
    *,
    command: str,
    arguments: Mapping[str, Any],
    step: int,
    block_window_steps: int,
    blocked_action: str = "gui_action",
) -> dict[str, Any] | None:
    matches = [
        previous
        for previous in _recent_gui_events(events)
        if _same_gui_action(
            _event_gui_arguments(
                previous,
                request_layer=arguments.get("action") == "gui_request",
            ),
            arguments,
        )
    ]
    if len(matches) < 2:
        return None

    normalized = _normalized_gui_arguments(arguments)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return {
        "type": "RepeatedActionBlocked",
        "detail": (
            "the same or near-identical GUI action was already attempted twice in the "
            "recent GUI sequence; inspect the screenshot, search deterministic tools, "
            "or choose a materially different action"
        ),
        "executed": False,
        "previous_step": max(int(previous.step) for previous in matches),
        "blocked_action": blocked_action,
        "argument_signature": hashlib.sha256(encoded).hexdigest(),
        "error_signature": ["RepeatedGUIAction", command, []],
        "block_window_steps": block_window_steps,
        "blocked_until_step": step + block_window_steps,
        "fallback_reason": "repeated_gui_pattern",
    }
