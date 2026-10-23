from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Any

from .errors import AdapterError


class LibreOfficeLifecycle:
    def __init__(self, host: str = "127.0.0.1", port: int = 2002) -> None:
        self.host = host
        self.port = port
        self._lock = Lock()
        runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        self.log_path = runtime_dir / "osworld-writer-adapter-soffice.log"

    def listener_ready(self, timeout: float = 0.15) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout):
                return True
        except OSError:
            return False

    def prepare(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        with self._lock:
            if self.listener_ready():
                return {"ready": True, "already_running": True, "port": self.port}
            env = os.environ.copy()
            env.setdefault("DISPLAY", ":0")
            env.setdefault(
                "DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus"
            )
            log_file = self.log_path.open("ab")
            try:
                subprocess.Popen(
                    [
                        "soffice",
                        f"--accept=socket,host={self.host},port={self.port};urp;",
                        "--norestore",
                        "--nologo",
                        "--nodefault",
                    ],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
            except OSError as exc:
                raise AdapterError(
                    "LIBREOFFICE_NOT_READY",
                    "failed to start LibreOffice",
                    str(exc),
                    503,
                ) from exc
            finally:
                log_file.close()
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if self.listener_ready():
                    return {"ready": True, "already_running": False, "port": self.port}
                time.sleep(0.1)
            raise AdapterError(
                "LIBREOFFICE_NOT_READY",
                "LibreOffice UNO listener did not become ready",
                {"port": self.port, "log_path": str(self.log_path)},
                503,
            )

    def health(self) -> dict[str, Any]:
        return {
            "listener_ready": self.listener_ready(),
            "uno_host": self.host,
            "uno_port": self.port,
            "display": os.environ.get("DISPLAY", ":0"),
            "log_path": str(self.log_path),
        }

    def shutdown(self, timeout_seconds: float = 10.0) -> dict[str, Any]:
        with self._lock:
            if not self.listener_ready():
                return {"stopped": True, "already_stopped": True}
            completed = subprocess.run(
                ["pkill", "-TERM", "-u", str(os.getuid()), "-x", "soffice.bin"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if completed.returncode not in (0, 1):
                raise AdapterError(
                    "LIBREOFFICE_NOT_READY",
                    "failed to stop LibreOffice",
                    completed.stderr[-2000:],
                    503,
                )
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if not self.listener_ready():
                    return {"stopped": True, "already_stopped": False}
                time.sleep(0.1)
            raise AdapterError(
                "TIMEOUT", "LibreOffice did not stop before timeout", http_status=504
            )
