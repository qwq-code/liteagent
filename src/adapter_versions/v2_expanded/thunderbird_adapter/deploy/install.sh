#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-thunderbird-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-thunderbird-adapter"
unit_dir="${HOME}/.config/systemd/user"

test -f "${payload_dir}/thunderbird_adapter/service.py"
test -f "${payload_dir}/thunderbird_adapter/deploy/osworld-thunderbird-adapter.service"
for command in thunderbird wmctrl python3 flock; do
  command -v "${command}"
done
/usr/bin/python3 -c 'import flask, pyatspi, pyautogui'

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/thunderbird_adapter"
cp -a "${payload_dir}/thunderbird_adapter" "${install_dir}/thunderbird_adapter"
install -m 0644 \
  "${payload_dir}/thunderbird_adapter/deploy/osworld-thunderbird-adapter.service" \
  "${unit_dir}/osworld-thunderbird-adapter.service"

systemctl --user daemon-reload
systemctl --user enable osworld-thunderbird-adapter.service
systemctl --user restart osworld-thunderbird-adapter.service
