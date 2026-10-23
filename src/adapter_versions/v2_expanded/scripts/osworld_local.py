#!/usr/bin/env python3
"""Start and stop a localhost-only OSWorld Docker/KVM instance."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path


DEFAULT_NAME = "osworld-local"
DEFAULT_IMAGE = "happysixd/osworld-docker:latest"
PORTS = {
    "control": "5000/tcp",
    "vnc": "8006/tcp",
    "vnc_raw": "5900/tcp",
    "chrome": "9222/tcp",
    "vlc": "8080/tcp",
    "calc_adapter": "8765/tcp",
    "impress_adapter": "8766/tcp",
    "chrome_adapter": "8767/tcp",
    "gimp_adapter": "8768/tcp",
    "os_adapter": "8769/tcp",
    "writer_adapter": "8770/tcp",
    "vscode_adapter": "8771/tcp",
    "vlc_adapter": "8772/tcp",
    "thunderbird_adapter": "8773/tcp",
    "multi_apps_adapter": "8774/tcp",
}
FIXED_HOST_PORTS = {"vnc": 32769, "multi_apps_adapter": 32959}


def run(
    *args: str,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def inspect(name: str) -> dict | None:
    result = run("docker", "inspect", name, check=False)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)[0]


def mapped_port(name: str, container_port: str) -> int:
    result = run("docker", "port", name, container_port)
    endpoint = result.stdout.strip().splitlines()[0]
    return int(endpoint.rsplit(":", 1)[1])


def endpoints(name: str) -> dict[str, str]:
    ports = {key: mapped_port(name, port) for key, port in PORTS.items()}
    return {
        "control": f"http://127.0.0.1:{ports['control']}",
        "vnc": (
            f"http://127.0.0.1:{ports['vnc']}/"
            "?resize=scale&quality=4&compression=0&"
            "reconnect=true&autoconnect=true"
        ),
        "vnc_raw": f"127.0.0.1::{ports['vnc_raw']}",
        "chrome": f"http://127.0.0.1:{ports['chrome']}",
        "vlc": f"http://127.0.0.1:{ports['vlc']}",
        "calc_adapter": f"http://127.0.0.1:{ports['calc_adapter']}",
        "impress_adapter": f"http://127.0.0.1:{ports['impress_adapter']}",
        "chrome_adapter": f"http://127.0.0.1:{ports['chrome_adapter']}",
        "gimp_adapter": f"http://127.0.0.1:{ports['gimp_adapter']}",
        "os_adapter": f"http://127.0.0.1:{ports['os_adapter']}",
        "writer_adapter": f"http://127.0.0.1:{ports['writer_adapter']}",
        "vscode_adapter": f"http://127.0.0.1:{ports['vscode_adapter']}",
        "vlc_adapter": f"http://127.0.0.1:{ports['vlc_adapter']}",
        "thunderbird_adapter": f"http://127.0.0.1:{ports['thunderbird_adapter']}",
        "multi_apps_adapter": f"http://127.0.0.1:{ports['multi_apps_adapter']}",
    }


def wait_until_ready(control_url: str, timeout: float = 300) -> None:
    deadline = time.monotonic() + timeout
    screenshot_url = control_url + "/screenshot"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(screenshot_url, timeout=10) as response:
                if response.status == 200 and response.read(8) == b"\x89PNG\r\n\x1a\n":
                    return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"OSWorld did not become ready within {timeout:.0f} seconds")


def validate_vnc_password(password: str | None) -> None:
    if password is None:
        return
    if not 1 <= len(password) <= 8:
        raise ValueError("QEMU VNC passwords must contain 1 to 8 characters")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(character not in allowed for character in password):
        raise ValueError(
            "QEMU VNC passwords may contain only ASCII letters, digits, '.', '_', or '-'"
        )


def set_vnc_password(name: str, password: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    monitor_script = "exec 3<>/dev/tcp/127.0.0.1/7100; cat >&3; sleep 0.3"
    monitor_input = f"change vnc password {password}\n"
    while time.monotonic() < deadline:
        result = run(
            "docker",
            "exec",
            "-i",
            name,
            "bash",
            "-lc",
            monitor_script,
            check=False,
            input_text=monitor_input,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError("QEMU monitor did not accept the VNC password")


def vnc_auth_enabled(current: dict) -> bool:
    return "VNC_PASSWORD_ENABLED=Y" in current["Config"].get("Env", [])


def start(
    name: str,
    image: str,
    qcow2: Path,
    display_script: Path,
    vnc_password: str | None,
) -> None:
    validate_vnc_password(vnc_password)
    current = inspect(name)
    if current and current["State"]["Running"]:
        if bool(vnc_password) != vnc_auth_enabled(current):
            raise RuntimeError(
                "VNC authentication mode differs from the running container; "
                "stop it before starting with the new mode"
            )
        if vnc_password:
            set_vnc_password(name, vnc_password)
        print(json.dumps(endpoints(name), indent=2))
        return
    if current:
        run("docker", "rm", name)

    if not qcow2.is_file():
        raise FileNotFoundError(f"OSWorld qcow2 image not found: {qcow2}")
    if not display_script.is_file():
        raise FileNotFoundError(f"QEMU display script not found: {display_script}")
    if not Path("/dev/kvm").exists():
        raise RuntimeError("/dev/kvm is not available")

    command = [
        "docker",
        "run",
        "--detach",
        "--name",
        name,
        "--cap-add",
        "NET_ADMIN",
        "--device",
        "/dev/kvm",
        "--env",
        "DISK_SIZE=32G",
        "--env",
        "RAM_SIZE=4G",
        "--env",
        "CPU_CORES=4",
        "--volume",
        f"{qcow2.resolve()}:/System.qcow2:ro",
        "--volume",
        f"{display_script.resolve()}:/run/display.sh:ro",
    ]
    if vnc_password:
        command.extend(["--env", "VNC_PASSWORD_ENABLED=Y"])
    for key, port in PORTS.items():
        host_port = FIXED_HOST_PORTS.get(key, "")
        command.extend(["--publish", f"127.0.0.1:{host_port}:{port.split('/')[0]}"])
    command.append(image)

    run(*command)
    try:
        urls = endpoints(name)
        wait_until_ready(urls["control"])
        if vnc_password:
            set_vnc_password(name, vnc_password)
    except Exception:
        run("docker", "stop", name, check=False)
        run("docker", "rm", name, check=False)
        raise

    print(json.dumps(urls, indent=2))


def stop(name: str) -> None:
    if not inspect(name):
        print(f"{name} is not running")
        return
    run("docker", "stop", name)
    run("docker", "rm", name)
    print(f"stopped {name}")


def status(name: str) -> None:
    current = inspect(name)
    if not current:
        print(json.dumps({"name": name, "running": False}, indent=2))
        return
    result = {"name": name, "running": current["State"]["Running"]}
    if result["running"]:
        result["endpoints"] = endpoints(name)
        result["vnc_auth_enabled"] = vnc_auth_enabled(current)
    print(json.dumps(result, indent=2))


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project_root = repo_root.parent if repo_root.name == "baseline" else repo_root
    default_qcow2 = (
        project_root / "third_party" / "OSWorld" / "docker_vm_data" / "Ubuntu.qcow2"
    )
    default_display_script = repo_root / "scripts" / "osworld_qemu_display.sh"

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "status", "stop"])
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--qcow2", type=Path, default=default_qcow2)
    parser.add_argument("--display-script", type=Path, default=default_display_script)
    parser.add_argument(
        "--vnc-password",
        default=os.environ.get("OSWORLD_VNC_PASSWORD"),
        help="Enable VNC authentication (QEMU permits at most 8 ASCII characters)",
    )
    args = parser.parse_args()

    if args.command == "start":
        start(
            args.name,
            args.image,
            args.qcow2,
            args.display_script,
            args.vnc_password,
        )
    elif args.command == "stop":
        stop(args.name)
    else:
        status(args.name)


if __name__ == "__main__":
    main()
