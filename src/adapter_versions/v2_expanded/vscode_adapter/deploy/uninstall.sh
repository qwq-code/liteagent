#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now osworld-vscode-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-vscode-adapter.service"
rm -rf "${HOME}/.local/share/osworld-vscode-adapter"
code --uninstall-extension osworld.array-variables >/dev/null 2>&1 || true
systemctl --user daemon-reload
