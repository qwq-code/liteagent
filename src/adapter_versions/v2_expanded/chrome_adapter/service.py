from __future__ import annotations

import importlib.util
import logging
import os
import threading
import time

from flask import Flask, jsonify, request

from .errors import AdapterError, error_payload
from .lifecycle import ChromeLifecycle
from .schema import ADAPTER_NAME, parse_action_request
from .worker_runner import WorkerRunner


def create_app(
    lifecycle: ChromeLifecycle | None = None,
    runner: WorkerRunner | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.logger.setLevel(logging.INFO)
    chrome = lifecycle or ChromeLifecycle()
    worker = runner or WorkerRunner()
    action_lock = threading.Lock()

    def failure(error: AdapterError, request_id: str | None = None):
        return (
            jsonify(
                {
                    "request_id": request_id,
                    "status": "error",
                    "result": None,
                    "verification": None,
                    "error": error_payload(error),
                    "duration_ms": 0,
                    "logs": [],
                }
            ),
            error.http_status,
        )

    @app.get("/health")
    def health():
        status = chrome.health()
        status.update(
            {
                "status": "ok",
                "adapter": ADAPTER_NAME,
                "service_pid": os.getpid(),
                "pychrome_available": importlib.util.find_spec("pychrome") is not None,
            }
        )
        return jsonify(status)

    @app.post("/v1/prepare")
    def prepare():
        started = time.monotonic()
        data = request.get_json(silent=True) or {}
        timeout_ms = data.get("timeout_ms", 20_000)
        try:
            if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
                raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
            result = chrome.prepare(max(0.1, min(timeout_ms, 120_000) / 1000))
            return jsonify(
                {
                    "status": "ok",
                    "adapter": ADAPTER_NAME,
                    "result": result,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        except AdapterError as error:
            return failure(error)

    def execute(parsed):
        if parsed.action not in {
            "browser.inspect",
            "browser.ensure_running",
            "browser.restart",
        }:
            if not chrome.health()["chrome_ready"]:
                raise AdapterError(
                    "CHROME_NOT_READY",
                    "call /v1/prepare before executing Chrome actions",
                    http_status=503,
                )
        if not action_lock.acquire(timeout=parsed.timeout_ms / 1000):
            raise AdapterError(
                "TIMEOUT",
                "timed out waiting for the Chrome action lock",
                http_status=504,
            )
        try:
            return worker.run(parsed)
        finally:
            action_lock.release()

    def success(parsed, result):
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

    @app.post("/v1/actions")
    def actions():
        parsed = None
        raw = request.get_json(silent=True)
        raw_request_id = raw.get("request_id") if isinstance(raw, dict) else None
        try:
            parsed = parse_action_request(raw)
            return success(parsed, execute(parsed))
        except AdapterError as error:
            return failure(error, parsed.request_id if parsed else raw_request_id)

    @app.post("/v1/verify")
    def verify():
        parsed = None
        raw_request_id = None
        try:
            data = dict(request.get_json(silent=True) or {})
            raw_request_id = data.get("request_id")
            data["action"] = "browser.inspect"
            data.setdefault("params", {})
            parsed = parse_action_request(data)
            return success(parsed, execute(parsed))
        except AdapterError as error:
            return failure(error, parsed.request_id if parsed else raw_request_id)

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
                    "result": chrome.shutdown(
                        max(0.1, min(timeout_ms, 120_000) / 1000)
                    ),
                }
            )
        except AdapterError as error:
            return failure(error)

    return app


def main() -> None:
    host = os.environ.get("CHROME_ADAPTER_HOST", "0.0.0.0")
    port = int(os.environ.get("CHROME_ADAPTER_PORT", "8767"))
    create_app().run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
