#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-chrome-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-chrome-adapter"
unit_dir="${HOME}/.config/systemd/user"

test -f "${payload_dir}/chrome_adapter/service.py"
test -f "${payload_dir}/chrome_adapter/worker.py"
test -f "${payload_dir}/chrome_adapter/deploy/osworld-chrome-adapter.service"
/usr/bin/python3 -c 'import flask'
/usr/bin/python3 -m pip install --user --disable-pip-version-check \
  --no-index --find-links "${payload_dir}/chrome_adapter/vendor" 'pychrome==0.2.4'

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/chrome_adapter"
cp -a "${payload_dir}/chrome_adapter" "${install_dir}/chrome_adapter"
install -m 0644 \
  "${payload_dir}/chrome_adapter/deploy/osworld-chrome-adapter.service" \
  "${unit_dir}/osworld-chrome-adapter.service"

systemctl --user daemon-reload
systemctl --user enable osworld-chrome-adapter.service
systemctl --user restart osworld-chrome-adapter.service

