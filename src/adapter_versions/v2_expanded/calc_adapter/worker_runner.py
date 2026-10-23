from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .errors import AdapterError
from .schema import ActionRequest


class WorkerRunner:
    def __init__(self, module: str = "calc_adapter.uno_worker") -> None:
        self.module = module

    def run(self, request: ActionRequest) -> dict[str, Any]:
        started = time.monotonic()
        env = os.environ.copy()
        package_root = str(Path(__file__).resolve().parents[1])
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            package_root
            if not existing_pythonpath
            else package_root + os.pathsep + existing_pythonpath
        )
        try:
            completed = subprocess.run(
                [sys.executable, "-m", self.module],
                input=json.dumps(request.to_worker_payload()),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=request.timeout_ms / 1000,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "TIMEOUT",
                f"action exceeded {request.timeout_ms} ms",
                {"stdout": exc.stdout, "stderr": exc.stderr},
                504,
            ) from exc

        duration_ms = round((time.monotonic() - started) * 1000)
        try:
            result = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError):
            result = None

        if completed.returncode != 0:
            details: dict[str, Any] = {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
            if isinstance(result, dict) and result.get("error"):
                error = result["error"]
                raise AdapterError(
                    error.get("code", "INTERNAL_ERROR"),
                    error.get("message", "UNO worker failed"),
                    error.get("details", details),
                    int(error.get("http_status", 500)),
                )
            if (
                isinstance(result, dict)
                and "result" in result
                and "verification" in result
            ):
                result.setdefault("logs", []).append(
                    {
                        "level": "warning",
                        "message": (
                            "UNO worker exited after emitting a complete response "
                            f"(return code {completed.returncode})"
                        ),
                    }
                )
            else:
                raise AdapterError("INTERNAL_ERROR", "UNO worker failed", details, 500)

        if not isinstance(result, dict):
            raise AdapterError(
                "INTERNAL_ERROR",
                "UNO worker returned invalid JSON",
                {
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                },
                500,
            )
        result["duration_ms"] = duration_ms
        if completed.stderr:
            result.setdefault("logs", []).append(
                {"level": "warning", "message": completed.stderr[-4000:]}
            )
        return result
