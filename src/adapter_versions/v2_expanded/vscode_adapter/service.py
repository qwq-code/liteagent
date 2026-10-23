from __future__ import annotations

import logging
import os
import threading
import time

from flask import Flask, jsonify, request

from .errors import AdapterError, error_payload
from .lifecycle import VscodeLifecycle
from .schema import ADAPTER_NAME, parse_action_request
from .worker_runner import WorkerRunner


def create_app(
    lifecycle: VscodeLifecycle | None = None,
    runner: WorkerRunner | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.logger.setLevel(logging.INFO)
    vscode_lifecycle = lifecycle or VscodeLifecycle()
    worker = runner or WorkerRunner()
    action_lock = threading.Lock()

    def failure(
        error: AdapterError, request_id: str | None = None, duration_ms: int = 0
    ):
        return (
            jsonify(
                {
                    "request_id": request_id,
                    "status": "error",
                    "result": None,
                    "verification": None,
                    "error": error_payload(error),
                    "duration_ms": duration_ms,
                    "logs": [],
                }
            ),
            error.http_status,
        )

    @app.get("/health")
    def health():
        status = vscode_lifecycle.health()
        status.update(
            {"status": "ok", "adapter": ADAPTER_NAME, "service_pid": os.getpid()}
        )
        return jsonify(status)

    @app.post("/v1/prepare")
    def prepare():
        started = time.monotonic()
        try:
            data = request.get_json(silent=True) or {}
            timeout_ms = data.get("timeout_ms", 10_000)
            if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
                raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
            result = vscode_lifecycle.prepare(max(0.1, min(timeout_ms, 120_000) / 1000))
            return jsonify(
                {
                    "status": "ok",
                    "adapter": ADAPTER_NAME,
                    "result": result,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        except AdapterError as error:
            return failure(
                error, duration_ms=round((time.monotonic() - started) * 1000)
            )

    def execute(parsed):
        if not action_lock.acquire(timeout=parsed.timeout_ms / 1000):
            raise AdapterError(
                "OPERATION_TIMEOUT",
                "timed out waiting for the VS Code action lock",
                http_status=504,
            )
        try:
            return worker.run(parsed)
        finally:
            action_lock.release()

    @app.post("/v1/actions")
    @app.post("/v1/verify")
    def actions():
        parsed = None
        started = time.monotonic()
        raw = request.get_json(silent=True)
        raw_request_id = raw.get("request_id") if isinstance(raw, dict) else None
        try:
            parsed = parse_action_request(raw)
            result = execute(parsed)
            return jsonify(
                {
                    "request_id": parsed.request_id,
                    "status": "ok",
                    "result": result.get("result", {}),
                    "verification": result.get("verification"),
                    "error": None,
                    "duration_ms": result.get("duration_ms", 0),
                    "logs": result.get("logs", []),
                }
            )
        except AdapterError as error:
            return failure(
                error,
                parsed.request_id if parsed else raw_request_id,
                round((time.monotonic() - started) * 1000),
            )

    @app.post("/v1/shutdown")
    def shutdown():
        try:
            data = request.get_json(silent=True) or {}
            timeout_ms = data.get("timeout_ms", 10_000)
            if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
                raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
            return jsonify(
                {
                    "status": "ok",
                    "adapter": ADAPTER_NAME,
                    "result": vscode_lifecycle.shutdown(
                        max(0.1, min(timeout_ms, 120_000) / 1000)
                    ),
                }
            )
        except AdapterError as error:
            return failure(error)

    return app


def main() -> None:
    host = os.environ.get("VSCODE_ADAPTER_HOST", "0.0.0.0")
    port = int(os.environ.get("VSCODE_ADAPTER_PORT", "8771"))
    create_app().run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
