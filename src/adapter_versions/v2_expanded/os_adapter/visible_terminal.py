"""Run one finite model-selected command and leave its real output visible."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import tempfile
import time
from typing import Any

from .command import CommandRunner, literal_argument_failure_guidance
from .errors import AdapterError
from .lifecycle import OSLifecycle, TERMINAL_TITLE
from .verifier import TERMINAL_OUTPUT_TIMEOUT_SECONDS, terminal_output


def _record_shell_history(argv: list[str]) -> dict[str, Any]:
    history_path = Path(
        os.environ.get("HISTFILE", str(Path.home() / ".bash_history"))
    ).expanduser()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = shlex.join(argv)
    with history_path.open("a", encoding="utf-8") as history:
        history.write(entry + "\n")
    return {"recorded": True, "path": str(history_path), "entry": entry}


def _expand_user_path_args(argv: list[str]) -> list[str]:
    """Expand standalone ``~`` path arguments while preserving shell scripts."""
    if len(argv) >= 3 and argv[0] in {"bash", "sh", "zsh"} and argv[1] == "-c":
        return list(argv)
    return [str(Path(arg).expanduser()) if arg == "~" or arg.startswith("~/") else arg for arg in argv]


def run_visible_terminal_command(
    runner: CommandRunner,
    lifecycle: OSLifecycle,
    params: dict[str, Any],
    *,
    cwd: Path,
    timeout: float,
) -> dict[str, Any]:
    """Execute exact argv in a terminal, await it, and verify its visible marker."""
    started = time.monotonic()
    deadline = started + max(0.1, timeout)
    argv = _expand_user_path_args(list(params["argv"]))
    output_handle, output_name = tempfile.mkstemp(
        prefix="osworld-terminal-output-", suffix=".txt"
    )
    status_handle, status_name = tempfile.mkstemp(
        prefix="osworld-terminal-output-", suffix=".status"
    )
    os.close(output_handle)
    os.close(status_handle)
    output_path = Path(output_name)
    status_path = Path(status_name)
    output_path.unlink(missing_ok=True)
    status_path.unlink(missing_ok=True)
    title = f"{TERMINAL_TITLE} Output {os.getpid()}-{time.monotonic_ns()}"
    displayed_command = shlex.join(argv)
    script = (
        "display_command=$1; output_file=$2; status_file=$3; shift 3; "
        "printf '$ %s\\n' \"$display_command\"; "
        'set -o pipefail; "$@" 2>&1 | tee "$output_file"; '
        "status=${PIPESTATUS[0]}; "
        "printf '\\n[command exited with status %s]\\n' \"$status\"; "
        'printf \'%s\\n\' "$status" > "$status_file"; '
        "exec bash --noprofile --norc"
    )
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AdapterError(
                "OPERATION_TIMEOUT",
                "the visible terminal deadline expired before command launch",
                {"argv": argv, "cwd": str(cwd)},
                504,
            )
        launch = runner.run(
            [
                "gnome-terminal",
                f"--title={title}",
                f"--working-directory={cwd}",
                "--",
                "bash",
                "--noprofile",
                "--norc",
                "-c",
                script,
                "osworld-terminal-output",
                displayed_command,
                str(output_path),
                str(status_path),
                *argv,
            ],
            timeout=min(15.0, remaining),
            error_code="TERMINAL_UNAVAILABLE",
            error_message="failed to launch the visible command terminal",
        )
        windows: list[str] = []
        returncode: int | None = None
        observed: str | None = None
        completion_marker: str | None = None
        overview_dismissal_attempted = False
        while time.monotonic() < deadline:
            windows = [
                line
                for line in lifecycle.windows()
                if title.casefold() in line.casefold()
            ]
            if windows:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if not overview_dismissal_attempted:
                    # EWMH activation alone does not leave GNOME Activities overview.
                    overview_dismissal_attempted = True
                    try:
                        runner.run(
                            [
                                "gdbus", "call", "--session", "--dest", "org.gnome.Shell",
                                "--object-path", "/org/gnome/Shell", "--method",
                                "org.freedesktop.DBus.Properties.Set", "org.gnome.Shell",
                                "OverviewActive", "<false>",
                            ],
                            check=False,
                            timeout=min(5.0, remaining),
                        )
                    except (AdapterError, OSError):
                        # Keep the ordinary focus/read-back path on other desktops.
                        pass
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                runner.run(
                    ["wmctrl", "-a", title], check=False, timeout=min(5.0, remaining)
                )
            if status_path.is_file():
                try:
                    returncode = int(status_path.read_text(encoding="utf-8").strip())
                except (OSError, ValueError):
                    returncode = None
            if returncode is not None:
                completion_marker = f"[command exited with status {returncode}]"
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                observed = terminal_output(
                    timeout=min(TERMINAL_OUTPUT_TIMEOUT_SECONDS, remaining)
                )
                if windows and observed is not None and completion_marker in observed:
                    break
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.1, remaining))
        if not windows:
            raise AdapterError(
                "TERMINAL_UNAVAILABLE",
                "the launched terminal window did not become observable",
                {"argv": argv, "cwd": str(cwd)},
                422,
            )
        if returncode is None:
            raise AdapterError(
                "OPERATION_TIMEOUT",
                "the visible terminal command did not finish before the timeout",
                {"argv": argv, "cwd": str(cwd), "timeout_seconds": timeout},
                504,
            )
        combined_output = (
            output_path.read_text(encoding="utf-8", errors="replace")
            if output_path.is_file()
            else ""
        )
        if observed is None or completion_marker not in observed:
            raise AdapterError(
                "TERMINAL_UNAVAILABLE",
                "the completed command marker was not observable in the terminal",
                {
                    "argv": argv,
                    "cwd": str(cwd),
                    "completion_marker": completion_marker,
                    "terminal_output": observed,
                    "command_completed": True,
                    "returncode": returncode,
                    "combined_output": combined_output[-8000:],
                    "output_truncated": len(combined_output) > 8000,
                },
                422,
            )
        expected_returncodes = list(params.get("expected_returncodes", [0]))
        result: dict[str, Any] = {
            "argv": argv,
            "displayed_command": displayed_command,
            "cwd": str(cwd),
            "cwd_source": params["cwd_source"],
            "returncode": returncode,
            "expected_returncodes": expected_returncodes,
            "stdout": combined_output[-8000:],
            "stderr": "",
            "combined_output": combined_output[-8000:],
            "output_truncated": len(combined_output) > 8000,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "launch_duration_ms": launch["duration_ms"],
            "completion_marker": completion_marker,
            "terminal_output": observed,
            "terminal": {
                "title": title,
                "windows": windows,
                "command_completed": True,
                "output_visible": True,
            },
            "provenance": params["provenance"],
            "verified": True,
        }
        if params["provenance"] == "shell_history":
            result["shell_history"] = _record_shell_history(argv)
        if returncode not in expected_returncodes:
            guidance = literal_argument_failure_guidance(
                argv,
                result["combined_output"],
                redirection_recovery=(
                    "If the leading > was intended to redirect output, explicitly select "
                    "argv=[\"bash\", \"-c\", <one model-authored script>] with the "
                    "redirection inside that script. For visible output only, omit the "
                    "redirection argument; terminal.show_output already displays command output."
                ),
            )
            if guidance:
                result["guidance"] = guidance
            raise AdapterError(
                "COMMAND_FAILED",
                "command returned an unexpected status",
                result,
                422,
            )
        return result
    finally:
        output_path.unlink(missing_ok=True)
        status_path.unlink(missing_ok=True)


__all__ = ["run_visible_terminal_command"]
