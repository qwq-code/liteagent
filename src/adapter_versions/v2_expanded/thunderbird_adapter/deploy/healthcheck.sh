#!/usr/bin/env bash
set -euo pipefail
/usr/bin/python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8773/health", timeout=10) as response:
    payload = json.load(response)
if (
    payload.get("status") != "ok"
    or not payload.get("all_commands_available")
    or not payload.get("all_modules_available")
    or not payload.get("profile_root_writable")
    or not payload.get("display")
    or not payload.get("dbus_session")
):
    raise SystemExit(json.dumps(payload))
print(json.dumps(payload, sort_keys=True))
PY
