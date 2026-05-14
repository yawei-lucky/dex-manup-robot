#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

NAVILA_MODE="${NAVILA_MODE:-sim}"   # sim | real
NAVILA_NO_VLM="${NAVILA_NO_VLM:-1}" # 1 = skip VLM inference, manual control only
NAVILA_CLIENT_WAIT_OK="${NAVILA_CLIENT_WAIT_OK:-0}" # 1 = run a client script that waits for "OK" input before starting the main loop, for better terminal output control during demos
HOLOSOMA_ROOT="${HOLOSOMA_ROOT:-${HOME}/robotics/nav_holosoma}"
VLM_HOST="${VLM_HOST:-100.110.59.37}"
VLM_PORT="${VLM_PORT:-54321}"
NAVILA_CONTROL_FIFO="${NAVILA_CONTROL_FIFO:-${DEX_ROOT}/runtime/navila_control.fifo}"

if [ "$NAVILA_MODE" = "real" ]; then
    HOLOSOMA_INTERFACE="${HOLOSOMA_INTERFACE:-enp4s0}"
    RUN_CAMERA_STREAM="${RUN_CAMERA_STREAM:-0}"
    NAVILA_CLIENT_INTERVAL_SEC="${NAVILA_CLIENT_INTERVAL_SEC:-1.0}"
    NAVILA_MANUAL_STEP_CM="${NAVILA_MANUAL_STEP_CM:-10}"
    NAVILA_MANUAL_TURN_DEG="${NAVILA_MANUAL_TURN_DEG:-10}"
    NAVILA_LINEAR_SPEED="${NAVILA_LINEAR_SPEED:-0.20}"
    NAVILA_ANGULAR_SPEED_DEGPS="${NAVILA_ANGULAR_SPEED_DEGPS:-30.0}"
else
    HOLOSOMA_INTERFACE="${HOLOSOMA_INTERFACE:-lo}"
    RUN_CAMERA_STREAM="${RUN_CAMERA_STREAM:-1}"
    NAVILA_CLIENT_INTERVAL_SEC="${NAVILA_CLIENT_INTERVAL_SEC:-0.2}"
    NAVILA_MANUAL_STEP_CM="${NAVILA_MANUAL_STEP_CM:-20}"
    NAVILA_MANUAL_TURN_DEG="${NAVILA_MANUAL_TURN_DEG:-15}"
    NAVILA_LINEAR_SPEED="${NAVILA_LINEAR_SPEED:-0.45}"
    NAVILA_ANGULAR_SPEED_DEGPS="${NAVILA_ANGULAR_SPEED_DEGPS:-60.0}"
fi

RUNTIME_DIR="${DEX_ROOT}/runtime"
LAYOUT_FILE="${RUNTIME_DIR}/terminator_navila_closed_loop.conf"

mkdir -p "$RUNTIME_DIR"

NAVILA_SCENE="${NAVILA_SCENE:-indoor_red_shoebox}"
PROMPT_JSON="${PROMPT_JSON:-test/navila_box_testset/prompt_red_shoebox.json}"

if [ "$RUN_CAMERA_STREAM" = "1" ]; then
    CAMERA_COMMAND="cd \"$HOLOSOMA_ROOT\"; echo \"[MuJoCo Camera Stream]\"; echo \"NAVILA_SCENE=$NAVILA_SCENE bash scripts/run_navila_mujoco_stream.sh\"; NAVILA_SCENE=\"$NAVILA_SCENE\" bash scripts/run_navila_mujoco_stream.sh; exec bash"
    CAMERA_TITLE="MuJoCo Camera Stream"
else
    CAMERA_COMMAND="cd \"$DEX_ROOT\"; echo \"[Camera Stream Disabled]\"; echo \"NAVILA_MODE=real, so MuJoCo camera stream is not started.\"; echo \"Start your real camera/image stream separately if needed.\"; exec bash"
    CAMERA_TITLE="Camera Stream Disabled"
fi

if [ "$NAVILA_CLIENT_WAIT_OK" = "1" ]; then
    CLIENT_SCRIPT="test/run_navila_client_wait_ok.sh"
else
    CLIENT_SCRIPT="test/run_navila_mujoco_client.sh"
fi

cat > "$LAYOUT_FILE" <<EOF
[global_config]
[keybindings]
[profiles]
  [[default]]
