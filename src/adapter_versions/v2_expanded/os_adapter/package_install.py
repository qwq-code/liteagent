"""Bounded, observable offline package installation for disposable guest setup."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from os_adapter.command import CommandRunner
from os_adapter.errors import AdapterError


def _run_command(argv: list[str], timeout: float) -> dict:
    started = time.monotonic()
    process = subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, errors="replace", start_new_session=True,
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive", "LC_ALL": "C"},
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=max(0.1, timeout))
    except subprocess.TimeoutExpired:
        timed_out = True
        # Kill only this command's group, including dpkg's maintainer scripts.
        # Killing sudo alone can leave a package transaction running behind it.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
    return {
        "argv": argv, "returncode": process.returncode, "timed_out": timed_out,
        "stdout": stdout[-8000:], "stderr": stderr[-8000:],
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def _install(packages: list[str], timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    attempts = []
    warnings = []
    for unit in ("packagekit.service", "packagekit.socket"):
        result = _run_command(["systemctl", "stop", unit], min(10, max(0.1, deadline-time.monotonic())))
        if result["returncode"]:
            warnings.append(result)
    # A previous killed dpkg leaves numeric journal fragments. Configure these
    # first; dpkg itself arbitrates its lock, which must never be deleted.
    interrupted = any(p.name.isdigit() for p in Path("/var/lib/dpkg/updates").glob("*"))
    operation = "configure" if interrupted else "install"
    recovered = False
    failure = "installation deadline exhausted"
    while time.monotonic() < deadline:
        argv = ["dpkg", "--configure", "--pending"] if operation == "configure" else ["dpkg", "-i", *packages]
        result = _run_command(argv, deadline-time.monotonic())
        attempts.append(result)
        if result["timed_out"]:
            failure = "package command timed out; its process group was terminated"
            break
        if result["returncode"] == 0:
            if operation == "configure":
                recovered = True
                operation = "install"
                continue
            return {"ok": True, "recovered_interrupted_install": recovered,
                    "attempt_count": len(attempts), "attempts": attempts[-12:], "warnings": warnings}
        stderr = result["stderr"].casefold()
        if any(s in stderr for s in ("is another process using it", "locked by process", "frontend lock was locked")):
            time.sleep(min(3, max(0, deadline-time.monotonic())))
            continue
        if operation == "install" and "dpkg was interrupted" in stderr and not recovered:
            operation = "configure"
            continue
        failure = "package command failed"
        break
    return {"ok": False, "reason": failure, "recovered_interrupted_install": recovered,
            "attempt_count": len(attempts), "attempts": attempts[-12:], "warnings": warnings}


def install_offline_packages(packages: list[Path], *, timeout: float = 600) -> dict:
    if not packages:
        return {"ok": True, "attempts": []}
    if timeout <= 0:
        raise ValueError("package installation timeout must be positive")
    # Run the timeout supervisor with the same privileges as dpkg so it can
    # terminate the complete transaction, not just an unprivileged sudo parent.
    result = CommandRunner().sudo(
        ["env", "PYTHONPATH=" + str(Path(__file__).resolve().parents[1]),
         "/usr/bin/python3", "-m", "os_adapter.package_install", "--worker",
         str(timeout), *[str(p) for p in packages]], timeout=timeout+15,
    )
    try:
        report = json.loads(result["stdout"])
    except (KeyError, ValueError) as exc:
        raise AdapterError("PACKAGE_INSTALL_PROTOCOL", "installer returned invalid diagnostics", result) from exc
    print(json.dumps({"offline_package_install": report}, ensure_ascii=False), flush=True)
    if not report.get("ok"):
        raise AdapterError("PACKAGE_INSTALL_FAILED", "offline package installation failed", report)
    return report


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "--worker" or os.geteuid() != 0:
        raise SystemExit("internal package installer requires root and explicit packages")
    try:
        report = _install(sys.argv[3:], float(sys.argv[2]))
    except Exception as error:
        report = {"ok": False, "reason": type(error).__name__ + ": " + str(error)}
    print(json.dumps(report, ensure_ascii=False), flush=True)
