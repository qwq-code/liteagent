#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-gimp-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-gimp-adapter"
dependency_dir="${install_dir}/python-deps"
unit_dir="${HOME}/.config/systemd/user"

test -f "${payload_dir}/gimp_adapter/service.py"
test -f "${payload_dir}/gimp_adapter/scriptfu.py"
test -f "${payload_dir}/gimp_adapter/deploy/osworld-gimp-adapter.service"
command -v gimp
command -v gimp-console
command -v wmctrl
/usr/bin/python3 -c 'import flask, PIL, pyautogui'

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/gimp_adapter"
cp -a "${payload_dir}/gimp_adapter" "${install_dir}/gimp_adapter"
rm -rf "${dependency_dir}"
install -m 0644 \
  "${payload_dir}/gimp_adapter/deploy/osworld-gimp-adapter.service" \
  "${unit_dir}/osworld-gimp-adapter.service"

systemctl --user daemon-reload
systemctl --user enable osworld-gimp-adapter.service
systemctl --user restart osworld-gimp-adapter.service