[layouts]
  [[navila_closed_loop]]
    [[[window0]]]
      type = Window
      parent = ""
      title = NaVILA Closed Loop
      size = 1700, 1000

    [[[vpaned_main]]]
      type = VPaned
      parent = window0
      order = 0
      position = 300
      ratio = 0.30

    [[[hpaned_top]]]
      type = HPaned
      parent = vpaned_main
      order = 0
      position = 850
      ratio = 0.50

    [[[hpaned_bottom]]]
      type = HPaned
      parent = vpaned_main
      order = 1
      position = 1300
      ratio = 0.76

    [[[terminal_camera]]]
      type = Terminal
      parent = hpaned_top
      order = 0
      title = $CAMERA_TITLE
      command = bash -lc '$CAMERA_COMMAND'

    [[[terminal_policy]]]
      type = Terminal
      parent = hpaned_top
      order = 1
      title = Holosoma Policy
      command = bash -lc 'cd "$DEX_ROOT"; echo "[Holosoma Policy]"; echo "HOLOSOMA_INTERFACE=$HOLOSOMA_INTERFACE bash test/run_holosoma_policy.sh"; HOLOSOMA_ROOT="$HOLOSOMA_ROOT" HOLOSOMA_INTERFACE="$HOLOSOMA_INTERFACE" bash test/run_holosoma_policy.sh; exec bash'

    [[[terminal_client]]]
      type = Terminal
      parent = hpaned_bottom
      order = 0
      title = NaVILA Client + Bridge
      command = bash -lc 'cd "$DEX_ROOT"; echo "[NaVILA Client + Bridge]"; echo "NAVILA_MODE=$NAVILA_MODE NAVILA_NO_VLM=$NAVILA_NO_VLM VLM_HOST=$VLM_HOST VLM_PORT=$VLM_PORT PROMPT_JSON=$PROMPT_JSON bash $CLIENT_SCRIPT"; NAVILA_MODE="$NAVILA_MODE" NAVILA_NO_VLM="$NAVILA_NO_VLM" VLM_HOST="$VLM_HOST" VLM_PORT="$VLM_PORT" HOLOSOMA_ROOT="$HOLOSOMA_ROOT" NAVILA_CONTROL_FIFO="$NAVILA_CONTROL_FIFO" NAVILA_CLIENT_INTERVAL_SEC="$NAVILA_CLIENT_INTERVAL_SEC" NAVILA_LINEAR_SPEED="$NAVILA_LINEAR_SPEED" NAVILA_ANGULAR_SPEED_DEGPS="$NAVILA_ANGULAR_SPEED_DEGPS" PROMPT_JSON="$PROMPT_JSON" bash "$CLIENT_SCRIPT"; exec bash'

    [[[terminal_manual]]]
      type = Terminal
      parent = hpaned_bottom
      order = 1
      title = Manual Control Console
      command = bash -lc 'cd "$DEX_ROOT"; echo "[Manual Control Console]"; echo "NAVILA_CONTROL_FIFO=$NAVILA_CONTROL_FIFO bash test/run_navila_manual_console.sh"; NAVILA_CONTROL_FIFO="$NAVILA_CONTROL_FIFO" NAVILA_MANUAL_STEP_CM="$NAVILA_MANUAL_STEP_CM" NAVILA_MANUAL_TURN_DEG="$NAVILA_MANUAL_TURN_DEG" bash test/run_navila_manual_console.sh; exec bash'
[plugins]
EOF

echo "[NAVILA_CLOSED_LOOP] DEX_ROOT=$DEX_ROOT"
echo "[NAVILA_CLOSED_LOOP] NAVILA_MODE=$NAVILA_MODE"
echo "[NAVILA_CLOSED_LOOP] NAVILA_NO_VLM=$NAVILA_NO_VLM"
echo "[NAVILA_CLOSED_LOOP] NAVILA_CLIENT_WAIT_OK=$NAVILA_CLIENT_WAIT_OK"
echo "[NAVILA_CLOSED_LOOP] CLIENT_SCRIPT=$CLIENT_SCRIPT"
echo "[NAVILA_CLOSED_LOOP] HOLOSOMA_ROOT=$HOLOSOMA_ROOT"
echo "[NAVILA_CLOSED_LOOP] VLM=$VLM_HOST:$VLM_PORT"
echo "[NAVILA_CLOSED_LOOP] HOLOSOMA_INTERFACE=$HOLOSOMA_INTERFACE"
echo "[NAVILA_CLOSED_LOOP] RUN_CAMERA_STREAM=$RUN_CAMERA_STREAM"
echo "[NAVILA_CLOSED_LOOP] NAVILA_CONTROL_FIFO=$NAVILA_CONTROL_FIFO"
echo "[NAVILA_CLOSED_LOOP] NAVILA_CLIENT_INTERVAL_SEC=$NAVILA_CLIENT_INTERVAL_SEC"
echo "[NAVILA_CLOSED_LOOP] NAVILA_MANUAL_STEP_CM=$NAVILA_MANUAL_STEP_CM"
echo "[NAVILA_CLOSED_LOOP] NAVILA_MANUAL_TURN_DEG=$NAVILA_MANUAL_TURN_DEG"
echo "[NAVILA_CLOSED_LOOP] NAVILA_LINEAR_SPEED=$NAVILA_LINEAR_SPEED"
echo "[NAVILA_CLOSED_LOOP] NAVILA_ANGULAR_SPEED_DEGPS=$NAVILA_ANGULAR_SPEED_DEGPS"
echo "[NAVILA_CLOSED_LOOP] layout=$LAYOUT_FILE"

if command -v sudo >/dev/null 2>&1; then
    sudo -v || true
fi

terminator --config "$LAYOUT_FILE" --layout navila_closed_loop &
TERM_PID=$!

sleep 2

if command -v wmctrl >/dev/null 2>&1; then
    wmctrl -a "NaVILA Closed Loop" || true
    wmctrl -r "NaVILA Closed Loop" -b add,above || true
    sleep 0.3
    wmctrl -r "NaVILA Closed Loop" -b remove,above || true
elif command -v xdotool >/dev/null 2>&1; then
    WIN_ID="$(xdotool search --sync --name "NaVILA Closed Loop" | head -n 1 || true)"
    if [ -n "$WIN_ID" ]; then
        xdotool windowactivate "$WIN_ID" windowraise "$WIN_ID" || true
    fi
fi

wait "$TERM_PID"
