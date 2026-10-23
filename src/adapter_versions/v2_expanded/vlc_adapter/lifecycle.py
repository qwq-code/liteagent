from __future__ import annotations

import importlib.util
import os
import shutil
import time
from pathlib import Path
from typing import Any

from .command import CommandRunner
from .config import VLC_CONFIG_PATH, read_config
from .errors import AdapterError


class VlcLifecycle:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def health(self) -> dict[str, Any]:
        commands = {
            name: shutil.which(name)
            for name in (
                "vlc",
                "ffmpeg",
                "ffprobe",
                "wmctrl",
                "gsettings",
                "xrandr",
                "python3",
            )
        }
        config = read_config(VLC_CONFIG_PATH)
        return {
            "commands": commands,
            "all_commands_available": all(commands.values()),
            "dbus_available": Path(f"/run/user/{os.getuid()}/bus").exists(),
            "display": os.environ.get("DISPLAY", ":0"),
            "config_path": str(VLC_CONFIG_PATH),
            "config_writable": VLC_CONFIG_PATH.parent.exists()
            and os.access(VLC_CONFIG_PATH.parent, os.W_OK),
            "flask_available": importlib.util.find_spec("flask") is not None,
            "opencv_available": importlib.util.find_spec("cv2") is not None,
            "http_configured": "http" in config.get("extraintf", "").split(":"),
            "http_password_configured": bool(config.get("http-password")),
        }

    def prepare(self, _timeout_seconds: float = 15.0) -> dict[str, Any]:
        VLC_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        health = self.health()
        required = (
            health["all_commands_available"],
            health["dbus_available"],
            health["config_writable"],
            health["flask_available"],
            health["opencv_available"],
            health["http_configured"],
            health["http_password_configured"],
        )
        if not all(required):
            raise AdapterError(
                "VLC_NOT_READY",
                "VLC Adapter prerequisites are unavailable",
                health,
                503,
            )
        return {"ready": True, "health": health}

    def shutdown(self, timeout_seconds: float = 10.0) -> dict[str, Any]:
        before = self.runner.run(["pgrep", "-x", "vlc"], check=False, timeout=5)[
            "stdout"
        ].split()
        self.runner.run(["pkill", "-TERM", "-x", "vlc"], check=False, timeout=5)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = self.runner.run(["pgrep", "-x", "vlc"], check=False, timeout=5)[
                "stdout"
            ]
            if not remaining.strip():
                return {"stopped": True, "process_ids": before}
            time.sleep(0.25)
        raise AdapterError(
            "OPERATION_TIMEOUT",
            "VLC processes did not stop before timeout",
            {"process_ids": before},
            504,
        )
