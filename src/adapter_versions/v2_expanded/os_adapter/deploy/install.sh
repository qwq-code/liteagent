#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-os-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-os-adapter"
unit_dir="${HOME}/.config/systemd/user"
pymupdf_wheel="${payload_dir}/os_adapter/vendor/pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl"

test -f "${payload_dir}/os_adapter/service.py"
test -f "${payload_dir}/os_adapter/actions.py"
test -f "${payload_dir}/os_adapter/vendor/pypdf-6.14.2-py3-none-any.whl"
test -f "${payload_dir}/os_adapter/vendor/typing_extensions-4.15.0-py3-none-any.whl"
test -f "${pymupdf_wheel}"
test -f "${payload_dir}/os_adapter/deploy/osworld-os-adapter.service"
for command in gio gsettings pactl timedatectl gnome-terminal gnome-screenshot wmctrl snap sudo useradd usermod openssl pdftocairo; do
  command -v "${command}"
done
/usr/bin/python3 -c 'import flask'

PYTHONPATH="${payload_dir}" /usr/bin/python3 -m os_adapter.clipboard_dependency \
  "${payload_dir}/os_adapter/vendor/clipboard"

ocr_dir="${payload_dir}/os_adapter/vendor/ocr"
if ! command -v tesseract >/dev/null || ! tesseract --list-langs 2>/dev/null | grep -qx eng; then
  PYTHONPATH="${payload_dir}" /usr/bin/python3 - "${ocr_dir}" <<'PY'
import hashlib
import sys
import time
from pathlib import Path

from os_adapter.command import CommandRunner
from os_adapter.errors import AdapterError

ocr_dir = Path(sys.argv[1])
packages = (
    "liblept5_1.82.0-3build1_amd64.deb",
    "libtesseract4_4.1.1-2.1build1_amd64.deb",
    "tesseract-ocr-eng_4.00-git30-7274cfa-1.1_all.deb",
    "tesseract-ocr-osd_4.00-git30-7274cfa-1.1_all.deb",
    "tesseract-ocr_4.1.1-2.1build1_amd64.deb",
)
entries = [line.split() for line in (ocr_dir / "SHA256SUMS.sha256").read_text().splitlines()]
if len(entries) != len(packages) or any(len(entry) != 2 for entry in entries):
    raise RuntimeError("OCR package manifest is incomplete")
expected = {filename: checksum for checksum, filename in entries}
if set(expected) != set(packages):
    raise RuntimeError("OCR package manifest does not match bundled packages")
for filename in packages:
    actual = hashlib.sha256((ocr_dir / filename).read_bytes()).hexdigest()
    if actual != expected[filename]:
        raise RuntimeError(f"OCR package checksum mismatch: {filename}")

runner = CommandRunner()
# PackageKit may hold the dpkg lock while a fresh guest is settling.
for service in ("packagekit.service", "packagekit.socket"):
    try:
        runner.sudo(["systemctl", "stop", service], timeout=20)
    except AdapterError as error:
        print(error.details, flush=True)
deadline = time.monotonic() + 180
while True:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("offline OCR package installation exceeded 180 seconds")
    try:
        result = runner.sudo(
            ["env", "DEBIAN_FRONTEND=noninteractive", "dpkg", "-i", *(str(ocr_dir / name) for name in packages)],
            timeout=min(120, remaining),
        )
        break
    except AdapterError as error:
        details = error.details if isinstance(error.details, dict) else {}
        stderr = str(details.get("stderr", "")).casefold()
        if not any(marker in stderr for marker in ("is another process using it", "locked by process")):
            raise
        time.sleep(min(3, max(0, deadline - time.monotonic())))
print(result["stdout"], end="")
print(result["stderr"], end="")
PY
  command -v tesseract
  tesseract --list-langs 2>/dev/null | grep -qx eng
fi

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/os_adapter"
rm -rf "${install_dir}/pypdf" "${install_dir}"/pypdf-*.dist-info
rm -rf "${install_dir}/typing_extensions.py" "${install_dir}"/typing_extensions-*.dist-info
cp -a "${payload_dir}/os_adapter" "${install_dir}/os_adapter"
/usr/bin/python3 -m pip install \
  --disable-pip-version-check \
  --no-index \
  --no-deps \
  --upgrade \
  --target "${install_dir}" \
  "${payload_dir}/os_adapter/vendor/pypdf-6.14.2-py3-none-any.whl" \
  "${payload_dir}/os_adapter/vendor/typing_extensions-4.15.0-py3-none-any.whl" \
  "${pymupdf_wheel}"
install -m 0644 \
  "${payload_dir}/os_adapter/deploy/osworld-os-adapter.service" \
  "${unit_dir}/osworld-os-adapter.service"

systemctl --user daemon-reload
systemctl --user enable osworld-os-adapter.service
systemctl --user restart osworld-os-adapter.service
