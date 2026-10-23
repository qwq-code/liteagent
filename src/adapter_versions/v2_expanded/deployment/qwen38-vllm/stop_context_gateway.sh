#!/usr/bin/env bash
set -euo pipefail

PID_FILE=${PID_FILE:-/home/liuhao/qwen38-context-gateway.pid}
if [[ ! -f "${PID_FILE}" ]]; then
  echo "gateway is not running"
  exit 0
fi
pid=$(<"${PID_FILE}")
if kill -0 "${pid}" 2>/dev/null; then
  kill "${pid}"
  for _ in {1..50}; do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.1
  done
fi
rm -f "${PID_FILE}"
echo "stopped gateway pid ${pid}"
