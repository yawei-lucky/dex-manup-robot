#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$DEX_ROOT"

# 默认假设 holosoma 和 dex-manup-robot 都在 ~/robotics 下
HOLOSOMA_ROOT="${HOLOSOMA_ROOT:-${HOME}/robotics/holosoma}"

IMAGES_DIR="${IMAGES_DIR:-${HOLOSOMA_ROOT}/runtime/navila_mujoco_stream}"
WINDOW_DIR="${WINDOW_DIR:-${DEX_ROOT}/runtime/navila_windows}"
PROMPT_JSON="${PROMPT_JSON:-test/navila_box_testset/prompt_bag_area.json}"

mkdir -p "$WINDOW_DIR"

echo "[NAVILA_CLIENT] DEX_ROOT=$DEX_ROOT"
echo "[NAVILA_CLIENT] HOLOSOMA_ROOT=$HOLOSOMA_ROOT"
echo "[NAVILA_CLIENT] IMAGES_DIR=$IMAGES_DIR"
echo "[NAVILA_CLIENT] WINDOW_DIR=$WINDOW_DIR"
echo "[NAVILA_CLIENT] PROMPT_JSON=$PROMPT_JSON"

python test/navila_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json "$PROMPT_JSON" \
  --images-dir "$IMAGES_DIR" \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.2 \
  --save-window-dir "$WINDOW_DIR" \
  --raw