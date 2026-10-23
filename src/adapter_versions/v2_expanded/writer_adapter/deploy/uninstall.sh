#!/usr/bin/env bash
set -euo pipefail
curl -fsS -X POST \
  http://127.0.0.1:8770/v1/shutdown \
  -H 'Content-Type: application/json' \
  --data '{"timeout_ms":10000}' \
  >/dev/null 2>&1 || true
systemctl --user disable --now osworld-writer-adapter.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/osworld-writer-adapter.service"
rm -rf "${HOME}/.local/share/osworld-writer-adapter"
systemctl --user daemon-reload
