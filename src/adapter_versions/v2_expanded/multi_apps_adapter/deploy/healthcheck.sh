#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:8774/health", timeout=10) as response:
    payload = json.load(response)
assert payload["status"] == "ok" and payload["mode"] == "strict_generic", payload
print(json.dumps(payload, indent=2))
PY
