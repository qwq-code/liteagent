#!/usr/bin/env bash
set -euo pipefail
journalctl --user -u osworld-multi-apps-adapter.service -n "${1:-200}" --no-pager
