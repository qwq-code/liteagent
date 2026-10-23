from __future__ import annotations

import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterator

from .errors import AdapterError


ACCESSIBILITY_URL = "http://127.0.0.1:5000/accessibility"
STATE_NS = "https://accessibility.ubuntu.example.org/ns/state"
ATTR_NS = "https://accessibility.ubuntu.example.org/ns/attributes"


def _state(node: ET.Element, name: str) -> bool:
    return node.get(f"{{{STATE_NS}}}{name}") == "true"


def _visible(node: ET.Element) -> bool:
    return _state(node, "showing") and _state(node, "visible")


def _summary(node: ET.Element) -> dict[str, Any]:
    return {
        "name": node.get("name", ""),
        "role": node.tag,
        "states": {
            name: _state(node, name)
            for name in ("active", "checked", "expanded", "showing", "visible")
        },
    }


def _walk(node: ET.Element) -> Iterator[ET.Element]:
    yield node
    for child in node:
        yield from _walk(child)


def fetch_accessibility_root(timeout: float = 5.0) -> ET.Element:
    try:
        with urllib.request.urlopen(ACCESSIBILITY_URL, timeout=timeout) as response:
            payload = json.load(response)
    except Exception as exc:
        raise AdapterError(
            "VSCODE_CONTROL_UNAVAILABLE",
            "OSWorld accessibility control endpoint is unavailable",
            str(exc),
            503,
        ) from exc
    tree = payload.get("AT") if isinstance(payload, dict) else None
    if not isinstance(tree, str) or not tree:
        raise AdapterError(
            "VSCODE_CONTROL_UNAVAILABLE",
            "OSWorld accessibility control endpoint returned no tree",
            http_status=503,
        )
    try:
        return ET.fromstring(tree)
    except ET.ParseError as exc:
        raise AdapterError(
            "VSCODE_CONTROL_UNAVAILABLE",
            "OSWorld accessibility tree is malformed",
            str(exc),
            503,
        ) from exc


def _active_code_frame(root: ET.Element, window_title: str) -> ET.Element:
    frames = [
        frame
        for application in root.findall("application")
        if "code" in application.get("name", "").casefold()
        or "visual studio" in application.get("name", "").casefold()
        for frame in application.findall("frame")
        if frame.get("name") == window_title and _state(frame, "active")
    ]
    if len(frames) != 1:
        raise AdapterError(
            "WINDOW_NOT_FOUND",
            "requested VS Code window is not the unique active controller frame",
            {"window_title": window_title, "match_count": len(frames)},
            422,
        )
    return frames[0]


def _control_matches(name: str, labels: tuple[str, ...]) -> bool:
    observed = " ".join(name.split()).casefold()
    return any(
        observed == label or observed.startswith(f"{label} ") for label in labels
    )


def _view_label_matches(name: str, expected_label: str) -> bool:
    observed = " ".join(name.split()).casefold()
    expected = expected_label.casefold()
    return observed == expected or observed.startswith(f"{expected} (") or observed.startswith(
        f"{expected}:"
    )


def _view_heading_matches(name: str, expected_label: str) -> bool:
    return " ".join(name.split()).casefold().startswith(
        f"{expected_label.casefold()}:"
    )


def inspect_view(window_id: str, window_title: str, expected_label: str) -> dict[str, Any]:
    """Inspect one visible VS Code view through the OSWorld controller tree."""
    frame = _active_code_frame(fetch_accessibility_root(), window_title)
    matches = [
        node
        for node in _walk(frame)
        if _view_label_matches(node.get("name", ""), expected_label)
    ]
    visible_matches = [node for node in matches if _visible(node)]
    selected_matches = [
        node
        for node in visible_matches
        if _state(node, "selected") or _state(node, "checked")
    ]
    heading_matches = [
        node
        for node in visible_matches
        if _view_heading_matches(node.get("name", ""), expected_label)
    ]
    return {
        "window_id": window_id,
        "window_title": window_title,
        "expected_label": expected_label,
        "active": bool(selected_matches or heading_matches),
        "label_match_count": len(matches),
        "visible_match_count": len(visible_matches),
        "selected_match_count": len(selected_matches),
        "heading_match_count": len(heading_matches),
        "selected_matches": [_summary(node) for node in selected_matches[:8]],
        "source": "osworld_accessibility_control",
    }


def inspect_debug_session(window_id: str, window_title: str) -> dict[str, Any]:
    frame = _active_code_frame(fetch_accessibility_root(), window_title)
    return inspect_debug_session_from_frame(window_id, window_title, frame)


def _quick_inputs(frame: ET.Element) -> list[dict[str, Any]]:
    observations = []
    for widget in _walk(frame):
        classes = widget.get(f"{{{ATTR_NS}}}class", "").split()
        if "quick-input-widget" not in classes or not _visible(widget):
            continue
        inputs = [
            node for node in _walk(widget)
            if node.tag == "combo-box" and _visible(node)
        ]
        lists = [
            node for node in _walk(widget)
            if node.tag == "list-box" and _visible(node)
        ]
        options = [
            node.get("name", "") for choices in lists for node in _walk(choices)
            if node.tag == "list-item" and _visible(node)
        ]
        observations.append({
            "prompts": [
                node.get(f"{{{ATTR_NS}}}placeholder") or node.get("name", "")
                for node in inputs
            ],
            "list_names": [node.get("name", "") for node in lists],
            "options": options[:32],
            "option_count": len(options),
            "truncated": len(options) > 32,
        })
    return observations


