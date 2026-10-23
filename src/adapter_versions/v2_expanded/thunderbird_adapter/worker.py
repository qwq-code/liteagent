from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from .actions import (
    ThunderbirdActions,
    semantic_preference_update,
    semantic_xulstore_update,
)
from .errors import AdapterError, error_payload
from .filter_contract import compile_filter_configuration
from .verifier import verify_specs


def _default_specs(
    action: str, params: dict[str, Any], result: dict[str, Any]
) -> list[dict[str, Any]]:
    if action == "mail.configure":
        update = semantic_preference_update(params)
        checks: list[dict[str, Any]] = []
        if update["values"] or update["remove_keys"]:
            checks.append(
                {
                    "type": "preferences",
                    "values": update["values"],
                    "absent": update["remove_keys"],
                }
            )
        xulstore = semantic_xulstore_update(params)
        if xulstore is not None:
            checks.append({"type": "json_path", "path": "xulstore.json", **xulstore})
        return checks
    if action == "preferences.update":
        return [
            {
                "type": "preferences",
                "values": params.get("values", {}),
                "absent": params.get("remove_keys", []),
            }
        ]
    if action == "xulstore.update":
        return [
            {
                "type": "json_path",
                "path": "xulstore.json",
                "keys": params["keys"],
                "value": params["value"],
            }
        ]
    if action == "folders.ensure_local":
        return [{"type": "folders", "names": params["names"]}]
    if action == "filters.configure":
        configuration = compile_filter_configuration(params)
        checks: list[dict[str, Any]] = [
            {"type": "filters", "filters": configuration["filters"]}
        ]
        if configuration["local_folders"]:
            checks.insert(
                0, {"type": "folders", "names": configuration["local_folders"]}
            )
        return checks
    if action == "messages.export_eml":
        return [
            {
                "type": "exported_eml",
                "destination": result["destination"],
                "filenames": [Path(item["path"]).name for item in result["messages"]],
            }
        ]
    if action == "contacts.export_csv":
        return [
            {
                "type": "exported_contacts",
                "path": params["output_path"],
                "columns": result["columns"],
                "contact_count": result["contact_count"],
            }
        ]
    if action == "attachments.save":
        return [
            {
                "type": "attachment_file",
                "path": result["output_path"],
                "size_bytes": result["size_bytes"],
                "sha256": result["sha256"],
            }
        ]
    if action == "accounts.remove":
        return [
            {
                "type": "account_removed",
                "email": params["email"],
                "hostnames": result.get("hostnames", []),
            }
        ]
    if action == "compose.attach":
        return [
            {
                "type": "accessibility",
                "kind": "attachment",
                "value": Path(params["attachment_path"]).stem,
            }
        ]
    if action == "compose.set_recipients":
        return [
            {"type": "accessibility", "kind": "recipient", "value": address}
            for address in params["recipients"]
        ]
    if action == "ui.prefill_account_setup":
        return [
            {"type": "accessibility", "kind": "text", "value": params["email"]},
            {"type": "accessibility", "kind": "name", "value": "Password"},
        ]
    return []


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    requested_action = payload["action"]
    requested_params = dict(payload.get("params") or {})
    timeout_seconds = max(0.1, int(payload.get("timeout_ms", 60_000)) / 1000 - 1)
    actions = ThunderbirdActions()
    started = time.monotonic()
    logs = [{"level": "info", "message": f"starting {requested_action}"}]
    action = requested_action
    params = requested_params
    result = actions.dispatch(action, params, timeout_seconds)
    specs = payload.get("verify") or _default_specs(action, params, result)
    verification = verify_specs(specs)
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
        json.dump(execute(json.load(sys.stdin)), sys.stdout, ensure_ascii=True)
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
                    "message": "unexpected Thunderbird worker failure",
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
