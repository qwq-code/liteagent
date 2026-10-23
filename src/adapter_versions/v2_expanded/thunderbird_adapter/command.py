from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from .errors import AdapterError


class CommandRunner:
    def run(
        self,
        command: list[str],
        *,
        timeout: float = 30,
        check: bool = True,
        error_code: str = "COMMAND_FAILED",
        error_message: str = "command failed",
    ) -> dict[str, Any]:
        started = time.monotonic()
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
        try:
            result = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "OPERATION_TIMEOUT",
                f"command exceeded {timeout:.1f} seconds",
                {"command": command},
                504,
            ) from exc
        payload = {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
        if check and result.returncode != 0:
            raise AdapterError(error_code, error_message, payload, 422)
        return payload
