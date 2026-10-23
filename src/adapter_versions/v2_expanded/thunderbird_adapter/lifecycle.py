from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

from .actions import ThunderbirdActions
from .errors import AdapterError


class ThunderbirdLifecycle:
    def __init__(self, actions: ThunderbirdActions | None = None) -> None:
        self.actions = actions or ThunderbirdActions()

    def health(self) -> dict[str, Any]:
        commands = {
            name: shutil.which(name) for name in ("thunderbird", "wmctrl", "python3")
        }
        modules = {
            name: importlib.util.find_spec(name) is not None
            for name in ("flask", "pyatspi", "pyautogui")
        }
        root = Path.home() / ".thunderbird"
        return {
            "commands": commands,
            "all_commands_available": all(commands.values()),
            "modules": modules,
            "all_modules_available": all(modules.values()),
            "profile_root": str(root),
            "profile_root_writable": root.exists() and os.access(root, os.W_OK),
            "display": os.environ.get("DISPLAY"),
            "dbus_session": bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")),
        }

    def prepare(self, _timeout_seconds: float = 15) -> dict[str, Any]:
        health = self.health()
        if not all(
            (
                health["all_commands_available"],
                health["all_modules_available"],
                health["profile_root_writable"],
                health["display"],
                health["dbus_session"],
            )
        ):
            raise AdapterError(
                "THUNDERBIRD_NOT_READY",
                "Thunderbird Adapter prerequisites are unavailable",
                health,
                503,
            )
        return {"ready": True, "health": health}

    def shutdown(self, timeout_seconds: float = 10) -> dict[str, Any]:
        return self.actions.stop_thunderbird(timeout_seconds)
