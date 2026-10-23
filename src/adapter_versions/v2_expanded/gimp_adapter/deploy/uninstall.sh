#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now osworld-gimp-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-gimp-adapter.service"
rm -rf "${HOME}/.local/share/osworld-gimp-adapter"
systemctl --user daemon-reload
