#!/usr/bin/env bash
set -euo pipefail

/usr/bin/python3 - <<'PY'
import json
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1:8772/v1/shutdown",
    data=b'{"timeout_ms":10000}',
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        print(json.load(response))
except Exception as exc:
    print("shutdown warning:", exc)
PY
systemctl --user restart osworld-vlc-adapter.service
