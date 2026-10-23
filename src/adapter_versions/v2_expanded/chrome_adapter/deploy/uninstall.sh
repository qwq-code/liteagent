#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now osworld-chrome-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-chrome-adapter.service"
rm -rf "${HOME}/.local/share/osworld-chrome-adapter"
systemctl --user daemon-reload

