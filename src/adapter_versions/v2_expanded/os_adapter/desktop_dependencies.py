"""Prepare clipboard and OCR dependencies in one verified offline transaction."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

from .clipboard_dependency import PACKAGE, PACKAGE_SHA256
from .package_install import install_offline_packages

OCR_PACKAGES = (
    "liblept5_1.82.0-3build1_amd64.deb",
    "libtesseract4_4.1.1-2.1build1_amd64.deb",
    "tesseract-ocr-eng_4.00-git30-7274cfa-1.1_all.deb",
    "tesseract-ocr-osd_4.00-git30-7274cfa-1.1_all.deb",
    "tesseract-ocr_4.1.1-2.1build1_amd64.deb",
)


def ocr_ready() -> bool:
    if not shutil.which("tesseract"):
        return False
    result = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10)
    return result.returncode == 0 and "eng" in result.stdout.splitlines()


def needs_package_recovery() -> bool:
    if any(p.name.isdigit() for p in Path("/var/lib/dpkg/updates").glob("*")):
        return True
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${db:Status-Status}\\n", "xsel", "liblept5",
         "libtesseract4", "tesseract-ocr", "tesseract-ocr-eng", "tesseract-ocr-osd"],
        capture_output=True, text=True, timeout=10,
    )
    return any(line.strip() in {"half-installed", "unpacked", "half-configured", "triggers-awaited", "triggers-pending"}
               for line in result.stdout.splitlines())


def ensure_desktop_dependencies(vendor: Path) -> None:
    packages = []
    recover = needs_package_recovery()
    if recover or not (shutil.which("xsel") or shutil.which("xclip")):
        clipboard = vendor / "clipboard" / PACKAGE
        if hashlib.sha256(clipboard.read_bytes()).hexdigest() != PACKAGE_SHA256:
            raise RuntimeError("Clipboard package checksum mismatch")
        packages.append(clipboard)
    if recover or not ocr_ready():
        directory = vendor / "ocr"
        entries = [line.split() for line in (directory / "SHA256SUMS.sha256").read_text().splitlines()]
        if len(entries) != len(OCR_PACKAGES) or any(len(e) != 2 for e in entries):
            raise RuntimeError("OCR package manifest is incomplete")
        expected = {name: checksum for checksum, name in entries}
        if set(expected) != set(OCR_PACKAGES):
            raise RuntimeError("OCR package manifest does not match bundled packages")
        for name in OCR_PACKAGES:
            package = directory / name
            if hashlib.sha256(package.read_bytes()).hexdigest() != expected[name]:
                raise RuntimeError(f"OCR package checksum mismatch: {name}")
            packages.append(package)
    install_offline_packages(packages)
    if not (shutil.which("xsel") or shutil.which("xclip")) or not ocr_ready() or needs_package_recovery():
        raise RuntimeError("Installed desktop dependencies failed executable/language checks")


if __name__ == "__main__":
    ensure_desktop_dependencies(Path(sys.argv[1]))
