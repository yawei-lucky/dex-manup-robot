#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HOLOSOMA_ROOT="${HOLOSOMA_ROOT:-${HOME}/robotics/holosoma}"
VLM_HOST="${VLM_HOST:-100.110.59.37}"
VLM_PORT="${VLM_PORT:-54321}"
HOLOSOMA_INTERFACE="${HOLOSOMA_INTERFACE:-lo}"
NAVILA_CONTROL_FIFO="${NAVILA_CONTROL_FIFO:-${DEX_ROOT}/runtime/navila_control.fifo}"

RUNTIME_DIR="${DEX_ROOT}/runtime"
LAYOUT_FILE="${RUNTIME_DIR}/terminator_navila_closed_loop.conf"

mkdir -p "$RUNTIME_DIR"

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

    # Whole window: upper area for MuJoCo/policy, lower area for client/manual input.
    [[[vpaned_main]]]
      type = VPaned
      parent = window0
      order = 0
      position = 300
      ratio = 0.30

    # Upper area: MuJoCo and low-level policy.
    [[[hpaned_top]]]
      type = HPaned
      parent = vpaned_main
      order = 0
      position = 850
      ratio = 0.50

    # Lower area: client on the left, manual console on the right.
    # The manual console is intentionally smaller.
    [[[hpaned_bottom]]]
      type = HPaned
      parent = vpaned_main
      order = 1
      position = 1300
      ratio = 0.76

    [[[terminal_mujoco]]]
      type = Terminal
      parent = hpaned_top
      order = 0
      title = MuJoCo Camera Stream
      command = bash -lc 'cd "$HOLOSOMA_ROOT"; echo "[MuJoCo Camera Stream]"; echo "bash scripts/run_navila_mujoco_stream.sh"; bash scripts/run_navila_mujoco_stream.sh; exec bash'

    [[[terminal_policy]]]
      type = Terminal
      parent = hpaned_top
      order = 1
      title = Holosoma Policy
      command = bash -lc 'cd "$DEX_ROOT"; echo "[Holosoma Policy]"; echo "HOLOSOMA_ROOT=$HOLOSOMA_ROOT HOLOSOMA_INTERFACE=$HOLOSOMA_INTERFACE bash test/run_holosoma_policy.sh"; HOLOSOMA_ROOT="$HOLOSOMA_ROOT" HOLOSOMA_INTERFACE="$HOLOSOMA_INTERFACE" bash test/run_holosoma_policy.sh; exec bash'

    [[[terminal_client]]]
      type = Terminal
      parent = hpaned_bottom
      order = 0
      title = NaVILA Client + Bridge
      command = bash -lc 'cd "$DEX_ROOT"; echo "[NaVILA Client + Bridge]"; echo "VLM_HOST=$VLM_HOST VLM_PORT=$VLM_PORT HOLOSOMA_ROOT=$HOLOSOMA_ROOT NAVILA_CONTROL_FIFO=$NAVILA_CONTROL_FIFO bash test/run_navila_client_wait_ok.sh"; VLM_HOST="$VLM_HOST" VLM_PORT="$VLM_PORT" HOLOSOMA_ROOT="$HOLOSOMA_ROOT" NAVILA_CONTROL_FIFO="$NAVILA_CONTROL_FIFO" bash test/run_navila_client_wait_ok.sh; exec bash'

    [[[terminal_manual]]]
      type = Terminal
      parent = hpaned_bottom
      order = 1
      title = Manual Control Console
      command = bash -lc 'cd "$DEX_ROOT"; echo "[Manual Control Console]"; echo "NAVILA_CONTROL_FIFO=$NAVILA_CONTROL_FIFO bash test/run_navila_manual_console.sh"; NAVILA_CONTROL_FIFO="$NAVILA_CONTROL_FIFO" bash test/run_navila_manual_console.sh; exec bash'
[plugins]
EOF

echo "[NAVILA_CLOSED_LOOP] DEX_ROOT=$DEX_ROOT"
echo "[NAVILA_CLOSED_LOOP] HOLOSOMA_ROOT=$HOLOSOMA_ROOT"
echo "[NAVILA_CLOSED_LOOP] VLM=$VLM_HOST:$VLM_PORT"
echo "[NAVILA_CLOSED_LOOP] HOLOSOMA_INTERFACE=$HOLOSOMA_INTERFACE"
echo "[NAVILA_CLOSED_LOOP] NAVILA_CONTROL_FIFO=$NAVILA_CONTROL_FIFO"
echo "[NAVILA_CLOSED_LOOP] layout=$LAYOUT_FILE"

# Cache sudo once before opening Terminator.
if command -v sudo >/dev/null 2>&1; then
    sudo -v || true
fi

terminator --config "$LAYOUT_FILE" --layout navila_closed_loop &
TERM_PID=$!

sleep 2

# Bring the new Terminator window to the front when supported.
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
