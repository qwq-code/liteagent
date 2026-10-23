#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-calc-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-calc-adapter"
unit_dir="${HOME}/.config/systemd/user"

test -f "${payload_dir}/calc_adapter/service.py"
test -f "${payload_dir}/calc_adapter/uno_worker.py"
test -f "${payload_dir}/calc_adapter/deploy/osworld-calc-adapter.service"
/usr/bin/python3 -c 'import flask, uno'

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/calc_adapter"
cp -a "${payload_dir}/calc_adapter" "${install_dir}/calc_adapter"
install -m 0644 \
  "${payload_dir}/calc_adapter/deploy/osworld-calc-adapter.service" \
  "${unit_dir}/osworld-calc-adapter.service"

systemctl --user daemon-reload
systemctl --user enable osworld-calc-adapter.service
systemctl --user restart osworld-calc-adapter.service
