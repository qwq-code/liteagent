#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now osworld-os-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-os-adapter.service"
rm -rf "${HOME}/.local/share/osworld-os-adapter"
systemctl --user daemon-reload

