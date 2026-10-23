from __future__ import annotations

import time
from typing import Any

from . import accessibility_state
from .command import CommandRunner
from .errors import AdapterError


CONTROL_LABELS = {
    "continue": accessibility_state.DEBUG_CONTINUE_CONTROLS,
    "stop": accessibility_state.DEBUG_STOP_CONTROLS,
}
CONTROL_ACTIONS = ("click", "press")


def _error_observation(error: AdapterError) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
        }
    }


def _press_unique_control(
    runner: CommandRunner,
    window_id: str,
    control: str,
) -> dict[str, Any]:
    atspi = accessibility_state._load_atspi()
    window = accessibility_state.requested_code_window(runner, window_id)
    frame = accessibility_state.active_window_node(window, atspi)
    labels = CONTROL_LABELS[control]
    matches = [
        node
        for node in accessibility_state._visible_debug_controls(frame, atspi)
        if accessibility_state._control_label_matches(
            accessibility_state._name(node), labels
        )
    ]
    if len(matches) != 1:
        raise AdapterError(
            "VSCODE_NOT_READY",
            f"requested VS Code window did not expose one {control} control",
            {
                "window_id": window.window_id,
                "window_title": window.title,
                "control": control,
                "match_count": len(matches),
                "matches": [
                    accessibility_state._node_summary(node, atspi)
                    for node in matches[:8]
                ],
            },
            422,
        )
    node = matches[0]
    before = accessibility_state._node_summary(node, atspi)
    try:
        actions = node.queryAction()
    except Exception as exc:
        raise AdapterError(
            "VSCODE_NOT_READY",
            f"VS Code {control} control has no accessible action",
            before,
            422,
        ) from exc
    action_names = []
    for index in range(actions.nActions):
        try:
            action_names.append(str(actions.getName(index) or "").casefold())
        except Exception:
            action_names.append("")
    selected_action = next(
        (name for name in CONTROL_ACTIONS if name in action_names), None
    )
    if selected_action is None:
        raise AdapterError(
            "VSCODE_NOT_READY",
            f"VS Code {control} control has no click or press action",
            {"control": before, "action_names": action_names},
            422,
        )
    action_index = action_names.index(selected_action)
    try:
        performed = bool(actions.doAction(action_index))
    except Exception as exc:
        raise AdapterError(
            "VSCODE_NOT_READY",
            f"accessible {control} action failed",
            {"control": before, "action": selected_action},
            422,
        ) from exc
    if not performed:
        raise AdapterError(
            "VSCODE_NOT_READY",
            f"accessible {control} action was rejected",
            {"control": before, "action": selected_action},
            422,
        )
    return {
        "name": control,
        "accessible_action": selected_action,
        "before": before,
    }


def _wait_for_phase_change(
    runner: CommandRunner,
    window_id: str,
    *,
    allowed_phases: frozenset[str],
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, timeout)
    last: dict[str, Any] | None = None
    while True:
        try:
            state = accessibility_state.inspect_debug_session_state(runner, window_id)
            last = state
            if state["phase"] in allowed_phases:
                return state
        except AdapterError as exc:
            last = _error_observation(exc)
        if time.monotonic() >= deadline:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "debug session did not reach the required observable state",
                {
                    "window_id": window_id,
                    "allowed_phases": sorted(allowed_phases),
                    "last_observation": last,
                },
                422,
            )
        time.sleep(0.1)


def continue_debug_session(
    runner: CommandRunner,
    window_id: str,
    timeout: float,
) -> dict[str, Any]:
    before = accessibility_state.inspect_debug_session_state(runner, window_id)
    if not before["paused"]:
        raise AdapterError(
            "VSCODE_NOT_READY",
            "debug continue requires an observable paused session",
            before,
            422,
        )
    control = _press_unique_control(runner, window_id, "continue")
    after = _wait_for_phase_change(
        runner,
        window_id,
        allowed_phases=frozenset({"inactive", "running"}),
        timeout=timeout,
    )
    return {"control": control, "before": before, "after": after}


def stop_debug_session(
    runner: CommandRunner,
    window_id: str,
    timeout: float,
) -> dict[str, Any]:
    before = accessibility_state.inspect_debug_session_state(runner, window_id)
    if not before["active"]:
        raise AdapterError(
            "VSCODE_NOT_READY",
            "debug stop requires an observable active session",
            before,
            422,
        )
    control = _press_unique_control(runner, window_id, "stop")
    after = accessibility_state.wait_for_debug_state(
        runner,
        window_id,
        "inactive",
        timeout,
    )
    return {"control": control, "before": before, "after": after}
