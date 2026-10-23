#!/usr/bin/env bash
set -euo pipefail
payload_dir="${1:-/tmp/osworld-multi-apps-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-multi-apps-adapter"
unit_dir="${HOME}/.config/systemd/user"
test -f "${payload_dir}/multi_apps_adapter/service.py"
test -f "${payload_dir}/multi_apps_adapter/actions.py"
test -f "${payload_dir}/multi_apps_adapter/schema.py"

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/multi_apps_adapter"
cp -a "${payload_dir}/multi_apps_adapter" "${install_dir}/multi_apps_adapter"
install -m 0644 "${payload_dir}/multi_apps_adapter/deploy/osworld-multi-apps-adapter.service" "${unit_dir}/osworld-multi-apps-adapter.service"
systemctl --user daemon-reload
systemctl --user enable osworld-multi-apps-adapter.service
systemctl --user restart osworld-multi-apps-adapter.service
