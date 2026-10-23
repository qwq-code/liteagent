#!/usr/bin/env bash
set -euo pipefail
/usr/bin/python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8768/health", timeout=5) as response:
    payload = json.load(response)
required = (
    "gimp_available",
    "gimp_console_available",
    "pillow_available",
)
if payload.get("status") != "ok" or not all(payload.get(key) for key in required):
    raise SystemExit(json.dumps(payload))
print(json.dumps(payload, sort_keys=True))
PY
