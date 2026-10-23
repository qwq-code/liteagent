from __future__ import annotations

import importlib.util
import os
import shutil
import time
from pathlib import Path
from typing import Any

from .actions import KEYBINDINGS_PATH, SETTINGS_PATH
from .command import CommandRunner
from .errors import AdapterError
from .verifier import extension_state


FORBIDDEN_EXTENSION_ID = "osworld.array-variables"


class VscodeLifecycle:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def health(self) -> dict[str, Any]:
        commands = {
            name: shutil.which(name)
            for name in ("code", "wmctrl", "python3", "zip", "unzip")
        }
        try:
            forbidden_extension = extension_state(self.runner, FORBIDDEN_EXTENSION_ID)
        except AdapterError as exc:
            forbidden_extension = {
                "extension_id": FORBIDDEN_EXTENSION_ID,
                "installed": None,
                "error": str(exc),
            }
        forbidden_extension_absent = (
            forbidden_extension.get("installed") is False
            and "error" not in forbidden_extension
        )
        return {
            "commands": commands,
            "all_commands_available": all(commands.values()),
            "dbus_available": Path(f"/run/user/{os.getuid()}/bus").exists(),
            "display": os.environ.get("DISPLAY", ":0"),
            "settings_path": str(SETTINGS_PATH),
            "keybindings_path": str(KEYBINDINGS_PATH),
            "config_writable": SETTINGS_PATH.parent.exists()
            and os.access(SETTINGS_PATH.parent, os.W_OK),
            "flask_available": importlib.util.find_spec("flask") is not None,
            "pyatspi_available": importlib.util.find_spec("pyatspi") is not None,
            "pyautogui_available": importlib.util.find_spec("pyautogui") is not None,
            "forbidden_extension": forbidden_extension,
            "forbidden_extension_absent": forbidden_extension_absent,
        }

    def prepare(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        Path("/home/user/.vscode/extensions").mkdir(parents=True, exist_ok=True)
        self.runner.run(
            ["code", "--uninstall-extension", FORBIDDEN_EXTENSION_ID],
            check=False,
            timeout=max(0.1, min(timeout_seconds, 60.0)),
        )
        health = self.health()
        required = (
            health["all_commands_available"],
            health["dbus_available"],
            health["config_writable"],
            health["flask_available"],
            health["pyatspi_available"],
            health["pyautogui_available"],
            health["forbidden_extension_absent"],
        )
        if not all(required):
            raise AdapterError(
                "VSCODE_NOT_READY",
                "VS Code Adapter prerequisites are unavailable",
                health,
                503,
            )
        return {"ready": True, "health": health}

    def shutdown(self, timeout_seconds: float = 10.0) -> dict[str, Any]:
        windows = self.runner.run(["wmctrl", "-lx"], check=False, timeout=5)[
            "stdout"
        ].splitlines()
        ids = [line.split()[0] for line in windows if "code.Code" in line]
        for window_id in ids:
            self.runner.run(["wmctrl", "-ic", window_id], check=False, timeout=5)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = self.runner.run(["wmctrl", "-lx"], check=False, timeout=5)[
                "stdout"
            ]
            if "code.Code" not in remaining:
                return {"stopped": True, "closed_windows": ids}
            time.sleep(0.25)
        raise AdapterError(
            "OPERATION_TIMEOUT",
            "VS Code windows did not close before timeout",
            {"window_ids": ids},
            504,
        )
