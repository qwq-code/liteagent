from __future__ import annotations

import os
import time
from typing import Any

from flask import Flask, jsonify, request

from .actions import MultiAppsActions
from .errors import AdapterError
from .schema import ADAPTER_NAME, parse_action_request


def create_app(actions: MultiAppsActions | None = None) -> Flask:
    app = Flask(__name__)
    executor = actions or MultiAppsActions()

    @app.get("/health")
    def health() -> Any:
        return jsonify(
            {
                "status": "ok",
                "adapter": ADAPTER_NAME,
                "mode": "strict_generic",
                "service_pid": os.getpid(),
                "display": bool(os.environ.get("DISPLAY")),
                "dbus_session": bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")),
            }
        )

    @app.post("/v1/actions")
    def actions_endpoint() -> Any:
        started = time.monotonic()
        request_id = None
        try:
            parsed = parse_action_request(request.get_json(silent=True))
            request_id = parsed.request_id
            result = executor.dispatch(
                parsed.action, parsed.params, parsed.timeout_ms / 1000
            )
            return jsonify(
                {
                    "status": "ok",
                    "request_id": parsed.request_id,
                    "adapter": ADAPTER_NAME,
                    "action": parsed.action,
                    "result": result,
                    "verification": None,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        except AdapterError as exc:
            payload = exc.payload(request_id)
            payload["duration_ms"] = round((time.monotonic() - started) * 1000)
            return jsonify(payload), exc.status_code
        except Exception as exc:
            return jsonify(
                {
                    "status": "error",
                    "request_id": request_id,
                    "error_code": "INTERNAL_ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            ), 500

    return app


def main() -> None:
    create_app().run(
        host="0.0.0.0",
        port=int(os.environ.get("MULTI_APPS_ADAPTER_PORT", "8774")),
        threaded=True,
    )


if __name__ == "__main__":
    main()
