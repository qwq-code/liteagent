from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Any

from .errors import AdapterError


GIMP_WINDOW_TOKENS = ("gimp", "image manipulation program")


class GimpLifecycle:
    def __init__(self) -> None:
        self._lock = Lock()
        self.display = os.environ.get("DISPLAY", ":0")
        runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        self.log_path = runtime_dir / "osworld-gimp-adapter-gui.log"

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["DISPLAY"] = self.display
        env.setdefault(
            "DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus"
        )
        return env

    def gui_running(self) -> bool:
        completed = subprocess.run(
            ["ps", "-u", str(os.getuid()), "-o", "stat=,comm="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return False
        for line in completed.stdout.splitlines():
            fields = line.split(None, 1)
            if len(fields) != 2:
                continue
            state, process_name = fields
            if process_name in {"gimp", "gimp-2.10"} and not state.startswith("Z"):
                return True
        return False

    def all_windows(self) -> list[str]:
        completed = subprocess.run(
            ["wmctrl", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=self._env(),
            check=False,
        )
        return completed.stdout.splitlines()

    def windows(self) -> list[str]:
        return [
            line
            for line in self.all_windows()
            if any(token in line.lower() for token in GIMP_WINDOW_TOKENS)
        ]

    def activate(self, title: str = "GIMP") -> bool:
        candidates = [title]
        if title == "GIMP":
            candidates.append("GNU Image Manipulation Program")
        for candidate in candidates:
            completed = subprocess.run(
                ["wmctrl", "-a", candidate],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._env(),
                check=False,
            )
            if completed.returncode == 0:
                return True
        return False

    def discard_recovery_dialog(self) -> None:
        self.activate("Image Recovery")
        completed = subprocess.run(
            [
                "python3",
                "-c",
                "import pyautogui; pyautogui.press('left'); pyautogui.press('enter')",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            env=self._env(),
            check=False,
        )
        if completed.returncode != 0:
            raise AdapterError(
                "GUI_ACTION_FAILED",
                "failed to discard GIMP crash recovery state",
                completed.stderr[-2000:],
                422,
            )

    @staticmethod
    def document_window_ready(windows: list[str], path: str | None) -> bool:
        if not windows:
            return False
        if path is None:
            return True
        basename = Path(path).name.lower()
        return any(basename in window.lower() for window in windows)

    def shutdown(self, timeout_seconds: float = 10.0) -> dict[str, Any]:
        with self._lock:
            if not self.gui_running():
                return {"stopped": True, "already_stopped": True}
            errors: list[str] = []
            for process_name in ("gimp", "gimp-2.10"):
                completed = subprocess.run(
                    ["pkill", "-TERM", "-u", str(os.getuid()), "-x", process_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if completed.returncode not in {0, 1}:
                    errors.append(completed.stderr[-2000:])
            if errors:
                raise AdapterError(
                    "GIMP_UNAVAILABLE", "failed to stop GIMP", errors, 503
                )
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if not self.gui_running():
                    return {"stopped": True, "already_stopped": False}
                time.sleep(0.1)
            for process_name in ("gimp", "gimp-2.10"):
                subprocess.run(
                    ["pkill", "-KILL", "-u", str(os.getuid()), "-x", process_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            time.sleep(0.2)
            if self.gui_running():
                raise AdapterError("GIMP_TIMEOUT", "GIMP did not stop", http_status=504)
            return {"stopped": True, "forced": True}

    def prepare(
        self, timeout_seconds: float = 25.0, path: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            if not shutil.which("gimp") or not shutil.which("gimp-console"):
                raise AdapterError(
                    "GIMP_UNAVAILABLE", "GIMP commands are unavailable", http_status=503
                )
            if self.gui_running():
                if path:
                    raise AdapterError(
                        "GIMP_BUSY",
                        "GIMP must be stopped before opening a deterministic result document",
                        http_status=409,
                    )
                self.activate()
                return {
                    "ready": True,
                    "already_running": True,
                    "windows": self.windows(),
                }
            command = ["gimp", "--no-splash"]
            if path:
                command.append(path)
            log_file = self.log_path.open("ab")
            try:
                subprocess.Popen(
                    command,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=self._env(),
                    start_new_session=True,
                )
            except OSError as exc:
                raise AdapterError(
                    "GIMP_UNAVAILABLE", "failed to start GIMP", str(exc), 503
                ) from exc
            finally:
                log_file.close()
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                all_windows = self.all_windows()
                if any("image recovery" in window.lower() for window in all_windows):
                    self.discard_recovery_dialog()
                    time.sleep(0.4)
                    continue
                windows = [
                    window
                    for window in all_windows
                    if any(token in window.lower() for token in GIMP_WINDOW_TOKENS)
                ]
                if self.gui_running() and self.document_window_ready(windows, path):
                    self.activate(Path(path).name if path else "GIMP")
                    return {
                        "ready": True,
                        "already_running": False,
                        "path": path,
                        "windows": windows,
                    }
                time.sleep(0.2)
            raise AdapterError(
                "GIMP_TIMEOUT",
                "GIMP GUI did not become ready",
                {"path": path, "log_path": str(self.log_path)},
                504,
            )

    def reopen(self, path: str, timeout_seconds: float = 25.0) -> dict[str, Any]:
        self.shutdown(min(10.0, timeout_seconds))
        return self.prepare(timeout_seconds, path)

    def health(self) -> dict[str, Any]:
        return {
            "gimp_available": shutil.which("gimp") is not None,
            "gimp_console_available": shutil.which("gimp-console") is not None,
            "gimp_gui_running": self.gui_running(),
            "display": self.display,
            "windows": self.windows(),
            "log_path": str(self.log_path),
        }
