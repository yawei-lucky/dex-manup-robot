#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HOLOSOMA_ROOT="${HOLOSOMA_ROOT:-${HOME}/robotics/holosoma}"
VLM_HOST="${VLM_HOST:-100.110.59.37}"
VLM_PORT="${VLM_PORT:-54321}"
HOLOSOMA_INTERFACE="${HOLOSOMA_INTERFACE:-lo}"

RUNTIME_DIR="${DEX_ROOT}/runtime"
LAYOUT_FILE="${RUNTIME_DIR}/terminator_navila_closed_loop.conf"

mkdir -p "$RUNTIME_DIR"

echo "[NAVILA_CLOSED_LOOP] DEX_ROOT=$DEX_ROOT"
echo "[NAVILA_CLOSED_LOOP] HOLOSOMA_ROOT=$HOLOSOMA_ROOT"
echo "[NAVILA_CLOSED_LOOP] VLM=$VLM_HOST:$VLM_PORT"
echo "[NAVILA_CLOSED_LOOP] HOLOSOMA_INTERFACE=$HOLOSOMA_INTERFACE"
echo "[NAVILA_CLOSED_LOOP] layout=$LAYOUT_FILE"

sudo -v || true

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
      size = 1600, 1000

    [[[vpaned0]]]
      type = VPaned
      parent = window0
      order = 0
      position = 280
      ratio = 0.28

    [[[hpaned0]]]
      type = HPaned
      parent = vpaned0
      order = 0
      position = 800
      ratio = 0.50

    [[[terminal_mujoco]]]
      type = Terminal
      parent = hpaned0
      order = 0
      title = MuJoCo Camera Stream
      command = bash -lc 'cd "$HOLOSOMA_ROOT"; echo "[MuJoCo Camera Stream]"; echo "bash scripts/run_navila_mujoco_stream.sh"; bash scripts/run_navila_mujoco_stream.sh; exec bash'

    [[[terminal_policy]]]
      type = Terminal
      parent = hpaned0
      order = 1
      title = Holosoma Policy
      command = bash -lc 'cd "$DEX_ROOT"; echo "[Holosoma Policy]"; echo "bash test/run_holosoma_policy.sh"; HOLOSOMA_ROOT="$HOLOSOMA_ROOT" HOLOSOMA_INTERFACE="$HOLOSOMA_INTERFACE" bash test/run_holosoma_policy.sh; exec bash'

    [[[terminal_client]]]
      type = Terminal
      parent = vpaned0
      order = 1
      title = NaVILA Client + Bridge
      command = bash -lc 'cd "$DEX_ROOT"; echo "[NaVILA Client + Bridge]"; echo "bash test/run_navila_client_wait_ok.sh"; VLM_HOST="$VLM_HOST" VLM_PORT="$VLM_PORT" HOLOSOMA_ROOT="$HOLOSOMA_ROOT" bash test/run_navila_client_wait_ok.sh; exec bash'
[plugins]
EOF

terminator --config "$LAYOUT_FILE" --layout navila_closed_loop &
TERM_PID=$!

sleep 2

if command -v wmctrl >/dev/null 2>&1; then
    wmctrl -a "NaVILA Closed Loop" || true
    wmctrl -r "NaVILA Closed Loop" -b add,above || true
    sleep 0.3
    wmctrl -r "NaVILA Closed Loop" -b remove,above || true
fi

wait "$TERM_PID"