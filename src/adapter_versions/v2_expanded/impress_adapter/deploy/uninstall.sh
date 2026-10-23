#!/usr/bin/env bash
set -euo pipefail
systemctl --user disable --now osworld-impress-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-impress-adapter.service"
rm -rf "${HOME}/.local/share/osworld-impress-adapter"
systemctl --user daemon-reload
