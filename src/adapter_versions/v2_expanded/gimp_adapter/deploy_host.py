#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from scripts.strict_deployment import filter_source_files


REMOTE_PAYLOAD = "/tmp/osworld-gimp-adapter-payload"


def execute(
    control_url: str, command: list[str], timeout: float = 180
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
    package = repo_root / "gimp_adapter"
    paths = (
        path
        for path in package.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.name != "deploy_host.py"
        and path.suffix in {".py", ".sh", ".service", ".png"}
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
                and payload.get("gimp_available")
                and payload.get("gimp_console_available")
                and payload.get("pillow_available")
            ):
                return payload
        except Exception as exc:
            error = exc
        time.sleep(0.25)
    raise TimeoutError(f"GIMP Adapter health check failed: {error}")


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
    execute(
        control_url,
        ["bash", f"{REMOTE_PAYLOAD}/gimp_adapter/deploy/install.sh", REMOTE_PAYLOAD],
    )
    return {"uploaded_files": len(paths), "health": wait_health(adapter_url)}


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["deploy", "health", "uninstall", "logs"])
    parser.add_argument(
        "--control-url",
        default=os.environ.get("OSWORLD_CONTROL_URL", "http://127.0.0.1:32837"),
    )
    parser.add_argument(
        "--adapter-url",
        default=os.environ.get("GIMP_ADAPTER_URL", "http://127.0.0.1:32844"),
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
            ["bash", f"{REMOTE_PAYLOAD}/gimp_adapter/deploy/uninstall.sh"],
        )
    else:
        result = execute(
            args.control_url,
            ["bash", f"{REMOTE_PAYLOAD}/gimp_adapter/deploy/logs.sh", "200"],
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
