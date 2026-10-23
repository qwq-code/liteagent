from __future__ import annotations

import time
import json
import urllib.request
from pathlib import Path
from typing import Any

from .accessibility_state import (
    active_window_node,
    inspect_debug_session_state,
    inspect_debug_variables,
    inspect_section_state,
    inspect_view_state,
    requested_code_window,
)
from .command import CommandRunner
from .controller_accessibility import inspect_source_breakpoint
from .errors import AdapterError
from .jsonfiles import is_subset, load_json


def extension_state(runner: CommandRunner, extension_id: str) -> dict[str, Any]:
    result = runner.run(
        ["code", "--list-extensions", "--show-versions"],
        timeout=60,
        error_code="VSCODE_NOT_READY",
        error_message="could not list VS Code extensions",
    )
    entries = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
    ids = [entry.split("@", 1)[0].lower() for entry in entries]
    return {
        "extension_id": extension_id,
        "installed": extension_id.lower() in ids,
        "entries": entries,
        "ids": ids,
    }


def window_state(runner: CommandRunner, expected_name: str) -> dict[str, Any]:
    result = runner.run(["wmctrl", "-lx"], check=False, timeout=10)
    lines = [line for line in result["stdout"].splitlines() if "code.Code" in line]
    expected = expected_name.lower()
    matches = [line for line in lines if expected in line.lower()]
    return {"expected_name": expected_name, "windows": lines, "matches": matches}


def accessibility_text(max_nodes: int = 60_000) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:5000/accessibility", timeout=30
        ) as response:
            tree = json.load(response).get("AT", "")
        if tree:
            return {
                "text": tree,
                "application_count": 1 if "code" in tree.lower() else 0,
                "node_count": tree.count("<"),
                "truncated": False,
                "source": "osworld_control",
            }
    except Exception:
        pass
    try:
        import pyatspi
    except ImportError as exc:
        raise AdapterError(
            "VSCODE_NOT_READY", "pyatspi is unavailable", str(exc), 503
        ) from exc

    desktop = pyatspi.Registry.getDesktop(0)
    apps = []
    for index in range(desktop.childCount):
        app = desktop.getChildAtIndex(index)
        name = (getattr(app, "name", "") or "").lower()
        if "code" in name or "visual studio" in name:
            apps.append(app)
    pieces: list[str] = []
    nodes = 0
    stack = list(reversed(apps))
    while stack and nodes < max_nodes:
        node = stack.pop()
        nodes += 1
        for attribute in ("name", "description"):
            try:
                value = getattr(node, attribute, "")
                if value:
                    pieces.append(str(value))
            except Exception:
                pass
        try:
            text = node.queryText()
            value = text.getText(0, text.characterCount)
            if value:
                pieces.append(value)
        except Exception:
            pass
        try:
            children = [node.getChildAtIndex(index) for index in range(node.childCount)]
            stack.extend(reversed(children))
        except Exception:
            pass
    return {
        "text": "\n".join(pieces),
        "application_count": len(apps),
        "node_count": nodes,
        "truncated": bool(stack),
        "source": "direct_pyatspi",
    }


