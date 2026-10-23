#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from scripts.strict_deployment import filter_source_files


REMOTE_PAYLOAD = "/tmp/osworld-os-adapter-payload"


def execute(
    control_url: str, command: list[str], timeout: float = 900
) -> dict[str, Any]:
    response = requests.post(
        f"{control_url.rstrip('/')}/execute",
        json={"command": command, "shell": False},
        timeout=timeout + 5,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("status") != "success" or result.get("returncode") != 0:
        raise RuntimeError(json.dumps(result, indent=2))
    return result


def upload(control_url: str, source: Path, destination: str) -> None:
    with source.open("rb") as file_data:
        response = requests.post(
            f"{control_url.rstrip('/')}/setup/upload",
            data={"file_path": destination},
            files={"file_data": (source.name, file_data)},
            timeout=120,
        )
    response.raise_for_status()


def source_files(repo_root: Path, *, strict_generic: bool = True) -> list[Path]:
    package = repo_root / "os_adapter"
    paths = (
        path
        for path in package.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.name != "deploy_host.py"
        and path.suffix in {".py", ".sh", ".service", ".md", ".whl", ".deb", ".sha256"}
    )
    return filter_source_files(package, paths, strict_generic=strict_generic)


def wait_health(adapter_url: str, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = requests.get(f"{adapter_url.rstrip('/')}/health", timeout=3)
            response.raise_for_status()
            payload = response.json()
            if (
                payload.get("status") == "ok"
                and payload.get("all_commands_available")
                and payload.get("clipboard_available")
                and payload.get("dbus_available")
                and payload.get("flask_available")
                and payload.get("pypdf_available")
                and payload.get("pdftocairo_available")
            ):
                return payload
        except Exception as exc:
            error = exc
        time.sleep(0.25)
    raise TimeoutError(f"OS Adapter health check failed: {error}")


INSTALL_WORKER = r'''
import json, os, subprocess, sys
from pathlib import Path
directory = Path(sys.argv[1])
with (directory / 'install.log').open('w') as log:
    try:
        result = subprocess.run(sys.argv[2:], stdout=log, stderr=subprocess.STDOUT, timeout=900)
        status = {'returncode': result.returncode}
    except Exception as error:
        status = {'returncode': -1, 'error': type(error).__name__ + ': ' + str(error)}
temporary = directory / 'status.tmp'
temporary.write_text(json.dumps(status))
os.replace(temporary, directory / 'status.json')
'''


def install_payload(control_url: str, command: list[str], timeout: float = 930) -> None:
    """Poll a detached install so the guest HTTP server's 120s limit cannot kill it.

    All files are unique to this attempt. Retries happen only after a reported
    failure; a still-running install is never re-launched by this function.
    """
    directory = f"/tmp/osworld-os-install-{uuid.uuid4().hex}"
    launch = (
        "import pathlib, subprocess, sys; "
        "p=pathlib.Path(sys.argv[1]); p.mkdir(); "
        "f=(p/'worker.log').open('w'); "
        "subprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1], *sys.argv[3:]], "
        "stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)"
    )
    execute(control_url, ["/usr/bin/python3", "-c", launch, directory, INSTALL_WORKER, *command], timeout=30)
    poll = (
        "import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); s=p/'status.json'; "
        "v=json.loads(s.read_text()) if s.exists() else {'running': True}; "
        "v.update(log=(p/'install.log').read_text()[-6000:]) if s.exists() and (p/'install.log').exists() else None; "
        "print(json.dumps(v))"
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = execute(control_url, ["/usr/bin/python3", "-c", poll, directory], timeout=30)
        status = json.loads(result["output"])
        if not status.get("running"):
            if status.get("returncode") != 0:
                raise RuntimeError(f"OS Adapter install failed: {status}")
            return
        time.sleep(2)
    raise TimeoutError(f"OS Adapter install status unavailable after {timeout}s: {directory}")


def deploy(
    control_url: str, adapter_url: str, repo_root: Path, *, strict_generic: bool = True
) -> dict[str, Any]:
    execute(control_url, ["rm", "-rf", REMOTE_PAYLOAD])
    paths = source_files(repo_root, strict_generic=strict_generic)
    for path in paths:
        upload(
            control_url,
            path,
            f"{REMOTE_PAYLOAD}/{path.relative_to(repo_root).as_posix()}",
        )
    pymupdf_wheel = (
        repo_root
        / "writer_adapter/vendor/pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl"
    )
    upload(
        control_url,
        pymupdf_wheel,
        f"{REMOTE_PAYLOAD}/os_adapter/vendor/{pymupdf_wheel.name}",
    )
    install_payload(
        control_url,
        ["bash", f"{REMOTE_PAYLOAD}/os_adapter/deploy/install.sh", REMOTE_PAYLOAD],
    )
    return {"uploaded_files": len(paths) + 1, "health": wait_health(adapter_url)}


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["deploy", "health", "uninstall", "logs"])
    parser.add_argument(
        "--control-url",
        default=os.environ.get("OSWORLD_CONTROL_URL", "http://127.0.0.1:32852"),
    )
    parser.add_argument(
        "--adapter-url",
        default=os.environ.get("OS_ADAPTER_URL", "http://127.0.0.1:32860"),
    )
    args = parser.parse_args()
    if args.command == "deploy":
        result = deploy(
            args.control_url,
            args.adapter_url,
            repo_root,
        )
    elif args.command == "health":
        result = wait_health(args.adapter_url, timeout=5)
    elif args.command == "uninstall":
        result = execute(
            args.control_url,
            ["bash", f"{REMOTE_PAYLOAD}/os_adapter/deploy/uninstall.sh"],
        )
    else:
        result = execute(
            args.control_url,
            ["bash", f"{REMOTE_PAYLOAD}/os_adapter/deploy/logs.sh", "200"],
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
