#!/usr/bin/env bash
set -euo pipefail
journalctl --user -u osworld-vscode-adapter.service -n "${1:-200}" --no-pager
