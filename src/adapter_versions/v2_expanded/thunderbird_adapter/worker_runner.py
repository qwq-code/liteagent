from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .errors import AdapterError
from .schema import ActionRequest


class WorkerRunner:
    def __init__(self, module: str = "thunderbird_adapter.worker") -> None:
        self.module = module

    def run(self, request: ActionRequest) -> dict:
        started = time.monotonic()
        env = os.environ.copy()
        package_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = package_root + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        process = subprocess.Popen(
            [sys.executable, "-m", self.module],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(
                json.dumps(request.to_worker_payload()),
                timeout=request.timeout_ms / 1000,
            )
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            raise AdapterError(
                "OPERATION_TIMEOUT",
                f"action exceeded {request.timeout_ms} ms",
                {"stdout": stdout[-4000:], "stderr": stderr[-4000:]},
                504,
            ) from exc
        duration_ms = round((time.monotonic() - started) * 1000)
        try:
            result = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            result = None
        details = {
            "returncode": process.returncode,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
        }
        if process.returncode != 0:
            if isinstance(result, dict) and result.get("error"):
                error = result["error"]
                raise AdapterError(
                    error.get("code", "INTERNAL_ERROR"),
                    error.get("message", "Thunderbird worker failed"),
                    error.get("details", details),
                    int(error.get("http_status", 500)),
                )
            raise AdapterError(
                "INTERNAL_ERROR", "Thunderbird worker failed", details, 500
            )
        if not isinstance(result, dict):
            raise AdapterError(
                "INTERNAL_ERROR",
                "Thunderbird worker returned invalid JSON",
                details,
                500,
            )
        result["duration_ms"] = duration_ms
        if stderr:
            result.setdefault("logs", []).append(
                {"level": "warning", "message": stderr[-4000:]}
            )
        return result
