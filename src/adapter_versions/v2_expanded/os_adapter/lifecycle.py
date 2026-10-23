from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .command import CommandRunner
from .errors import AdapterError


TERMINAL_TITLE = "OSWorld OS Adapter Terminal"
REQUIRED_COMMANDS = (
    "gio",
    "gsettings",
    "pactl",
    "timedatectl",
    "gnome-terminal",
    "gnome-screenshot",
    "wmctrl",
    "xprop",
    "snap",
    "sudo",
    "useradd",
    "usermod",
    "openssl",
    "xdg-mime",
)


class OSLifecycle:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def windows(self) -> list[str]:
        completed = subprocess.run(
            ["wmctrl", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=self.runner.environment(),
            check=False,
        )
        return completed.stdout.splitlines()

    def health(self) -> dict[str, Any]:
        commands = {name: shutil.which(name) is not None for name in REQUIRED_COMMANDS}
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        return {
            "commands": commands,
            "all_commands_available": all(commands.values()),
            "clipboard_available": any(shutil.which(name) for name in ("xsel", "xclip")),
            "display": os.environ.get("DISPLAY", ":0"),
            "dbus_socket": str(runtime / "bus"),
            "dbus_available": (runtime / "bus").exists(),
            "sudo_password_configured": bool(self.runner.sudo_password),
            "terminal_windows": [
                line
                for line in self.windows()
                if TERMINAL_TITLE.lower() in line.lower()
            ],
        }

    def prepare(self, _timeout_seconds: float = 10.0) -> dict[str, Any]:
        status = self.health()
        if not status["all_commands_available"]:
            missing = [
                name for name, available in status["commands"].items() if not available
            ]
            raise AdapterError(
                "OS_UNAVAILABLE",
                "required guest commands are unavailable",
                missing,
                503,
            )
        if not status["dbus_available"]:
            raise AdapterError(
                "OS_UNAVAILABLE", "desktop DBus session is unavailable", status, 503
            )
        if not status["clipboard_available"]:
            raise AdapterError(
                "CLIPBOARD_UNAVAILABLE", "required clipboard backend is unavailable",
                {"required_commands": ["xsel", "xclip"]}, 503,
            )
        return {"ready": True, **status}

    def shutdown(self, _timeout_seconds: float = 10.0) -> dict[str, Any]:
        closed = 0
        for line in self.windows():
            if TERMINAL_TITLE.lower() not in line.lower():
                continue
            window_id = line.split(maxsplit=1)[0]
            subprocess.run(
                ["wmctrl", "-ic", window_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self.runner.environment(),
                check=False,
            )
            closed += 1
        return {"stopped": True, "closed_terminal_windows": closed}
