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
    lifecycle: LibreOfficeLifecycle | None = None,
    runner: WorkerRunner | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.logger.setLevel(logging.INFO)
    office = lifecycle or LibreOfficeLifecycle()
    worker = runner or WorkerRunner()
    action_lock = threading.Lock()

    def failure(error: AdapterError, request_id: str | None = None):
        payload = {
            "request_id": request_id,
            "status": "error",
            "result": None,
            "verification": None,
            "error": error_payload(error),
            "duration_ms": 0,
            "logs": [],
        }
        if hasattr(g, "office_lifecycle"):
            payload["lifecycle"] = g.office_lifecycle
        return jsonify(payload), error.http_status

    @app.get("/health")
    def health():
        status = office.health()
        status.update(
            {
                "status": "ok",
                "adapter": ADAPTER_NAME,
                "service_pid": os.getpid(),
                "uno_module_available": importlib.util.find_spec("uno") is not None,
            }
        )
        return jsonify(status)

    @app.post("/v1/prepare")
    def prepare():
        started = time.monotonic()
        data = request.get_json(silent=True) or {}
        timeout_ms = data.get("timeout_ms", 15_000)
        try:
            if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
                raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
            result = office.prepare(max(0.1, min(timeout_ms, 120_000) / 1000))
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

    def execute_parsed(parsed):
        deadline = time.monotonic() + parsed.timeout_ms / 1000
        if not action_lock.acquire(timeout=parsed.timeout_ms / 1000):
            raise AdapterError(
                "TIMEOUT", "timed out waiting for the Calc action lock", http_status=504
            )
        try:
            if not office.listener_ready():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AdapterError("TIMEOUT", "Calc request deadline expired", http_status=504)
                g.office_lifecycle = {"operation": "ensure_listener", "status": "attempted"}
                try:
                    prepared = office.prepare(min(15.0, remaining), restart_existing=False)
                except AdapterError:
                    g.office_lifecycle["status"] = "failed"
                    raise
                g.office_lifecycle.update(status="ready", result=prepared)
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    raise AdapterError("TIMEOUT", "Calc request deadline expired", http_status=504)
                # Only the operational time budget changes; the model's action,
                # document, semantic arguments and verification remain intact.
                parsed = replace(parsed, timeout_ms=remaining_ms)
            return worker.run(parsed)
        finally:
            action_lock.release()

    def success(parsed, worker_result):
        return jsonify(
            {
                "request_id": parsed.request_id,
                "status": "ok",
                "result": worker_result.get("result", {}),
                "verification": worker_result.get("verification"),
                "error": None,
                "duration_ms": worker_result.get("duration_ms", 0),
                    "logs": worker_result.get("logs", []),
                    **({"lifecycle": g.office_lifecycle} if hasattr(g, "office_lifecycle") else {}),
            }
        )

    @app.post("/v1/actions")
    def actions():
        parsed = None
        raw_payload = request.get_json(silent=True)
        raw_request_id = (
            raw_payload.get("request_id") if isinstance(raw_payload, dict) else None
        )
        try:
            parsed = parse_action_request(raw_payload)
            worker_result = execute_parsed(parsed)
            return success(parsed, worker_result)
        except AdapterError as error:
            return failure(error, parsed.request_id if parsed else raw_request_id)

    @app.post("/v1/verify")
    def verify():
        parsed = None
        raw_request_id = None
        try:
            data = dict(request.get_json(silent=True) or {})
            raw_request_id = data.get("request_id")
            data["action"] = "workbook.inspect"
            data.setdefault("params", {})
            parsed = parse_action_request(data)
            worker_result = execute_parsed(parsed)
            return success(parsed, worker_result)
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
                    "result": office.shutdown(
                        max(0.1, min(timeout_ms, 120_000) / 1000)
                    ),
                }
            )
        except AdapterError as error:
            return failure(error)

    return app


def main() -> None:
    host = os.environ.get("CALC_ADAPTER_HOST", "0.0.0.0")
    port = int(os.environ.get("CALC_ADAPTER_PORT", "8765"))
    create_app().run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
