from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterator

from .command import CommandRunner
from .controller_accessibility import (
    inspect_debug_session as inspect_controller_debug_session,
    inspect_debug_variables as inspect_controller_debug_variables,
    inspect_view as inspect_controller_view,
)
from .errors import AdapterError


VIEW_LABELS = {
    "explorer": "Explorer",
    "search": "Search",
    "source_control": "Source Control",
    "run_and_debug": "Run and Debug",
    "extensions": "Extensions",
}

DEBUG_VARIABLES_TREE_LABEL = "VARIABLES"
DEBUG_CONTINUE_CONTROLS = ("continue",)
DEBUG_PAUSE_CONTROLS = ("pause",)
DEBUG_STOP_CONTROLS = ("stop",)
DEBUG_DISCONNECT_CONTROLS = ("disconnect",)
DEBUG_PROGRESS_CONTROLS = DEBUG_CONTINUE_CONTROLS + DEBUG_PAUSE_CONTROLS
DEBUG_TERMINATION_CONTROLS = DEBUG_DISCONNECT_CONTROLS + DEBUG_STOP_CONTROLS
DEBUG_SESSION_PHASES = frozenset({"inactive", "paused", "running"})
# F5 should return a diagnostic promptly when VS Code is waiting for a
# debugger/extension choice.  The outer worker timeout is much larger for
# other Adapter operations, but holding the model for the whole request hides
# the actionable UI state and turns a recoverable dependency issue into a
# transport timeout.
DEBUG_START_OBSERVATION_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class WindowRecord:
    window_id: str
    wm_class: str
    title: str


def _load_atspi() -> Any:
    try:
        import pyatspi
    except ImportError as exc:
        raise AdapterError(
            "VSCODE_NOT_READY", "pyatspi is unavailable", str(exc), 503
        ) from exc
    return pyatspi


def _canonical_window_id(value: str) -> str:
    try:
        return f"0x{int(value, 16):x}"
    except (TypeError, ValueError) as exc:
        raise AdapterError(
            "INVALID_ARGUMENT", f"invalid wmctrl window ID: {value}"
        ) from exc


def _wmctrl_windows(runner: CommandRunner) -> list[WindowRecord]:
    result = runner.run(
        ["wmctrl", "-lx"],
        check=False,
        timeout=10,
        error_code="VSCODE_NOT_READY",
        error_message="could not inspect VS Code windows",
    )
    if result["returncode"] != 0:
        raise AdapterError(
            "VSCODE_NOT_READY",
            "could not inspect VS Code windows",
            result,
            503,
        )
    windows: list[WindowRecord] = []
    for line in result["stdout"].splitlines():
        fields = line.split(None, 4)
        if len(fields) != 5:
            continue
        raw_id, _desktop, wm_class, _host, title = fields
        try:
            window_id = _canonical_window_id(raw_id)
        except AdapterError:
            continue
        windows.append(WindowRecord(window_id, wm_class, title))
    return windows


def requested_code_window(runner: CommandRunner, window_id: str) -> WindowRecord:
    expected_id = _canonical_window_id(window_id)
    matches = [
        window for window in _wmctrl_windows(runner) if window.window_id == expected_id
    ]
    if len(matches) != 1:
        raise AdapterError(
            "WINDOW_NOT_FOUND",
            "requested wmctrl window ID did not identify exactly one window",
            {"window_id": window_id, "match_count": len(matches)},
            422,
        )
    window = matches[0]
    if "code" not in window.wm_class.casefold():
        raise AdapterError(
            "WINDOW_NOT_FOUND",
            "requested window is not a VS Code window",
            {
                "window_id": window.window_id,
                "wm_class": window.wm_class,
                "title": window.title,
            },
            422,
        )
    return window


def _children(node: Any) -> Iterator[Any]:
    try:
        count = int(node.childCount)
    except Exception:
        return
    for index in range(count):
        try:
            yield node.getChildAtIndex(index)
        except Exception:
            continue


def _walk(node: Any) -> Iterator[Any]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(list(_children(current))))


