#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-writer-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-writer-adapter"
unit_dir="${HOME}/.config/systemd/user"
pymupdf_wheel="${payload_dir}/writer_adapter/vendor/pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl"

test -f "${payload_dir}/writer_adapter/service.py"
test -f "${payload_dir}/writer_adapter/uno_worker.py"
test -f "${payload_dir}/writer_adapter/deploy/osworld-writer-adapter.service"
test -f "${pymupdf_wheel}"

# DOCX PDF export enables normalization by default. Ship its dependency
# offline so fresh guests do not depend on external package mirrors.
/usr/bin/python3 -c 'import flask, uno'

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/writer_adapter"
cp -a "${payload_dir}/writer_adapter" "${install_dir}/writer_adapter"
/usr/bin/python3 -m pip install \
  --disable-pip-version-check \
  --no-index \
  --no-deps \
  --upgrade \
  --target "${install_dir}" \
  "${pymupdf_wheel}"
install -m 0644 "${payload_dir}/writer_adapter/deploy/osworld-writer-adapter.service" "${unit_dir}/osworld-writer-adapter.service"
systemctl --user daemon-reload
systemctl --user enable osworld-writer-adapter.service
systemctl --user restart osworld-writer-adapter.service
