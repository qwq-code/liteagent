#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now osworld-calc-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-calc-adapter.service"
rm -rf "${HOME}/.local/share/osworld-calc-adapter"
systemctl --user daemon-reload
