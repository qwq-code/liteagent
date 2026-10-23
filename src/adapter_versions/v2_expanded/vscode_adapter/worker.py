from __future__ import annotations

import json
import sys
import time
from typing import Any

from .actions import KEYBINDINGS_PATH, SETTINGS_PATH, VscodeActions
from .errors import AdapterError, error_payload
from .verifier import verify_specs, wait_for_verification


def _default_specs(
    action: str,
    params: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    if action in {
        "settings.update",
        "debugging.configure",
        "diagnostics.configure",
        "editor.configure",
        "files.configure",
        "explorer.set_exclusion",
    }:
        return [
            {
                "type": "json_subset",
                "path": result.get("path", str(SETTINGS_PATH)),
                "expected": result["values"],
            }
        ]
    if action == "keybindings.ensure":
        return [
            {
                "type": "keybinding",
                "path": result.get("path", str(KEYBINDINGS_PATH)),
                "binding": result["binding"],
            }
        ]
    if action == "extension.install":
        return [{"type": "extension", "extension_id": result["extension_id"]}]
    if action in {"workspace.open", "editor.open_file"}:
        return [{"type": "workspace_open", "expected_name": result["expected_name"]}]
    if action == "workspace.find_files":
        # Discovery is read-only: verify the returned shape itself so the model
        # receives the exact paths instead of an empty-spec false failure.
        return [{"type": "workspace_files", "min_matches": 0}]
    if action in {
        "workspace.write",
        "workspace.set_folders",
        "workspace.add_folders",
    }:
        return [
            {
                "type": "json_subset",
                "path": result["path"],
                "expected": {"folders": result["workspace"]["folders"]},
            }
        ]
    if action == "file.create":
        return [{"type": "file", "path": result["path"], "content": result["content"]}]
    if action == "file.read_text":
        return [
            {
                "type": "text_snapshot",
                "path": result["path"],
                "content": result["content"],
                "total_chars": result["total_chars"],
                "truncated": result["truncated"],
                "start_char": params.get("start_char", 0),
                "max_chars": params.get("max_chars", 20_000),
            }
        ]
    if action in {"file.replace_literal", "file.indent_lines"}:
        return [{"type": "text", "path": result["path"], "content": result["content"]}]
    if action == "ui.expand_section":
        return [
            {
                "type": "vscode_section_expanded",
                "window_id": result["window_id"],
                "name": result["section"]["name"],
            }
        ]
    if action == "ui.open_view":
        return [
            {
                "type": "vscode_view_active",
                "window_id": result["window_id"],
                "view": result["view"],
            }
        ]
    if action == "debug.breakpoint.set":
        return [
            {
                "type": "vscode_breakpoint_set",
                "window_id": result["window_id"],
                "path": result["path"],
                "line": result["line"],
            }
        ]
    if action == "debug.start":
        return [
            {
                "type": "vscode_debug_session",
                "window_id": result["window_id"],
            }
        ]
    if action == "debug.session.wait":
        return [
            {
                "type": "vscode_debug_state",
                "window_id": result["window_id"],
                "state": params["state"],
            }
        ]
    if action == "debug.continue":
        return [
            {
                "type": "vscode_debug_state",
                "window_id": result["window_id"],
                "states": ["inactive", "running"],
            }
        ]
    if action == "debug.stop":
        return [
            {
                "type": "vscode_debug_state",
                "window_id": result["window_id"],
                "state": "inactive",
            }
        ]
    if action == "debug.variables.read":
        variables = result["variables"]
        return [
            {
                "type": "vscode_debug_variables",
                "window_id": result["window_id"],
                "max_items": int(params.get("max_items", 256)),
                "item_names": variables["item_names"],
            }
        ]
    return []


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    requested_action = payload["action"]
    requested_params = dict(payload.get("params") or {})
    timeout_seconds = max(0.1, int(payload.get("timeout_ms", 45_000)) / 1000 - 1)
    actions = VscodeActions()
    started = time.monotonic()
    logs = [{"level": "info", "message": f"starting {requested_action}"}]

    action = requested_action
    params = requested_params

    result = actions.dispatch(action, params, timeout_seconds)
    specs = payload.get("verify") or _default_specs(action, params, result)
    if action == "workspace.inspect" and not specs:
        verification = {
            "passed": True,
            "checks": [{"type": "inspect", "passed": True, "observed": result}],
            "observed_state": result,
            "expected_state": [],
            "error_code": None,
            "details": None,
        }
    elif action in {
        "ui.open_view",
        "ui.expand_section",
        "debug.breakpoint.set",
        "debug.start",
        "debug.session.wait",
        "debug.continue",
        "debug.stop",
        "debug.variables.read",
    }:
        remaining = max(0.1, timeout_seconds - (time.monotonic() - started))
        verification = wait_for_verification(
            specs,
            result,
            actions.runner,
            min(remaining, 10),
        )
    else:
        verification = verify_specs(specs, result, actions.runner)
    if not verification["passed"]:
        raise AdapterError(
            "VERIFICATION_FAILED", "operation verification failed", verification, 422
        )
    duration_ms = round((time.monotonic() - started) * 1000)
    logs.append({"level": "info", "message": f"completed {action} in {duration_ms} ms"})
    return {
        "result": result,
        "verification": verification,
        "logs": logs,
    }


def main() -> None:
    try:
        output = execute(json.load(sys.stdin))
        json.dump(output, sys.stdout, ensure_ascii=True)
    except AdapterError as error:
        json.dump(
            {"error": {**error_payload(error), "http_status": error.http_status}},
            sys.stdout,
            ensure_ascii=True,
        )
        raise SystemExit(1)
    except Exception as exc:
        json.dump(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "unexpected VS Code worker failure",
                    "details": str(exc),
                    "http_status": 500,
                }
            },
            sys.stdout,
            ensure_ascii=True,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
