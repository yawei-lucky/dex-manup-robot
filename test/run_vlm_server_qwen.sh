#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$DEX_ROOT"

VLM_HOST="${VLM_HOST:-localhost}"
VLM_PORT="${VLM_PORT:-54321}"
VLM_MODEL="${VLM_MODEL:-qwen-vl-max}"
VLM_IMAGE_MAX_WIDTH="${VLM_IMAGE_MAX_WIDTH:-320}"
VLM_IMAGE_QUALITY="${VLM_IMAGE_QUALITY:-70}"

if [ -z "$DASHSCOPE_API_KEY" ] && [ -z "$QWEN_API_KEY" ]; then
    echo "[vlm_server] ERROR: DASHSCOPE_API_KEY or QWEN_API_KEY not set."
    exit 1
fi

echo "[vlm_server] model=$VLM_MODEL host=$VLM_HOST port=$VLM_PORT"

python3 others/vlm_server_qwen.py \
    --host "$VLM_HOST" \
    --port "$VLM_PORT" \
    --model "$VLM_MODEL" \
    --image-max-width "$VLM_IMAGE_MAX_WIDTH" \
    --image-quality "$VLM_IMAGE_QUALITY"
