#!/usr/bin/env bash
set -euo pipefail

MODEL_ID=${MODEL_ID:-Qwen/Qwen3.8-27B}
MODEL_REVISION=${MODEL_REVISION:-1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0}
MODEL_CACHE=${MODEL_CACHE:-/home/liuhao/models/qwen3.8-27b/hf-cache}
CONTAINER_NAME=${CONTAINER_NAME:-qwen38-27b}
IMAGE_NAME=${IMAGE_NAME:-local/vllm-qwen38:26.07-transformers5.8.0}
HOST_PORT=${HOST_PORT:-8001}
HOST_BIND_ADDRESS=${HOST_BIND_ADDRESS:-0.0.0.0}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-65536}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.75}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-6}
MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS:-16384}

mkdir -p "${MODEL_CACHE}"

docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  --gpus all \
  --ipc host \
  -p "${HOST_BIND_ADDRESS}:${HOST_PORT}:8001" \
  -e HF_ENDPOINT=https://hf-mirror.com \
  -e HF_HUB_DISABLE_XET=1 \
  -e HF_HUB_DOWNLOAD_TIMEOUT=120 \
  -e HF_HUB_ETAG_TIMEOUT=30 \
  -v "${MODEL_CACHE}:/root/.cache/huggingface" \
  "${IMAGE_NAME}" \
  vllm serve "${MODEL_ID}" \
  --revision "${MODEL_REVISION}" \
  --served-model-name qwen3.8-27b \
  --host 0.0.0.0 \
  --port 8001 \
  --dtype bfloat16 \
  --max-model-len "${MAX_MODEL_LEN}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}" \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
