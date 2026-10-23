from __future__ import annotations

import json
import sys
import time
from typing import Any

from .actions import OSActions
from .errors import AdapterError, error_payload
from .verifier import verify_specs


def _default_specs(
    action: str, params: dict[str, Any], result: dict[str, Any]
) -> list[dict[str, Any]]:
    if action == "filesystem.find":
        return [
            {
                "type": "filesystem_query",
                "roots": result["roots"],
                "name_patterns": result["name_patterns"],
                "kind": result["kind"],
                "recursive": result["recursive"],
                "max_depth": result["max_depth"],
                "match_count": result["match_count"],
                "returned_count": result["returned_count"],
                "truncated": result["truncated"],
            },
            *[
                {
                    "type": "path",
                    "path": item["path"],
                    "kind": item["kind"],
                }
                for item in result["matches"]
            ],
        ]
    if action == "filesystem.copy":
        return [{"type": "path", "path": result["destination"], "kind": "file"}]
    if action == "filesystem.create_directory":
        return [{"type": "path", "path": result["path"], "kind": "directory"}]
    if action == "filesystem.copy_to_directories":
        return [
            {"type": "path", "path": path, "kind": "file"} for path in result["copied"]
        ]
    if action == "filesystem.rename":
        return [{"type": "path", "path": result["destination"]}]
    if action == "filesystem.set_permissions":
        return [{"type": "path", "path": result["path"], "kind": "file"}]
    if action == "archive.compress_file":
        return [{"type": "path", "path": result["destination"], "kind": "file"}]
    if action == "text.append_each_line":
        return [{"type": "text", "path": result["path"], "content": result["content"]}]
    if action == "trash.list":
        return [
            {
                "type": "trash_listing",
                "offset": result["offset"],
                "max_results": result["max_results"],
            }
        ]
    if action == "trash.restore":
        return [
            {
                "type": "trash_restored",
                "trash_uri": result["trash_uri"],
                "original_path": result["original_path"],
            }
        ]
    if action == "terminal.default_profile.inspect":
        if "key" in result:
            return [{"type": "gsettings", "schema": result["schema"], "key": result["key"], "expected": result["observed"]}]
        return [{"type": "gsettings", "schema": "org.gnome.Terminal.ProfilesList", "key": "default", "expected": result["profile_id"]}]
    if action in {"desktop.set_setting", "terminal.default_profile.set_setting"}:
        return [
            {
                "type": "gsettings",
                "schema": result["schema"],
                "key": result["key"],
                "expected": result["expected"],
            }
        ]
    if action == "desktop.open_path":
        return [{"type": "path", "path": result["path"], "kind": result["kind"]}]
    if action == "desktop.set_wallpaper":
        return [
            {"type": "path", "path": result["image_path"], "kind": "file"},
            *[
                {
                    "type": "gsettings",
                    "schema": setting["schema"],
                    "key": setting["key"],
                    "expected": setting["observed"],
                }
                for setting in result["settings"]
            ],
        ]
    if action == "desktop.applications.inspect":
        return [
            {
                "type": "desktop_applications_query",
                "query": result["query"],
                "mime_type_prefixes": result["mime_type_prefixes"],
                "max_results": result["max_results"],
                "mime_offset": result["mime_offset"],
                "max_mime_types_per_application": result[
                    "max_mime_types_per_application"
                ],
            }
        ]
    if action == "desktop.mime_associations.set":
        return [
            {
                "type": "mime_association",
                "desktop_id": result["desktop_id"],
                "mime_types": result["mime_types"],
            }
        ]
    if action in {
        "notifications.configure",
        "desktop.set_accessibility_scale",
        "desktop.set_dim_inactive",
    }:
        return [
            {
                "type": "gsettings",
                "schema": setting["schema"],
                "key": setting["key"],
                "expected": setting["expected"],
            }
            for setting in result["settings"]
        ]
    if action == "desktop.favorites.list":
        return [
            {
                "type": "desktop_favorites_listing",
                "offset": result["offset"],
                "max_results": result["max_results"],
            }
        ]
    if action == "desktop.remove_favorite":
        return [
            {
                "type": "gsettings",
                "schema": "org.gnome.shell",
                "key": "favorite-apps",
                "expected": repr(result["after"]),
            }
        ]
    if action == "audio.set_volume":
        return [
            {"type": "volume", "sink": result["sink"], "percent": result["percent"]}
        ]
    if action == "system.set_timezone":
        return [{"type": "timezone", "timezone": result["timezone"]}]
    if action == "terminal.show_output":
        return [
            {
                "type": "command_result",
                # visible_terminal expands standalone ``~`` arguments before
                # invoking the direct argv command. Verify the exact argv
                # that actually ran, not the model's shorthand spelling.
                "argv": list(result.get("argv", params["argv"])),
                "returncodes": params.get("expected_returncodes", [0]),
            },
            {"type": "terminal", "contains": result["completion_marker"]},
        ]
    if action == "terminal.launch":
        return [
            {
                "type": "terminal_launch",
                "argv": list(params["argv"]),
                "returncodes": [0],
                "record_shell_history": bool(params.get("record_shell_history")),
            }
        ]
    if action == "clipboard.set":
        return [{"type": "clipboard", "text": result["text"]}]
    if action == "clipboard.get":
        return [{
            "type": "clipboard", "text": result["text"],
            "max_chars": int(params.get("max_chars", 100_000)),
            "character_count": result["character_count"],
        }]
    if action == "command.run":
        return [
            {
                "type": "command_result",
                "returncodes": params.get("expected_returncodes", [0]),
                "stdout_contains": params.get("stdout_contains", []),
                "stdout_excludes": params.get("stdout_excludes", []),
                "stderr_contains": params.get("stderr_contains", []),
                "stderr_excludes": params.get("stderr_excludes", []),
            }
        ]
    if action == "window.capture":
        return [{"type": "path", "path": result["output_path"], "kind": "file"}]
    if action == "document.convert":
        return [{"type": "path", "path": result["destination"], "kind": "file"}]
    if action in {"archive.create_zip", "archive.extract_zip"}:
        archive_check = {
            "type": "zip_archive",
            "path": result["archive_path"],
            "members": [
                {
                    "name": item["name"],
                    "kind": item["kind"],
                    "size_bytes": item["size_bytes"],
                }
                for item in result["members"]
            ],
        }
        if result["mode"] == "create":
            return [archive_check]
        return [
            archive_check,
            *[
                {"type": "path", "path": item["path"], "kind": "file"}
                for item in result["extracted_files"]
            ],
        ]
    if action == "pdf.outline.inspect":
        return [
            {
                "type": "pdf_outline_query",
                "input_path": result["input_path"],
                "source_sha256": result["source_sha256"],
                "source_page_count": result["source_page_count"],
                "outline_level": result["outline_level"],
                "section_count": result["section_count"],
                "offset": result["offset"],
                "max_sections": result["max_sections"],
            }
        ]
    if action in {"pdf.form.inspect", "pdf.tables.inspect"}:
        return [{"type": "path", "path": result["input_path"], "kind": "file"}]
    if action in {"pdf.pages.extract", "pdf.form.fill"}:
        return [{"type": "path", "path": result["output_path"], "kind": "file"}]
    if action in {"pdf.extract_text_batch", "image.extract_text_batch"}:
        return [
            {"type": "path", "path": item["path"], "kind": "file"}
            for item in result["files"]
            if item.get("status") == "ok"
        ]
    if action == "user.ensure_account":
        account = result["account"]
        return [
            {
                "type": "user",
                "username": account["username"],
                "home": account["home"],
                "mode": result["mode"],
            }
        ]
    if action == "package.install_snap":
        return [
            {
                "type": "package",
                "package": result["package"],
                "executable": result["package"],
            }
        ]
    return []


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload["action"]
    params = dict(payload.get("params") or {})
    timeout_seconds = max(0.1, int(payload.get("timeout_ms", 45_000)) / 1000 - 1)
    actions = OSActions()
    started = time.monotonic()
    logs = [{"level": "info", "message": f"starting {action}"}]
    result = actions.dispatch(action, params, timeout_seconds)
    specs = payload.get("verify") or _default_specs(action, params, result)
    verification = verify_specs(specs, result, actions.runner)
    if not verification["passed"]:
        raise AdapterError(
            "VERIFICATION_FAILED", "operation verification failed", verification, 422
        )
    logs.append(
        {
            "level": "info",
            "message": f"completed {action} in {round((time.monotonic() - started) * 1000)} ms",
        }
    )
    return {"result": result, "verification": verification, "logs": logs}


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
                    "message": "unexpected OS worker failure",
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
