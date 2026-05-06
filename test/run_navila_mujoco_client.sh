#!/usr/bin/env bash
set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$DEX_ROOT"

# -------------------------------
# VLM server config
# -------------------------------
# 默认使用你的 VLM server / 仿真服务地址
VLM_HOST="${VLM_HOST:-100.110.59.37}"
VLM_PORT="${VLM_PORT:-54321}"

# -------------------------------
# Path config
# -------------------------------
HOLOSOMA_ROOT="${HOLOSOMA_ROOT:-${HOME}/robotics/holosoma}"

IMAGES_DIR="${IMAGES_DIR:-${HOLOSOMA_ROOT}/runtime_image_file/navila_mujoco_stream}"
WINDOW_DIR="${WINDOW_DIR:-${DEX_ROOT}/runtime/navila_windows}"
PROMPT_JSON="${PROMPT_JSON:-test/navila_box_testset/prompt_bag_area.json}"
CLIENT_LOG_DIR="${CLIENT_LOG_DIR:-${DEX_ROOT}/runtime/logs}"
CLIENT_LOG_FILE="${CLIENT_LOG_FILE:-${CLIENT_LOG_DIR}/navila_client_$(date +%Y%m%d_%H%M%S).log}"
NAVILA_CONTROL_FIFO="${NAVILA_CONTROL_FIFO:-${DEX_ROOT}/runtime/navila_control.fifo}"

# -------------------------------
# Bridge gate config
# -------------------------------
NAVILA_REQUIRE_GO="${NAVILA_REQUIRE_GO:-1}"
NAVILA_BOOTSTRAP_STAND="${NAVILA_BOOTSTRAP_STAND:-1}"
BRIDGE_CMD="bash test/run_navila_bridge_ros2.sh"
if [ "$NAVILA_BOOTSTRAP_STAND" = "1" ]; then
  BRIDGE_CMD="$BRIDGE_CMD --bootstrap-stand"
fi
BRIDGE_GATE_CMD="python3 test/navila_bridge_gate.py --bridge-cmd '$BRIDGE_CMD' --control-fifo '$NAVILA_CONTROL_FIFO'"
if [ "$NAVILA_REQUIRE_GO" = "1" ]; then
  BRIDGE_GATE_CMD="$BRIDGE_GATE_CMD --require-go"
fi

mkdir -p "$WINDOW_DIR"
mkdir -p "$CLIENT_LOG_DIR"
mkdir -p "$IMAGES_DIR"
mkdir -p "$(dirname "$NAVILA_CONTROL_FIFO")"
rm -f "$NAVILA_CONTROL_FIFO"

echo "[NAVILA_CLIENT] DEX_ROOT=$DEX_ROOT"
echo "[NAVILA_CLIENT] HOLOSOMA_ROOT=$HOLOSOMA_ROOT"
echo "[NAVILA_CLIENT] VLM=$VLM_HOST:$VLM_PORT"
echo "[NAVILA_CLIENT] IMAGES_DIR=$IMAGES_DIR"
echo "[NAVILA_CLIENT] WINDOW_DIR=$WINDOW_DIR"
echo "[NAVILA_CLIENT] PROMPT_JSON=$PROMPT_JSON"
echo "[NAVILA_CLIENT] CLIENT_LOG_FILE=$CLIENT_LOG_FILE"
echo "[NAVILA_CLIENT] NAVILA_CONTROL_FIFO=$NAVILA_CONTROL_FIFO"
echo "[NAVILA_CLIENT] BRIDGE_GATE=$BRIDGE_GATE_CMD"
echo "[NAVILA_CLIENT] NAVILA_REQUIRE_GO=$NAVILA_REQUIRE_GO"
echo "[NAVILA_CLIENT] NAVILA_BOOTSTRAP_STAND=$NAVILA_BOOTSTRAP_STAND"
echo "[NAVILA_CLIENT] NAVILA_NO_VLM=${NAVILA_NO_VLM:-1}"
echo "[NAVILA_CLIENT] NAVILA_IGNORE_EXISTING_FRAMES=${NAVILA_IGNORE_EXISTING_FRAMES:-1}"
echo "[NAVILA_CLIENT] Type 'go' into the manual-control console to enable VLM bridge execution."
echo "[NAVILA_CLIENT] Manual commands: stop, pause, move forward 25 centimeters, turn left 15 degrees."

NO_VLM_FLAG=""
if [ "${NAVILA_NO_VLM:-1}" = "1" ]; then
  NO_VLM_FLAG="--no-vlm"
fi

IGNORE_EXISTING_FLAG=""
if [ "${NAVILA_IGNORE_EXISTING_FRAMES:-1}" = "1" ]; then
  IGNORE_EXISTING_FLAG="--ignore-existing"
fi

stdbuf -oL -eL python test/navila_stream_client.py \
  --host "$VLM_HOST" \
  --port "$VLM_PORT" \
  --prompt-json "$PROMPT_JSON" \
  --images-dir "$IMAGES_DIR" \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec "${NAVILA_CLIENT_INTERVAL_SEC:-0.2}" \
  --bridge-cmd "$BRIDGE_GATE_CMD" \
  --raw \
  $NO_VLM_FLAG \
  $IGNORE_EXISTING_FLAG \
  2>&1 | tee -a "$CLIENT_LOG_FILE"
