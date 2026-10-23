#!/usr/bin/env bash
set -euo pipefail
journalctl --user -u osworld-impress-adapter.service -n "${1:-200}" --no-pager
