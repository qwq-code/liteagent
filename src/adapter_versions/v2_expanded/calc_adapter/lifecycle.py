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
        self.log_path = runtime_dir / "osworld-calc-adapter-soffice.log"
        self._process: subprocess.Popen[bytes] | None = None

    def listener_ready(self, timeout: float = 0.15) -> bool:
        if self._process is not None and self._process.poll() is not None:
            self._process = None
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout):
                return True
        except OSError:
            return False

    def _live_office_processes(self) -> list[str]:
        completed = subprocess.run(
            ["ps", "-u", str(os.getuid()), "-o", "stat=,comm="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        live = []
        for line in completed.stdout.splitlines():
            fields = line.strip().split(None, 1)
            if len(fields) != 2:
                continue
            state, name = fields
            if not state.startswith("Z") and name in {
                "soffice.bin",
                "soffice",
                "oosplash",
            }:
                live.append(name)
        return live

    @staticmethod
    def _remove_profile_locks() -> None:
        profile = Path.home() / ".config/libreoffice/4"
        for path in (profile / ".lock", profile / "user/.lock"):
            path.unlink(missing_ok=True)

    def _stop_stale_office(self, timeout_seconds: float) -> bool:
        live_before = self._live_office_processes()
        for name in ("soffice.bin", "soffice", "oosplash"):
            subprocess.run(
                ["pkill", "-TERM", "-u", str(os.getuid()), "-x", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        deadline = time.monotonic() + max(0.1, timeout_seconds)
        while time.monotonic() < deadline:
            if not self._live_office_processes() and not self.listener_ready():
                break
            time.sleep(0.1)
        if self._live_office_processes() or self.listener_ready():
            for name in ("soffice.bin", "soffice", "oosplash"):
                subprocess.run(
                    ["pkill", "-KILL", "-u", str(os.getuid()), "-x", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            kill_deadline = time.monotonic() + 2
            while time.monotonic() < kill_deadline:
                if not self._live_office_processes() and not self.listener_ready():
                    break
                time.sleep(0.1)
        if self._process is not None:
            try:
                self._process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
            if self._process.poll() is not None:
                self._process = None
        self._remove_profile_locks()
        return bool(live_before)

    def prepare(
        self, timeout_seconds: float = 15.0, *, restart_existing: bool = True
    ) -> dict[str, Any]:
        with self._lock:
            if self.listener_ready():
                return {"ready": True, "already_running": True, "port": self.port}
            deadline = time.monotonic() + timeout_seconds
            last_exit_code = None
            cleaned_stale_processes = False
            attached_to_running = False
            for attempt in range(2):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if restart_existing:
                    cleaned_stale_processes = (
                        self._stop_stale_office(min(5, remaining))
                        or cleaned_stale_processes
                    )
                else:
                    if attempt and self.listener_ready():
                        return {
                            "ready": True,
                            "already_running": True,
                            "port": self.port,
                        }
                    live_processes = self._live_office_processes()
                    attached_to_running = bool(live_processes)
                    # soffice forwards --accept to an existing instance by IPC.
                    # Its live profile and open documents must remain intact.
                    if not live_processes:
                        self._remove_profile_locks()
                display = os.environ.get("DISPLAY", ":0")
                env = os.environ.copy()
                env["DISPLAY"] = display
                env.setdefault(
                    "DBUS_SESSION_BUS_ADDRESS",
                    f"unix:path=/run/user/{os.getuid()}/bus",
                )
                log_file = self.log_path.open("ab")
                try:
                    self._process = subprocess.Popen(
                        [
                            "soffice",
                            f"--accept=socket,host={self.host},port={self.port};urp;",
                            "--norestore",
                            "--nologo",
                            "--nodefault",
                            "--nofirststartwizard",
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

                process = self._process
                attempt_deadline = (
                    deadline if attempt else min(deadline, time.monotonic() + 30)
                )
                while time.monotonic() < attempt_deadline:
                    if self.listener_ready():
                        return {
                            "ready": True,
                            "already_running": attached_to_running,
                            "attached_to_running": attached_to_running,
                            "port": self.port,
                            "attempt": attempt + 1,
                            "cleaned_stale_processes": cleaned_stale_processes,
                        }
                    if process.poll() is not None:
                        last_exit_code = process.returncode
                        self._process = None
                        if restart_existing or last_exit_code != 0:
                            break
                        # Exit zero can mean IPC delivery; wait for the listener.
                    time.sleep(0.1)
            raise AdapterError(
                "LIBREOFFICE_NOT_READY",
                "LibreOffice UNO listener did not become ready",
                {
                    "port": self.port,
                    "log_path": str(self.log_path),
                    "last_exit_code": last_exit_code,
                    "live_processes": self._live_office_processes(),
                },
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
            already_stopped = (
                not self.listener_ready() and not self._live_office_processes()
            )
            self._stop_stale_office(timeout_seconds)
            if self.listener_ready() or self._live_office_processes():
                raise AdapterError(
                    "TIMEOUT",
                    "LibreOffice did not stop before the shutdown timeout",
                    http_status=504,
                )
            return {"stopped": True, "already_stopped": already_stopped}
