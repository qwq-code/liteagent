#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-impress-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-impress-adapter"
unit_dir="${HOME}/.config/systemd/user"

test -f "${payload_dir}/impress_adapter/service.py"
test -f "${payload_dir}/impress_adapter/uno_worker.py"
test -f "${payload_dir}/impress_adapter/deploy/osworld-impress-adapter.service"
/usr/bin/python3 -c 'import flask, uno'

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/impress_adapter"
cp -a "${payload_dir}/impress_adapter" "${install_dir}/impress_adapter"
install -m 0644 "${payload_dir}/impress_adapter/deploy/osworld-impress-adapter.service" "${unit_dir}/osworld-impress-adapter.service"
systemctl --user daemon-reload
systemctl --user enable osworld-impress-adapter.service
systemctl --user restart osworld-impress-adapter.service
