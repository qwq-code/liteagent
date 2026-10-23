from __future__ import annotations

import json
import sys
import time
from typing import Any

from .actions import VlcActions
from .errors import AdapterError, error_payload
from .verifier import verify_specs


def _default_specs(
    action: str,
    params: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    if action in {"config.update", "preferences.configure"}:
        return [{"type": "config", "path": result["path"], "values": result["values"]}]
    if action == "playback.status":
        return [{"type": "status"}]
    if action == "playback.find_local":
        return [{"type": "local_discovery"}]
    if action == "playback.open":
        return [
            {
                "type": "playback",
                "source": result["source"],
                "loop": bool(result["loop_requested"]),
            }
        ]
    if action == "window.set_fullscreen":
        return [{"type": "window_fullscreen", "enabled": result["enabled"]}]
    if action == "media.extract_audio":
        return [
            {"type": "media", "path": result["output_path"], "stream_type": "audio"}
        ]
    if action == "media.extract_subtitles":
        return [
            {
                "type": "subtitle",
                "path": result["output_path"],
                "sha256": result["sha256"],
                "cue_count": result["cue_count"],
            }
        ]
    if action in {"media.transcode_clip", "media.flip_video"}:
        return [
            {"type": "media", "path": result["output_path"], "stream_type": "video"}
        ]
    if action == "media.extract_frame":
        return [
            {"type": "media", "path": result["output_path"], "stream_type": "video"}
        ]
    return []


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    requested_action = payload["action"]
    requested_params = dict(payload.get("params") or {})
    timeout_seconds = max(0.1, int(payload.get("timeout_ms", 60_000)) / 1000 - 1)
    actions = VlcActions()
    started = time.monotonic()
    logs = [{"level": "info", "message": f"starting {requested_action}"}]

    action = requested_action
    params = requested_params

    result = actions.dispatch(action, params, timeout_seconds)
    specs = payload.get("verify") or _default_specs(action, params, result)
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
                    "message": "unexpected VLC worker failure",
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
