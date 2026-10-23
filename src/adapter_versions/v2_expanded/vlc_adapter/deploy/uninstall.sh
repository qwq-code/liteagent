#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now osworld-vlc-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-vlc-adapter.service"
rm -rf "${HOME}/.local/share/osworld-vlc-adapter"
systemctl --user daemon-reload