def _check(
    spec: dict[str, Any],
    context: dict[str, Any],
    runner: CommandRunner,
) -> dict[str, Any]:
    check_type = spec["type"]
    if check_type == "file":
        path = Path(str(spec.get("path") or context.get("path")))
        observed = {
            "path": str(path),
            "exists": path.exists(),
            "is_file": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
        }
        passed = observed["is_file"]
        if "content" in spec:
            observed["content"] = (
                path.read_text(encoding="utf-8") if path.is_file() else None
            )
            passed = passed and observed["content"] == spec["content"]
    elif check_type == "text":
        path = Path(str(spec["path"]))
        observed = path.read_text(encoding="utf-8") if path.is_file() else None
        passed = observed == spec["content"]
    elif check_type == "text_snapshot":
        path = Path(str(spec["path"]))
        actual = path.read_text(encoding="utf-8") if path.is_file() else None
        expected_content = spec["content"]
        expected_total = spec["total_chars"]
        expected_truncated = spec["truncated"]
        start_char = spec.get("start_char", 0)
        max_chars = spec.get(
            "max_chars", len(expected_content) if isinstance(expected_content, str) else 0
        )
        valid_window = (
            type(start_char) is int and start_char >= 0
            and type(max_chars) is int and max_chars >= 0
            and isinstance(actual, str) and start_char <= len(actual)
        )
        end_char = min(start_char + max_chars, len(actual)) if valid_window else None
        window_matches = (
            valid_window
            and isinstance(expected_content, str)
            and actual[start_char:end_char] == expected_content
        )
        prefix_matches = (
            isinstance(actual, str)
            and isinstance(expected_content, str)
            and actual.startswith(expected_content)
        )
        observed = {
            "path": str(path),
            "is_file": path.is_file(),
            "total_chars": len(actual) if isinstance(actual, str) else None,
            "returned_chars": (
                len(expected_content) if isinstance(expected_content, str) else None
            ),
            "prefix_matches": prefix_matches,
            "source_start_char": start_char,
            "source_end_char": end_char,
            "window_matches": window_matches,
        }
        passed = (
            isinstance(expected_total, int)
            and not isinstance(expected_total, bool)
            and isinstance(expected_truncated, bool)
            and isinstance(actual, str)
            and isinstance(expected_content, str)
            and len(actual) == expected_total
            and window_matches
        )
        if passed:
            passed = expected_truncated == (end_char < expected_total)
    elif check_type == "json_subset":
        path = Path(str(spec["path"]))
        expected = spec["expected"]
        expected_type = list if isinstance(expected, list) else dict
        observed = load_json(path, expected_type, expected_type())
        passed = is_subset(expected, observed)
    elif check_type == "keybinding":
        path = Path(str(spec["path"]))
        observed = load_json(path, list, [])
        passed = spec["binding"] in observed
    elif check_type == "extension":
        observed = extension_state(runner, str(spec["extension_id"]))
        passed = observed["installed"]
    elif check_type == "workspace_open":
        observed = window_state(runner, str(spec["expected_name"]))
        passed = bool(observed["matches"])
    elif check_type == "accessibility":
        observed = accessibility_text()
        full_text = observed["text"]
        include = list(spec.get("include", []))
        exclude = list(spec.get("exclude", []))
        passed = observed["application_count"] > 0
        passed = passed and all(value in full_text for value in include)
        passed = passed and all(value not in full_text for value in exclude)
        preview_start = max(0, full_text.find("VARIABLES") - 500)
        observed = {
            **{key: value for key, value in observed.items() if key != "text"},
            "text_preview": full_text[preview_start : preview_start + 4000],
            "include_matches": {value: value in full_text for value in include},
            "exclude_matches": {value: value in full_text for value in exclude},
        }
    elif check_type == "vscode_view_active":
        observed = inspect_view_state(
            runner,
            str(spec["window_id"]),
            str(spec["view"]),
        )
        passed = observed["active"]
    elif check_type == "vscode_section_expanded":
        observed = inspect_section_state(
            runner,
            str(spec["window_id"]),
            str(spec["name"]),
        )
        passed = observed["match_count"] == 1 and observed["expanded"]
    elif check_type == "vscode_debug_session":
        observed = inspect_debug_session_state(runner, str(spec["window_id"]))
        passed = observed["active"]
        started_session = context.get("session")
        if (
            isinstance(started_session, dict)
            and started_session.get("active") is True
            and observed.get("phase") == "inactive"
        ):
            observed = {
                **observed,
                "transition": "started_then_ended",
                "guidance": (
                    "Debugging started, then execution ended before verification. "
                    "This is not evidence of a missing debugger. Check the current "
                    "source and latest terminal output for normal exit or an error. "
                    "To inspect variables, use file.read_text to choose an executable "
                    "line and debug.breakpoint.set before restarting. A breakpoint "
                    "pauses before its line executes, so later assignments have not "
                    "run yet. Do not repeat debug.start unchanged."
                ),
            }
    elif check_type == "vscode_breakpoint_set":
        path = Path(str(spec["path"])).expanduser().resolve()
        line = int(spec["line"])
        window = requested_code_window(runner, str(spec["window_id"]))
        active_window_node(window)
        observed = inspect_source_breakpoint(window.window_id, window.title, path, line)
        passed = (
            path.is_file()
            and observed["breakpoints_heading_count"] == 1
            and observed["match_count"] == 1
            and observed["checked_count"] == 1
        )
    elif check_type == "vscode_debug_state":
        observed = inspect_debug_session_state(runner, str(spec["window_id"]))
        expected_states = spec.get("states", [spec.get("state")])
        passed = observed["phase"] in expected_states
    elif check_type == "vscode_debug_variables":
        observed = inspect_debug_variables(
            runner,
            str(spec["window_id"]),
            int(spec.get("max_items", 256)),
        )
        expected_names = spec.get("item_names")
        passed = observed["session"]["active"]
        if expected_names is not None:
            passed = passed and observed["item_names"] == expected_names
    elif check_type == "workspace_files":
        matches = context.get("matches")
        passed = (
            isinstance(matches, list)
            and all(isinstance(match, dict) for match in matches)
            and len(matches) >= int(spec.get("min_matches", 0))
        )
        observed = {
            "match_count": len(matches) if isinstance(matches, list) else None,
            "matches": matches,
            "workspace_roots": context.get("workspace_roots"),
            "workspace_name": context.get("workspace_name"),
        }
    else:
        raise AdapterError(
            "INVALID_ARGUMENT", f"unsupported verifier type: {check_type}"
        )
    return {
        "type": check_type,
        "passed": passed,
        "observed": observed,
        "expected": spec,
    }


def verify_specs(
    specs: list[dict[str, Any]],
    context: dict[str, Any],
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    command = runner or CommandRunner()
    checks = []
    for spec in specs:
        try:
            checks.append(_check(spec, context, command))
        except (AdapterError, OSError, ValueError, KeyError) as exc:
            checks.append(
                {
                    "type": spec.get("type"),
                    "passed": False,
                    "error": str(exc),
                    "expected": spec,
                }
            )
    passed = bool(checks) and all(check.get("passed", False) for check in checks)
    return {
        "passed": passed,
        "checks": checks,
        "observed_state": context,
        "expected_state": specs,
        "error_code": None if passed else "VERIFICATION_FAILED",
        "details": None if passed else "one or more checks failed",
    }


def wait_for_verification(
    specs: list[dict[str, Any]],
    context: dict[str, Any],
    runner: CommandRunner,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, timeout)
    last = verify_specs(specs, context, runner)
    while not last["passed"] and time.monotonic() < deadline:
        time.sleep(0.25)
        last = verify_specs(specs, context, runner)
    return last
