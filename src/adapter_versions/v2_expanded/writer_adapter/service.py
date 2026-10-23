from __future__ import annotations

import importlib.util
import logging
import os
import threading
import time
from dataclasses import replace

from flask import Flask, g, jsonify, request

from .errors import AdapterError, error_payload
from .lifecycle import LibreOfficeLifecycle
from .schema import ADAPTER_NAME, parse_action_request
from .worker_runner import WorkerRunner


def create_app(
    lifecycle: LibreOfficeLifecycle | None = None, runner: WorkerRunner | None = None
) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.logger.setLevel(logging.INFO)
    office = lifecycle or LibreOfficeLifecycle()
    worker = runner or WorkerRunner()
    action_lock = threading.Lock()

    def failure(error: AdapterError, request_id: str | None = None):
        return jsonify(
            {
                "request_id": request_id,
                "status": "error",
                "result": None,
                "verification": None,
                "error": error_payload(error),
                "duration_ms": 0,
                "logs": [],
                **({"lifecycle": g.office_lifecycle} if hasattr(g, "office_lifecycle") else {}),
            }
        ), error.http_status

    @app.get("/health")
    def health():
        status = office.health()
        status.update(
            {
                "status": "ok",
                "adapter": ADAPTER_NAME,
                "service_pid": os.getpid(),
                "uno_module_available": importlib.util.find_spec("uno") is not None,
                "pymupdf_available": importlib.util.find_spec("fitz") is not None,
            }
        )
        return jsonify(status)

    @app.post("/v1/prepare")
    def prepare():
        data = request.get_json(silent=True) or {}
        timeout_ms = data.get("timeout_ms", 15_000)
        try:
            if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
                raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
            result = office.prepare(max(0.1, min(timeout_ms, 120_000) / 1000))
            return jsonify({"status": "ok", "adapter": ADAPTER_NAME, "result": result})
        except AdapterError as error:
            return failure(error)

    def execute(parsed):
        deadline = time.monotonic() + parsed.timeout_ms / 1000
        if not action_lock.acquire(timeout=parsed.timeout_ms / 1000):
            raise AdapterError(
                "TIMEOUT", "timed out waiting for Writer action lock", http_status=504
            )
        try:
            listener_ready = office.listener_ready()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AdapterError(
                    "TIMEOUT", "Writer request deadline expired", http_status=504
                )
            if not listener_ready:
                g.office_lifecycle = {"operation": "ensure_listener", "status": "attempted"}
                try:
                    prepared = office.prepare(min(15.0, remaining))
                except AdapterError:
                    g.office_lifecycle["status"] = "failed"
                    raise
                g.office_lifecycle.update(status="ready", result=prepared)
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                raise AdapterError(
                    "TIMEOUT", "Writer request deadline expired", http_status=504
                )
            # Listener preparation and lock wait share the original budget;
            # the model-selected action, document, arguments and checks do not change.
            parsed = replace(parsed, timeout_ms=remaining_ms)
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
                **({"lifecycle": g.office_lifecycle} if hasattr(g, "office_lifecycle") else {}),
            }
        )

    @app.post("/v1/actions")
    def actions():
        parsed = None
        raw = request.get_json(silent=True)
        raw_id = raw.get("request_id") if isinstance(raw, dict) else None
        try:
            parsed = parse_action_request(raw)
            return success(parsed, execute(parsed))
        except AdapterError as error:
            return failure(error, parsed.request_id if parsed else raw_id)

    @app.post("/v1/verify")
    def verify():
        parsed = None
        raw = dict(request.get_json(silent=True) or {})
        raw_id = raw.get("request_id")
        try:
            raw["action"] = "document.inspect"
            raw.setdefault("params", {})
            parsed = parse_action_request(raw)
            return success(parsed, execute(parsed))
        except AdapterError as error:
            return failure(error, parsed.request_id if parsed else raw_id)

    @app.post("/v1/shutdown")
    def shutdown():
        data = request.get_json(silent=True) or {}
        timeout_ms = data.get("timeout_ms", 10_000)
        try:
            if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
                raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
            return jsonify(
                {
                    "status": "ok",
                    "adapter": ADAPTER_NAME,
                    "result": office.shutdown(
                        max(0.1, min(timeout_ms, 120_000) / 1000)
                    ),
                }
            )
        except AdapterError as error:
            return failure(error)

    return app


def main() -> None:
    host = os.environ.get("WRITER_ADAPTER_HOST", "0.0.0.0")
    port = int(os.environ.get("WRITER_ADAPTER_PORT", "8770"))
    create_app().run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