def _name(node: Any) -> str:
    try:
        return str(getattr(node, "name", "") or "")
    except Exception:
        return ""


def _role(node: Any) -> str:
    try:
        return str(node.getRoleName() or "").strip().casefold().replace(" ", "-")
    except Exception:
        return ""


def _has_state(node: Any, atspi: Any, state_name: str) -> bool:
    state = getattr(atspi, f"STATE_{state_name.upper()}", None)
    if state is None:
        return False
    try:
        return bool(node.getState().contains(state))
    except Exception:
        return False


def _state_summary(node: Any, atspi: Any) -> dict[str, bool]:
    return {
        state: _has_state(node, atspi, state)
        for state in (
            "active",
            "checked",
            "expanded",
            "expandable",
            "focused",
            "selected",
            "showing",
            "visible",
        )
    }


def _node_summary(node: Any, atspi: Any) -> dict[str, Any]:
    return {
        "name": _name(node),
        "role": _role(node),
        "states": _state_summary(node, atspi),
    }


def _code_applications(atspi: Any) -> list[Any]:
    desktop = atspi.Registry.getDesktop(0)
    applications = []
    for app in _children(desktop):
        app_name = _name(app).casefold()
        if "code" in app_name or "visual studio" in app_name:
            applications.append(app)
    return applications


def _top_level_windows(application: Any) -> Iterator[Any]:
    for node in _children(application):
        if _role(node) in {"dialog", "frame", "window"}:
            yield node


def active_window_node(window: WindowRecord, atspi: Any | None = None) -> Any:
    module = atspi or _load_atspi()
    code_windows = [
        node for app in _code_applications(module) for node in _top_level_windows(app)
    ]
    candidates = [node for node in code_windows if _name(node) == window.title]
    active = [node for node in code_windows if _has_state(node, module, "active")]
    if len(active) != 1 or len(candidates) != 1 or active[0] is not candidates[0]:
        raise AdapterError(
            "WINDOW_NOT_FOUND",
            "requested VS Code window is not the unique active accessible frame",
            {
                "window_id": window.window_id,
                "title": window.title,
                "title_match_count": len(candidates),
                "active_code_window_count": len(active),
                "active_titles": [_name(node) for node in active[:8]],
            },
            422,
        )
    return active[0]


def wait_for_active_window(
    runner: CommandRunner,
    window_id: str,
    timeout: float,
) -> WindowRecord:
    deadline = time.monotonic() + max(0.1, timeout)
    last_error: AdapterError | None = None
    while True:
        try:
            window = requested_code_window(runner, window_id)
            active_window_node(window)
            return window
        except AdapterError as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            assert last_error is not None
            raise last_error
        time.sleep(0.1)


def _is_showing(node: Any, atspi: Any) -> bool:
    return _has_state(node, atspi, "showing") and _has_state(node, atspi, "visible")


def _view_label_matches(name: str, expected_label: str) -> bool:
    observed = " ".join(name.split()).casefold()
    expected = expected_label.casefold()
    return observed == expected or observed.startswith(f"{expected} (") or observed.startswith(
        f"{expected}:"
    )


def _view_heading_matches(name: str, expected_label: str) -> bool:
    """Recognize the visible panel heading form used by some VS Code builds."""
    observed = " ".join(name.split()).casefold()
    return observed.startswith(f"{expected_label.casefold()}:")


def _control_label_matches(name: str, labels: tuple[str, ...]) -> bool:
    observed = " ".join(name.split()).casefold()
    return any(
        observed == label or observed.startswith(f"{label} ") for label in labels
    )


def _visible_debug_controls(frame: Any, atspi: Any) -> list[Any]:
    labels = DEBUG_PROGRESS_CONTROLS + DEBUG_TERMINATION_CONTROLS
    return [
        node
        for node in _walk(frame)
        if _is_showing(node, atspi)
        and _role(node) in {"button", "push-button"}
        and _control_label_matches(_name(node), labels)
    ]


