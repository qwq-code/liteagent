"""Install the pinned desktop clipboard utility without guest network access."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import time

from .command import CommandRunner
from .errors import AdapterError


PACKAGE = "xsel_1.2.0+git9bfc13d.20180109-3_amd64.deb"
PACKAGE_SHA256 = "9b4b7758933d2ed9c8d98008abe73e0d264d1c2e80dcfd7692958bb7291002a5"


def ensure_clipboard_backend(package_dir: Path) -> str:
    """Keep either existing backend, or install and check the bundled xsel."""
    for name in ("xsel", "xclip"):
        if shutil.which(name):
            return name
    package = package_dir / PACKAGE
    if hashlib.sha256(package.read_bytes()).hexdigest() != PACKAGE_SHA256:
        raise RuntimeError("Clipboard package checksum mismatch")
    runner = CommandRunner()
    # PackageKit can hold the guest's package lock immediately after boot.
    for service in ("packagekit.service", "packagekit.socket"):
        try:
            runner.sudo(["systemctl", "stop", service], timeout=20)
        except AdapterError:
            pass
    deadline = time.monotonic() + 180
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Offline clipboard installation exceeded 180 seconds")
        try:
            runner.sudo(
                ["env", "DEBIAN_FRONTEND=noninteractive", "dpkg", "-i", str(package)],
                timeout=min(120, remaining),
            )
            break
        except AdapterError as error:
            details = error.details if isinstance(error.details, dict) else {}
            stderr = str(details.get("stderr", "")).casefold()
            if not any(marker in stderr for marker in (
                "is another process using it", "locked by process",
            )):
                raise
            time.sleep(min(3, max(0, deadline - time.monotonic())))
    if not shutil.which("xsel"):
        raise RuntimeError("Clipboard installation completed without an xsel executable")
    return "xsel"


if __name__ == "__main__":
    import sys

    print(ensure_clipboard_backend(Path(sys.argv[1])))
