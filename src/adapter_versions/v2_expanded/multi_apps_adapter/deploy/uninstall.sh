#!/usr/bin/env bash
set -euo pipefail
systemctl --user disable --now osworld-multi-apps-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-multi-apps-adapter.service"
rm -rf "${HOME}/.local/share/osworld-multi-apps-adapter"
systemctl --user daemon-reload