def _visible_variables_trees(frame: Any, atspi: Any) -> list[Any]:
    return [
        node
        for node in _walk(frame)
        if _role(node) == "tree"
        and _is_showing(node, atspi)
        and " ".join(_name(node).split()).casefold()
        == DEBUG_VARIABLES_TREE_LABEL.casefold()
    ]


def inspect_debug_session_state(
    runner: CommandRunner,
    window_id: str,
) -> dict[str, Any]:
    window = requested_code_window(runner, window_id)
    try:
        return inspect_controller_debug_session(window.window_id, window.title)
    except AdapterError as exc:
        if exc.code != "VSCODE_CONTROL_UNAVAILABLE":
            raise

    atspi = _load_atspi()
    frame = active_window_node(window, atspi)
    controls = _visible_debug_controls(frame, atspi)
    control_names = [_name(node) for node in controls]
    continue_count = sum(
        _control_label_matches(name, DEBUG_CONTINUE_CONTROLS) for name in control_names
    )
    pause_count = sum(
        _control_label_matches(name, DEBUG_PAUSE_CONTROLS) for name in control_names
    )
    stop_count = sum(
        _control_label_matches(name, DEBUG_STOP_CONTROLS) for name in control_names
    )
    disconnect_count = sum(
        _control_label_matches(name, DEBUG_DISCONNECT_CONTROLS)
        for name in control_names
    )
    termination_count = stop_count + disconnect_count
    paused = continue_count == 1 and pause_count == 0 and termination_count == 1
    running = pause_count == 1 and continue_count == 0 and termination_count == 1
    no_controls = continue_count == pause_count == termination_count == 0
    phase = (
        "paused"
        if paused
        else "running"
        if running
        else "inactive"
        if no_controls
        else "ambiguous"
    )
    variables_trees = _visible_variables_trees(frame, atspi)
    return {
        "window_id": window.window_id,
        "window_title": window.title,
        "active": paused or running,
        "paused": paused,
        "running": running,
        "phase": phase,
        "has_progress_control": bool(continue_count or pause_count),
        "has_termination_control": bool(termination_count),
        "continue_control_count": continue_count,
        "pause_control_count": pause_count,
        "stop_control_count": stop_count,
        "disconnect_control_count": disconnect_count,
        "controls": [_node_summary(node, atspi) for node in controls[:16]],
        "variables_tree_count": len(variables_trees),
        "variables_trees": [_node_summary(node, atspi) for node in variables_trees[:8]],
    }