def inspect_debug_variables(
    window_id: str, window_title: str, max_items: int
) -> dict[str, Any]:
    root = fetch_accessibility_root()
    frame = _active_code_frame(root, window_title)
    session = inspect_debug_session_from_frame(window_id, window_title, frame)
    if not session["paused"]:
        raise AdapterError(
            "VSCODE_NOT_READY",
            "the requested VS Code window has no observable paused debug session",
            session,
            422,
        )
    trees = [
        node
        for node in _walk(frame)
        if node.tag == "tree"
        and _visible(node)
        and " ".join(node.get("name", "").split()).casefold() == "debug variables"
    ]
    if len(trees) != 1:
        raise AdapterError(
            "WINDOW_NOT_FOUND",
            "the standard Debug Variables tree was not uniquely visible",
            {"window_id": window_id, "match_count": len(trees)},
            422,
        )
    items = [
        _summary(node)
        for node in _walk(trees[0])
        if node is not trees[0] and node.tag == "tree-item" and _visible(node)
    ]
    returned = items[:max_items]
    return {
        "window_id": window_id,
        "window_title": window_title,
        "session": session,
        "tree": _summary(trees[0]),
        "items": returned,
        "item_names": [str(item["name"]) for item in returned],
        "item_count": len(items),
        "truncated": len(returned) < len(items),
        "source": "osworld_accessibility_control",
    }


def inspect_debug_session_from_frame(
    window_id: str, window_title: str, frame: ET.Element
) -> dict[str, Any]:
    controls = [
        node
        for node in _walk(frame)
        if node.tag == "push-button"
        and _visible(node)
        and _control_matches(
            node.get("name", ""), ("continue", "pause", "stop", "disconnect")
        )
    ]
    names = [node.get("name", "") for node in controls]
    continue_count = sum(_control_matches(name, ("continue",)) for name in names)
    pause_count = sum(_control_matches(name, ("pause",)) for name in names)
    stop_count = sum(_control_matches(name, ("stop",)) for name in names)
    disconnect_count = sum(_control_matches(name, ("disconnect",)) for name in names)
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
    variables_trees = [
        node
        for node in _walk(frame)
        if node.tag == "tree"
        and _visible(node)
        and " ".join(node.get("name", "").split()).casefold() == "debug variables"
    ]
    return {
        "window_id": window_id,
        "window_title": window_title,
        "source": "osworld_accessibility_control",
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
        "controls": [_summary(node) for node in controls[:16]],
        "variables_tree_count": len(variables_trees),
        "variables_trees": [_summary(node) for node in variables_trees[:8]],
        "quick_inputs": _quick_inputs(frame),
    }


def inspect_source_breakpoint(
    window_id: str, window_title: str, path: Path, line: int
) -> dict[str, Any]:
    frame = _active_code_frame(fetch_accessibility_root(), window_title)
    breakpoints_headings = [
        node
        for node in _walk(frame)
        if node.tag == "heading"
        and _visible(node)
        and " ".join(node.get("name", "").split()).casefold() == "breakpoints"
    ]
    resolved = path.expanduser().resolve()
    labels = {str(resolved)}
    try:
        labels.add(f"~/{resolved.relative_to('/home/user').as_posix()}")
    except ValueError:
        pass
    prefix = f"{resolved.name} {line}, "
    matches = [
        node
        for node in _walk(frame)
        if node.tag == "check-box"
        and _visible(node)
        and node.get("name", "").startswith(prefix)
        and node.get("name", "")[len(prefix) :] in labels
    ]
    checked = [node for node in matches if _state(node, "checked")]
    return {
        "window_id": window_id,
        "window_title": window_title,
        "path": str(resolved),
        "line": line,
        "breakpoints_heading_count": len(breakpoints_headings),
        "match_count": len(matches),
        "checked_count": len(checked),
        "matches": [_summary(node) for node in matches[:8]],
        "source": "osworld_accessibility_control",
    }


def wait_for_breakpoints_view(
    window_id: str,
    window_title: str,
    path: Path,
    line: int,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, timeout)
    last: dict[str, Any] | None = None
    while True:
        try:
            last = inspect_source_breakpoint(window_id, window_title, path, line)
            if last["breakpoints_heading_count"] == 1:
                return last
        except AdapterError as exc:
            last = {"error": {"code": exc.code, "message": exc.message}}
        if time.monotonic() >= deadline:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "VS Code did not expose one visible Breakpoints section",
                {"path": str(path), "line": line, "last_observation": last},
                422,
            )
        time.sleep(0.25)


def wait_for_source_breakpoint(
    window_id: str,
    window_title: str,
    path: Path,
    line: int,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, timeout)
    last: dict[str, Any] | None = None
    while True:
        try:
            last = inspect_source_breakpoint(window_id, window_title, path, line)
            if (
                last["breakpoints_heading_count"] == 1
                and last["match_count"] == 1
                and last["checked_count"] == 1
            ):
                return last
        except AdapterError as exc:
            last = {"error": {"code": exc.code, "message": exc.message}}
        if time.monotonic() >= deadline:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "VS Code did not expose the requested checked source breakpoint",
                {"path": str(path), "line": line, "last_observation": last},
                422,
            )
        time.sleep(0.25)
