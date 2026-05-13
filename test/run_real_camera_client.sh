#!/usr/bin/env bash
set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$DEX_ROOT"

# -------------------------------
# G1 RealSense ZMQ server config
# -------------------------------
CAMERA_HOST="${CAMERA_HOST:-192.168.123.164}"
CAMERA_PORT="${CAMERA_PORT:-5556}"
CAMERA_SERVER="tcp://${CAMERA_HOST}:${CAMERA_PORT}"

# -------------------------------
# Path config
# -------------------------------
HOLOSOMA_ROOT="${HOLOSOMA_ROOT:-${HOME}/robotics/nav_holosoma}"
IMAGES_DIR="${IMAGES_DIR:-${HOLOSOMA_ROOT}/runtime_image_file/navila_mujoco_stream}"

# -------------------------------
# Stream config
# -------------------------------
CAMERA_FPS="${CAMERA_FPS:-10.0}"
CAMERA_PREFIX="${CAMERA_PREFIX:-real}"
CAMERA_MAX_FILES="${CAMERA_MAX_FILES:-500}"
CAMERA_TIMEOUT_MS="${CAMERA_TIMEOUT_MS:-2000}"

mkdir -p "$IMAGES_DIR"

echo "[real_camera] CAMERA_SERVER=$CAMERA_SERVER"
echo "[real_camera] IMAGES_DIR=$IMAGES_DIR"
echo "[real_camera] FPS=$CAMERA_FPS"

python3 test/real_camera_client.py \
  --server "$CAMERA_SERVER" \
  --out-dir "$IMAGES_DIR" \
  --fps "$CAMERA_FPS" \
  --prefix "$CAMERA_PREFIX" \
  --timeout-ms "$CAMERA_TIMEOUT_MS" \
  --max-files "$CAMERA_MAX_FILES" \
  --clear-dir
