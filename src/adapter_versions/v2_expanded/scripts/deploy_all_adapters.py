#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

from osworld_local import endpoints, inspect


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = [
    ("calc_adapter", "calc_adapter"),
    ("impress_adapter", "impress_adapter"),
    ("chrome_adapter", "chrome_adapter"),
    ("gimp_adapter", "gimp_adapter"),
    ("os_adapter", "os_adapter"),
    ("writer_adapter", "writer_adapter"),
    ("vscode_adapter", "vscode_adapter"),
    ("vlc_adapter", "vlc_adapter"),
    ("thunderbird_adapter", "thunderbird_adapter"),
    ("multi_apps_adapter", "multi_apps_adapter"),
]


def deploy_adapter(
    module: str,
    control_url: str,
    adapter_url: str,
    retries: int = 3,
) -> None:
    command = [
        sys.executable,
        "-m",
        f"{module}.deploy_host",
        "deploy",
        "--control-url",
        control_url,
        "--adapter-url",
        adapter_url,
    ]
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, retries + 1):
        try:
            subprocess.run(command, cwd=REPO_ROOT, check=True)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            try:
                response = requests.get(adapter_url.rstrip("/") + "/health", timeout=10)
                if response.ok and response.json().get("status") == "ok":
                    return
            except (requests.RequestException, ValueError):
                pass
            if attempt < retries:
                delay = min(5 * attempt, 15)
                print(
                    f"Adapter deploy failed for {module} "
                    f"(attempt {attempt}/{retries}); retrying in {delay}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay)
    assert last_error is not None
    raise last_error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="osworld-local")
    args = parser.parse_args()

    current = inspect(args.name)
    if not current or not current["State"]["Running"]:
        raise RuntimeError(f"OSWorld container is not running: {args.name}")
    urls = endpoints(args.name)
    deployed = []
    for module, endpoint_key in ADAPTERS:
        deploy_adapter(
            module,
            urls["control"],
            urls[endpoint_key],
        )
        response = requests.get(urls[endpoint_key] + "/health", timeout=15)
        response.raise_for_status()
        health = response.json()
        if health.get("status") != "ok":
            raise RuntimeError({"adapter": module, "health": health})
        deployed.append(
            {
                "adapter": module,
                "url": urls[endpoint_key],
                "health": health,
            }
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "container": args.name,
                "control_url": urls["control"],
                "deployed": deployed,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
