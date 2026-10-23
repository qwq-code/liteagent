from __future__ import annotations

import os
import subprocess
from typing import Any

from .errors import AdapterError


class CommandRunner:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = os.environ.copy()
        if env:
            self.env.update(env)

    def run(
        self,
        argv: list[str],
        *,
        timeout: float = 45,
        check: bool = True,
        error_code: str = "OPERATION_FAILED",
        error_message: str = "command failed",
    ) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=max(0.1, timeout),
                env=self.env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout
            stderr = exc.stderr
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise AdapterError(
                "OPERATION_TIMEOUT",
                f"command exceeded {timeout:.1f} seconds",
                {"argv": argv, "stdout": stdout, "stderr": stderr},
                504,
            ) from exc
        result = {
            "argv": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        if check and completed.returncode != 0:
            raise AdapterError(error_code, error_message, result, 422)
        return result
