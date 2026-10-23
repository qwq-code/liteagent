#!/usr/bin/env bash
set -euo pipefail

BASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# One backend serves both short and long requests. The gateway owns the public
# ports and serializes long requests when the KV pool is under pressure.
HOST_BIND_ADDRESS=${HOST_BIND_ADDRESS:-127.0.0.1} \
HOST_PORT=${HOST_PORT:-8101} \
CONTAINER_NAME=${CONTAINER_NAME:-qwen38-27b-shared-256k} \
MAX_MODEL_LEN=${MAX_MODEL_LEN:-262144} \
MAX_NUM_SEQS=${MAX_NUM_SEQS:-6} \
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.75} \
MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS:-16384} \
  "${BASE_DIR}/run.sh"
