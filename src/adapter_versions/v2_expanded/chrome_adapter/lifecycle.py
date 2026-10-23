from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from threading import Lock
from typing import Any

from .errors import AdapterError


OSWORLD_CHROME_STDERR_LOG = Path("/tmp/osworld_chrome_stderr.log")


class ChromeLifecycle:
    def __init__(self, chrome_port: int = 1337, forward_port: int = 9222) -> None:
        self.chrome_port = chrome_port
        self.forward_port = forward_port
        self._lock = Lock()
        runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        # OSWorld validates the live CDP browser GUID against the first marker in
        # this exact file after profile actions restart Chrome.
        self.chrome_log = OSWORLD_CHROME_STDERR_LOG
        self.socat_log = runtime_dir / "osworld-chrome-adapter-socat.log"
        self.state_dir = Path.home() / ".config" / "osworld-chrome-adapter"
        self.launch_args_path = self.state_dir / "launch-args.json"

    @staticmethod
    def _port_ready(port: int, timeout: float = 0.15) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                return True
        except OSError:
            return False

    def _version(self, port: int | None = None) -> dict[str, Any] | None:
        target_port = port or self.chrome_port
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{target_port}/json/version", timeout=1
            ) as response:
                return json.load(response)
        except Exception:
            return None

    @staticmethod
    def _chrome_pids() -> list[int]:
        result = subprocess.run(
            ["pgrep", "-f", "/opt/google/chrome/chrome"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        pids: list[int] = []
        for value in result.stdout.split():
            try:
                pid = int(value)
                state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2]
            except (OSError, ValueError, IndexError):
                continue
            if state != "Z":
                pids.append(pid)
        return pids

    def _stop_chrome_unlocked(self, timeout_seconds: float) -> dict[str, Any]:
        was_running = self._version() is not None or bool(self._chrome_pids())
        if not was_running:
            return {"stopped": True, "already_stopped": True, "forced": False}

        subprocess.run(
            ["pkill", "-TERM", "-f", "/opt/google/chrome/chrome"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        deadline = time.monotonic() + timeout_seconds
        term_deadline = time.monotonic() + timeout_seconds * 0.8
        while time.monotonic() < term_deadline:
            if self._version() is None and not self._chrome_pids():
                return {"stopped": True, "already_stopped": False, "forced": False}
            time.sleep(0.1)

        subprocess.run(
            ["pkill", "-KILL", "-f", "/opt/google/chrome/chrome"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        while time.monotonic() < deadline:
            if self._version() is None and not self._chrome_pids():
                return {"stopped": True, "already_stopped": False, "forced": True}
            time.sleep(0.05)
        raise AdapterError(
            "TIMEOUT", "Chrome did not stop before the timeout", http_status=504
        )

    def _extra_args(self) -> list[str]:
        try:
            data = json.loads(self.launch_args_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        args = data.get("args", []) if isinstance(data, dict) else []
        fixed_flags = {
            "--ignore-certificate-errors",
            "--allow-insecure-localhost",
            "--disable-quic",
            "--host-resolver-rules=MAP google.com 127.0.0.1, MAP www.google.com 127.0.0.1",
            "--host-resolver-rules=MAP github.com 127.0.0.1, MAP docs.python.org 127.0.0.1",
            "--host-resolver-rules=MAP apple.com 127.0.0.1, MAP www.apple.com 127.0.0.1, MAP scholar.google.com 127.0.0.1, MAP amazon.com 127.0.0.1, MAP www.amazon.com 127.0.0.1",
        }
        return [
            arg
            for arg in args
            if isinstance(arg, str)
            and (arg.startswith("--load-extension=") or arg in fixed_flags)
        ]

    def _start_chrome(self, timeout_seconds: float) -> None:
        if self._version():
            return
        if self._chrome_pids():
            self._stop_chrome_unlocked(min(timeout_seconds, 10.0))
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        env.setdefault(
            "DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus"
        )
        self.chrome_log.parent.mkdir(parents=True, exist_ok=True)
        log = self.chrome_log.open("wb")
        try:
            subprocess.Popen(
                [
                    "google-chrome",
                    f"--remote-debugging-port={self.chrome_port}",
                    *self._extra_args(),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            raise AdapterError(
                "CHROME_NOT_READY", "failed to start Chrome", str(exc), 503
            ) from exc
        finally:
            log.close()

    def _start_forward(self) -> None:
        if self._port_ready(self.forward_port):
            return
        log = self.socat_log.open("ab")
        try:
            subprocess.Popen(
                [
                    "socat",
                    f"tcp-listen:{self.forward_port},fork,reuseaddr",
                    f"tcp:127.0.0.1:{self.chrome_port}",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            raise AdapterError(
                "CDP_NOT_READY", "failed to start the CDP forward", str(exc), 503
            ) from exc
        finally:
            log.close()

    def prepare(self, timeout_seconds: float = 20.0) -> dict[str, Any]:
        with self._lock:
            already_running = self._version() is not None
            started = time.monotonic()
            self._start_chrome(timeout_seconds)
            self._start_forward()
            deadline = started + timeout_seconds
            while time.monotonic() < deadline:
                version = self._version()
                forwarded = self._version(self.forward_port)
                if version and forwarded:
                    return {
                        "ready": True,
                        "already_running": already_running,
                        "chrome_port": self.chrome_port,
                        "forward_port": self.forward_port,
                        "browser": version.get("Browser"),
                        "protocol_version": version.get("Protocol-Version"),
                    }
                time.sleep(0.1)
        raise AdapterError(
            "CDP_NOT_READY",
            "Chrome CDP did not become ready",
            {"chrome_port": self.chrome_port, "forward_port": self.forward_port},
            503,
        )

    def shutdown(self, timeout_seconds: float = 10.0) -> dict[str, Any]:
        with self._lock:
            return self._stop_chrome_unlocked(timeout_seconds)

    def restart(self, timeout_seconds: float = 20.0) -> dict[str, Any]:
        self.shutdown(min(timeout_seconds, 10.0))
        return self.prepare(timeout_seconds)

    def health(self) -> dict[str, Any]:
        version = self._version()
        return {
            "chrome_ready": version is not None,
            "forward_ready": self._version(self.forward_port) is not None,
            "chrome_port": self.chrome_port,
            "forward_port": self.forward_port,
            "browser": version.get("Browser") if version else None,
            "protocol_version": version.get("Protocol-Version") if version else None,
            "profile_path": str(Path.home() / ".config" / "google-chrome" / "Default"),
            "display": os.environ.get("DISPLAY", ":0"),
            "chrome_log": str(self.chrome_log),
            "socat_log": str(self.socat_log),
        }