def wait_for_debug_session(
    runner: CommandRunner,
    window_id: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(
        0.1,
        min(float(timeout), DEBUG_START_OBSERVATION_TIMEOUT_SECONDS),
    )
    last: dict[str, Any] | None = None
    while True:
        try:
            state = inspect_debug_session_state(runner, window_id)
            last = state
            if state["active"]:
                return state
        except AdapterError as exc:
            last = {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            }
        if time.monotonic() >= deadline or (last and last.get("quick_inputs")):
            raise AdapterError(
                "VSCODE_NOT_READY",
                "VS Code did not expose an active debug session",
                {
                    "window_id": window_id,
                    "last_observation": last,
                    "guidance": (
                        "Inspect last_observation.quick_inputs and the current screenshot. "
                        "F5 may be waiting for a debugger or launch configuration choice. "
                        "Use gui_request to select the appropriate visible option, then "
                        "continue from the resulting screen; do not press F5 again while "
                        "the picker is open. An available debugger option is not a missing "
                        "extension. If VS Code reports a missing "
                        "debugger or extension, search the public catalog for "
                        "extension.install and call it with the model-selected "
                        "Marketplace identifier or local VSIX path and its "
                        "matching source_type; then retry debug.start. If the "
                        "window is stale, obtain a fresh window_id with "
                        "editor.open_file. Do not retry F5 unchanged."
                    ),
                },
                422,
            )
        time.sleep(0.1)


def wait_for_debug_state(
    runner: CommandRunner,
    window_id: str,
    expected_phase: str,
    timeout: float,
) -> dict[str, Any]:
    if expected_phase not in DEBUG_SESSION_PHASES:
        raise AdapterError(
            "INVALID_ARGUMENT",
            f"unsupported debug session phase: {expected_phase}",
        )
    deadline = time.monotonic() + max(0.1, timeout)
    last: dict[str, Any] | None = None
    while True:
        try:
            state = inspect_debug_session_state(runner, window_id)
            last = state
            if state["phase"] == expected_phase:
                return state
        except AdapterError as exc:
            last = {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            }
        if time.monotonic() >= deadline:
            raise AdapterError(
                "VSCODE_NOT_READY",
                f"VS Code did not expose a {expected_phase} debug session",
                {
                    "window_id": window_id,
                    "expected_phase": expected_phase,
                    "last_observation": last,
                },
                422,
            )
        time.sleep(0.1)


def inspect_debug_variables(
    runner: CommandRunner,
    window_id: str,
    max_items: int = 256,
) -> dict[str, Any]:
    window = requested_code_window(runner, window_id)
    try:
        return inspect_controller_debug_variables(
            window.window_id, window.title, max_items
        )
    except AdapterError as exc:
        if exc.code != "VSCODE_CONTROL_UNAVAILABLE":
            raise

    atspi = _load_atspi()
    frame = active_window_node(window, atspi)
    session = inspect_debug_session_state(runner, window.window_id)
    if not session["paused"]:
        raise AdapterError(
            "VSCODE_NOT_READY",
            "the requested VS Code window has no observable paused debug session",
            session,
            422,
        )
    trees = _visible_variables_trees(frame, atspi)
    if len(trees) != 1:
        raise AdapterError(
            "WINDOW_NOT_FOUND",
            "the standard VARIABLES tree was not uniquely visible",
            {
                "window_id": window.window_id,
                "window_title": window.title,
                "match_count": len(trees),
                "matches": [_node_summary(node, atspi) for node in trees[:8]],
            },
            422,
        )
    items = [
        _node_summary(node, atspi)
        for node in _walk(trees[0])
        if node is not trees[0]
        and _role(node) == "tree-item"
        and _is_showing(node, atspi)
    ]
    returned = items[:max_items]
    return {
        "window_id": window.window_id,
        "window_title": window.title,
        "session": session,
        "tree": _node_summary(trees[0], atspi),
        "items": returned,
        "item_names": [str(item["name"]) for item in returned],
        "item_count": len(items),
        "truncated": len(returned) < len(items),
    }


def inspect_view_state(
    runner: CommandRunner,
    window_id: str,
    view: str,
) -> dict[str, Any]:
    if view not in VIEW_LABELS:
        raise AdapterError("INVALID_ARGUMENT", f"unsupported VS Code view: {view}")
    atspi = _load_atspi()
    window = requested_code_window(runner, window_id)
    frame = active_window_node(window, atspi)
    expected_label = VIEW_LABELS[view]
    matches = [
        node
        for node in _walk(frame)
        if _view_label_matches(_name(node), expected_label)
    ]
    visible_matches = [node for node in matches if _is_showing(node, atspi)]
    selected_matches = [
        node
        for node in visible_matches
        if any(_has_state(node, atspi, state) for state in ("selected", "checked"))
    ]
    heading_matches = [
        node
        for node in visible_matches
        if _view_heading_matches(_name(node), expected_label)
    ]
    result = {
        "window_id": window.window_id,
        "window_title": window.title,
        "view": view,
        "expected_label": expected_label,
        "active": bool(selected_matches or heading_matches),
        "label_match_count": len(matches),
        "visible_match_count": len(visible_matches),
        "selected_match_count": len(selected_matches),
        "heading_match_count": len(heading_matches),
        "selected_matches": [
            _node_summary(node, atspi) for node in selected_matches[:8]
        ],
    }
    if not matches:
        try:
            controller_result = inspect_controller_view(
                window.window_id, window.title, expected_label
            )
        except AdapterError:
            controller_result = None
        if isinstance(controller_result, dict) and controller_result.get(
            "label_match_count", 0
        ):
            return {"view": view, **controller_result}
    return result


def _action_names(node: Any) -> list[str]:
    try:
        actions = node.queryAction()
    except Exception:
        return []
    names = []
    for index in range(actions.nActions):
        try:
            names.append(str(actions.getName(index) or ""))
        except Exception:
            continue
    return names


def _normalized_accessible_name(value: str) -> str:
    """Normalize human-entered accessible labels without changing their meaning."""
    return " ".join(value.split()).casefold()


def _section_candidates(frame: Any, name: str, atspi: Any) -> list[Any]:
    expected_name = _normalized_accessible_name(name)
    return [
        node
        for node in _walk(frame)
        if _normalized_accessible_name(_name(node)) == expected_name
        and _is_showing(node, atspi)
        and (
            _has_state(node, atspi, "expanded")
            or _has_state(node, atspi, "expandable")
            or "press" in _action_names(node)
        )
    ]


def inspect_section_state(
    runner: CommandRunner,
    window_id: str,
    name: str,
) -> dict[str, Any]:
    atspi = _load_atspi()
    window = requested_code_window(runner, window_id)
    frame = active_window_node(window, atspi)
    matches = _section_candidates(frame, name, atspi)
    summaries = [_node_summary(node, atspi) for node in matches[:8]]
    return {
        "window_id": window.window_id,
        "window_title": window.title,
        "name": name,
        "match_count": len(matches),
        "expanded": len(matches) == 1 and _has_state(matches[0], atspi, "expanded"),
        "matches": summaries,
    }


def _unique_section_node(
    runner: CommandRunner,
    window_id: str,
    name: str,
) -> tuple[WindowRecord, Any, Any]:
    atspi = _load_atspi()
    window = requested_code_window(runner, window_id)
    frame = active_window_node(window, atspi)
    matches = _section_candidates(frame, name, atspi)
    if len(matches) != 1:
        raise AdapterError(
            "SECTION_NOT_FOUND" if not matches else "AMBIGUOUS_SECTION",
            "the requested window was found, but the section name did not identify exactly one visible expandable element",
            {
                "window_id": window.window_id,
                "window_title": window.title,
                "name": name,
                "match_count": len(matches),
                "matches": [_node_summary(node, atspi) for node in matches[:8]],
                "guidance": (
                    "Keep the observed window_id. Choose a section exposed in the current "
                    "view or first establish the application state that exposes it; "
                    "changing the window ID will not create the missing section."
                ),
            },
            422,
        )
    return window, matches[0], atspi


def expand_accessible_section(
    runner: CommandRunner,
    window_id: str,
    name: str,
    timeout: float,
) -> dict[str, Any]:
    window, node, atspi = _unique_section_node(runner, window_id, name)
    before = _node_summary(node, atspi)
    if before["states"]["expanded"]:
        return {
            "name": name,
            "already_expanded": True,
            "action": None,
            "before": before,
            "after": before,
        }

    try:
        actions = node.queryAction()
    except Exception as exc:
        raise AdapterError(
            "VSCODE_NOT_READY",
            f"accessible section has no press action: {name}",
            _node_summary(node, atspi),
            422,
        ) from exc
    pressed = False
    for index in range(actions.nActions):
        if actions.getName(index) == "press":
            pressed = bool(actions.doAction(index))
            break
    if not pressed:
        raise AdapterError(
            "VSCODE_NOT_READY",
            f"AT-SPI press action failed for {name}",
            _node_summary(node, atspi),
            422,
        )

    deadline = time.monotonic() + max(0.1, timeout)
    last: dict[str, Any] | None = None
    while True:
        state = inspect_section_state(runner, window.window_id, name)
        last = state
        if state["match_count"] == 1 and state["expanded"]:
            return {
                "name": name,
                "already_expanded": False,
                "action": "press",
                "before": before,
                "after": state["matches"][0],
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    raise AdapterError(
        "VERIFICATION_FAILED",
        f"section did not become expanded after press: {name}",
        {
            "window_id": window.window_id,
            "window_title": window.title,
            "name": name,
            "before": before,
            "after": last,
        },
        422,
    )
