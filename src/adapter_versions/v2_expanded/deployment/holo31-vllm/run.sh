#!/usr/bin/env bash
set -euo pipefail

MODEL_ID=${MODEL_ID:-Hcompany/Holo-3.1-4B}
MODEL_REVISION=${MODEL_REVISION:-8c88265a5a159bfd1492db9243733dd2e6e04a6e}
MODEL_CACHE=${MODEL_CACHE:-/home/liuhao/models/holo3.1-4b/hf-cache}
CONTAINER_NAME=${CONTAINER_NAME:-holo31-4b}
IMAGE_NAME=${IMAGE_NAME:-local/vllm-qwen35:26.07-xgrammar-0.2.4}
HOST_PORT=${HOST_PORT:-8002}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-65536}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.21}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-6}

mkdir -p "${MODEL_CACHE}"

docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  --gpus all \
  --ipc host \
  -p "${HOST_PORT}:8001" \
  -e HF_ENDPOINT=https://hf-mirror.com \
  -e HF_HUB_DISABLE_XET=1 \
  -e HF_HUB_DOWNLOAD_TIMEOUT=120 \
  -e HF_HUB_ETAG_TIMEOUT=30 \
  -v "${MODEL_CACHE}:/root/.cache/huggingface" \
  "${IMAGE_NAME}" \
  vllm serve "${MODEL_ID}" \
  --revision "${MODEL_REVISION}" \
  --served-model-name holo3.1-4b \
  --host 0.0.0.0 \
  --port 8001 \
  --dtype bfloat16 \
  --max-model-len "${MAX_MODEL_LEN}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
