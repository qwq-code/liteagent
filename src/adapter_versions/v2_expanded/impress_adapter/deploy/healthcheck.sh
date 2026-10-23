#!/usr/bin/env bash
set -euo pipefail
/usr/bin/python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8766/health", timeout=5) as response:
    payload = json.load(response)
if payload.get("status") != "ok" or not payload.get("uno_module_available"):
    raise SystemExit(json.dumps(payload))
print(json.dumps(payload, sort_keys=True))
PY
