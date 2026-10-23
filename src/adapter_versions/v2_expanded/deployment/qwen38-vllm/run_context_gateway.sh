#!/usr/bin/env bash
set -euo pipefail

BASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BACKEND_URL=${BACKEND_URL:-http://127.0.0.1:8101}
GATEWAY_BIND=${GATEWAY_BIND:-0.0.0.0}
SHORT_PORT=${SHORT_PORT:-8001}
LONG_PORT=${LONG_PORT:-8003}
LOG_FILE=${LOG_FILE:-/home/liuhao/qwen38-context-gateway.log}
PID_FILE=${PID_FILE:-/home/liuhao/qwen38-context-gateway.pid}

if [[ -f "${PID_FILE}" ]] && kill -0 "$(<"${PID_FILE}")" 2>/dev/null; then
  echo "gateway already running with pid $(<"${PID_FILE}")"
  exit 0
fi

nohup python3 "${BASE_DIR}/context_gateway.py" \
  --backend "${BACKEND_URL}" \
  --bind "${GATEWAY_BIND}" \
  --short-port "${SHORT_PORT}" \
  --long-port "${LONG_PORT}" \
  >>"${LOG_FILE}" 2>&1 &
echo $! >"${PID_FILE}"
echo "started gateway pid $(<"${PID_FILE}")"
