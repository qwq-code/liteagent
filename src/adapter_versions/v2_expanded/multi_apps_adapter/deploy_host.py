from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from scripts.strict_deployment import STRICT_DENIED_FILENAMES, filter_source_files


REPO_ROOT = Path(__file__).resolve().parents[1]
REMOTE_PAYLOAD = "/tmp/osworld-multi-apps-adapter-payload"
REMOTE_INSTALL = "/home/user/.local/share/osworld-multi-apps-adapter/multi_apps_adapter"


def execute(
    control_url: str, command: list[str], timeout: float = 300
) -> dict[str, Any]:
    response = requests.post(
        control_url.rstrip("/") + "/execute",
        json={"command": command, "shell": False},
        timeout=timeout + 10,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success" or payload.get("returncode") != 0:
        raise RuntimeError(payload)
    return payload


def package_paths(root: Path) -> list[Path]:
    package = root / "multi_apps_adapter"
    paths = [
        path
        for path in package.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    denied = sorted(
        path.relative_to(package).as_posix()
        for path in paths
        if path.name.casefold() in STRICT_DENIED_FILENAMES
    )
    if denied:
        raise RuntimeError(f"Multi-Apps package contains forbidden manifests: {denied}")
    return filter_source_files(package, paths, strict_generic=True)


def upload(control_url: str, source: Path, destination: str) -> None:
    with source.open("rb") as stream:
        response = requests.post(
            control_url.rstrip("/") + "/setup/upload",
            data={"file_path": destination},
            files={"file_data": (source.name, stream)},
            timeout=180,
        )
    response.raise_for_status()


def wait_health(
    adapter_url: str,
    timeout: float = 90,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            response = requests.get(adapter_url.rstrip("/") + "/health", timeout=5)
            response.raise_for_status()
            payload = response.json()
            if (
                payload.get("status") == "ok"
                and payload.get("mode") == "strict_generic"
            ):
                return payload
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"Multi-Apps Adapter health timeout: {last_error}")


def deploy(
    control_url: str,
    adapter_url: str,
    root: Path,
) -> dict[str, Any]:
    execute(control_url, ["rm", "-rf", REMOTE_PAYLOAD])
    paths = package_paths(root)
    for path in paths:
        relative = path.relative_to(root)
        upload(control_url, path, f"{REMOTE_PAYLOAD}/{relative}")
    execute(control_url, ["rm", "-rf", f"{REMOTE_INSTALL}/goldens"])
    execute(control_url, ["rm", "-f", f"{REMOTE_INSTALL}/task_manifest.json"])
    execute(
        control_url,
        [
            "bash",
            f"{REMOTE_PAYLOAD}/multi_apps_adapter/deploy/install.sh",
            REMOTE_PAYLOAD,
        ],
    )
    return {
        "uploaded_files": len(paths),
        "mode": "strict_generic",
        "health": wait_health(adapter_url),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["deploy", "health", "uninstall", "logs"])
    parser.add_argument(
        "--control-url",
        default=os.environ.get("OSWORLD_CONTROL_URL", "http://127.0.0.1:32946"),
    )
    parser.add_argument(
        "--adapter-url",
        default=os.environ.get("MULTI_APPS_ADAPTER_URL", "http://127.0.0.1:32959"),
    )
    args = parser.parse_args()
    if args.command == "deploy":
        result = deploy(
            args.control_url,
            args.adapter_url,
            REPO_ROOT,
        )
    elif args.command == "health":
        result = wait_health(args.adapter_url, 10)
    elif args.command == "uninstall":
        result = execute(
            args.control_url,
            ["bash", f"{REMOTE_PAYLOAD}/multi_apps_adapter/deploy/uninstall.sh"],
        )
    else:
        result = execute(
            args.control_url,
            ["bash", f"{REMOTE_PAYLOAD}/multi_apps_adapter/deploy/logs.sh", "200"],
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
