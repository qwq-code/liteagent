from __future__ import annotations

import os
import subprocess
import time
from glob import has_magic
from typing import Any

from .errors import AdapterError


def gsettings_failure_guidance(argv: list[str], stderr: str) -> str | None:
    """Explain how to recover from an invalid GSettings schema or key.

    GSettings reports schema/key mistakes only in stderr.  Keep that native
    diagnostic intact, but add the shortest generic next step so a model can
    discover relocatable instances instead of retrying the same bare schema.
    """
    if not argv or argv[0] != "gsettings":
        return None
    lowered = stderr.casefold()
    if not any(
        marker in lowered
        for marker in ("no such key", "no such schema", "is relocatable")
    ):
        return None
    return (
        "Do not retry the unchanged GSettings request. Discover the exact schema "
        "and key first: use gsettings list-schemas for fixed schemas or "
        "gsettings list-relocatable-schemas for per-instance schemas; obtain the "
        "concrete instance path from the owning registry, then run gsettings "
        "list-keys SCHEMA:/instance/path/ and gsettings get/range before setting."
    )


def literal_argument_failure_guidance(
    argv: list[str],
    output: str,
    *,
    redirection_recovery: str | None = None,
) -> str | None:
    mentioned = [argument for argument in argv[1:] if argument and argument in output]
    attached_redirection = any(
        argument.lstrip().startswith(">") and argument.strip() not in {">", ">>"}
        for argument in mentioned
    )
    wildcard = any(has_magic(argument) for argument in mentioned)
    if not attached_redirection and not wildcard:
        return None
    guidance = (
        "Native command output mentions a supplied argument containing shell-like characters. "
        "Direct argv passes each string literally; the selected program receives it "
        "unchanged unless that program itself interprets it. "
    )
    if attached_redirection:
        guidance += (redirection_recovery or (
            "If the leading > was intended to redirect output, omit that entire argument "
            "and supply your output filename as stdout_path instead; for >> also set "
            "append_stdout=true."
        )).rstrip() + " "
    if wildcard:
        guidance += (
            "If the wildcard was intended to match filenames, explicitly select "
            "argv=[\"bash\", \"-c\", <one model-authored script>] for shell expansion, "
            "or pass a pattern to a program that handles it, such as find -name. "
        )
    return guidance.rstrip()


class CommandRunner:
    def __init__(self, sudo_password: str | None = None) -> None:
        self.sudo_password = sudo_password or os.environ.get(
            "OSWORLD_SUDO_PASSWORD", "password"
        )

    @staticmethod
    def environment() -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        env.setdefault(
            "DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus"
        )
        return env

    def run(
        self,
        argv: list[str],
        *,
        timeout: float = 30.0,
        input_text: str | None = None,
        check: bool = True,
        error_code: str = "OPERATION_FAILED",
        error_message: str = "command failed",
        cwd: str | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                input=input_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(0.1, timeout),
                cwd=cwd,
                env=self.environment(),
                check=False,
            )
        except FileNotFoundError as exc:
            missing_cwd = cwd is not None and exc.filename == cwd
            guidance = (
                "The selected working directory was not found. Inspect the directory "
                "and select an existing cwd before retrying."
                if missing_cwd
                else "argv is executed directly without a shell: argv[0] must be one "
                "executable name or path, with each argument in a separate string. "
                "Do not put a complete shell command in argv[0]. For shell syntax, "
                "explicitly select argv=[\"bash\", \"-c\", <one model-authored script>]. "
                "If argv is already separated, verify the executable path and its interpreter."
            )
            raise AdapterError(
                "WORKING_DIRECTORY_NOT_FOUND" if missing_cwd else "EXECUTABLE_NOT_FOUND",
                "command working directory was not found"
                if missing_cwd
                else "command executable or its interpreter was not found",
                {
                    "argv": argv,
                    "executable": argv[0],
                    "cwd": cwd,
                    "errno": exc.errno,
                    "filename": exc.filename,
                    "error": str(exc),
                    "shell_parsing": False,
                    "guidance": guidance,
                },
                422,
            ) from exc
        except subprocess.TimeoutExpired as exc:

            def tail_text(value: str | bytes | None) -> str:
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="replace")
                return (value or "")[-4000:]

            raise AdapterError(
                "OPERATION_TIMEOUT",
                f"command exceeded {timeout:.1f} seconds",
                {
                    "argv": argv,
                    "stdout": tail_text(exc.stdout),
                    "stderr": tail_text(exc.stderr),
                },
                504,
            ) from exc
        result = {
            "argv": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
        if check and completed.returncode != 0:
            guidance = gsettings_failure_guidance(argv, result["stderr"])
            if guidance:
                result["guidance"] = guidance
            raise AdapterError(error_code, error_message, result, 422)
        return result

    def start(
        self,
        argv: list[str],
        *,
        error_code: str = "OPERATION_FAILED",
        error_message: str = "command failed to start",
        cwd: str | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=cwd,
                env=self.environment(),
                start_new_session=True,
            )
        except OSError as exc:
            raise AdapterError(
                error_code,
                error_message,
                {"argv": argv, "error": str(exc)},
                422,
            ) from exc
        return {
            "argv": argv,
            "pid": process.pid,
            "returncode": process.poll(),
            "duration_ms": round((time.monotonic() - started) * 1000),
        }

    def sudo(
        self,
        argv: list[str],
        *,
        timeout: float = 60.0,
        error_code: str = "SUDO_AUTH_FAILED",
        error_message: str = "privileged command failed",
    ) -> dict[str, Any]:
        return self.run(
            ["sudo", "-S", "-p", "", "--", *argv],
            timeout=timeout,
            input_text=self.sudo_password + "\n",
            error_code=error_code,
            error_message=error_message,
        )
