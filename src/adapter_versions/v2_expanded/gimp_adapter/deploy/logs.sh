#!/usr/bin/env bash
set -euo pipefail
journalctl --user -u osworld-gimp-adapter.service -n "${1:-200}" --no-pager
