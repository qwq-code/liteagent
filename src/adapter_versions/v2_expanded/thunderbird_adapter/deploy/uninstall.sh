#!/usr/bin/env bash
set -euo pipefail
systemctl --user disable --now osworld-thunderbird-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-thunderbird-adapter.service"
rm -rf "${HOME}/.local/share/osworld-thunderbird-adapter"
systemctl --user daemon-reload
