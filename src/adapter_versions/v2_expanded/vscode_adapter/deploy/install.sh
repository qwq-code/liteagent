#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-vscode-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-vscode-adapter"
unit_dir="${HOME}/.config/systemd/user"

test -f "${payload_dir}/vscode_adapter/service.py"
test ! -e "${payload_dir}/vscode_adapter/extension"
test -f "${payload_dir}/vscode_adapter/deploy/osworld-vscode-adapter.service"
for command in code wmctrl python3 zip unzip flock; do
  command -v "${command}"
done
/usr/bin/python3 -c 'import flask, pyatspi, pyautogui'

mkdir -p "${install_dir}" "${unit_dir}" "${HOME}/.config/Code/User" "${HOME}/.vscode/extensions"
rm -rf "${install_dir}/vscode_adapter"
cp -a "${payload_dir}/vscode_adapter" "${install_dir}/vscode_adapter"

code --uninstall-extension osworld.array-variables >/dev/null 2>&1 || true
if code --list-extensions | grep -Fxi osworld.array-variables >/dev/null; then
  echo "forbidden VS Code extension remains installed: osworld.array-variables" >&2
  exit 1
fi

install -m 0644 \
  "${payload_dir}/vscode_adapter/deploy/osworld-vscode-adapter.service" \
  "${unit_dir}/osworld-vscode-adapter.service"

systemctl --user daemon-reload
systemctl --user enable osworld-vscode-adapter.service
systemctl --user restart osworld-vscode-adapter.service
