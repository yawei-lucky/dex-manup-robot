#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$DEX_ROOT"

NAVILA_CONTROL_FIFO="${NAVILA_CONTROL_FIFO:-${DEX_ROOT}/runtime/navila_control.fifo}"

mkdir -p "$(dirname "$NAVILA_CONTROL_FIFO")"

clear || true
cat <<EOF
============================================================
 NaVILA Manual Control Console
============================================================

Start / restart commands:

  # full closed-loop split launcher
  bash test/launch_navila_closed_loop_split.sh

  # client only
  bash test/run_navila_mujoco_client.sh

  # MuJoCo camera stream only
  cd ${HOME}/robotics/holosoma && bash scripts/run_navila_mujoco_stream.sh

  # Holosoma policy only
  bash test/run_holosoma_policy.sh

Control FIFO:
  $NAVILA_CONTROL_FIFO

Manual commands:
  go                         enable VLM automatic bridge execution
  pause                      disable VLM automatic execution and send stop
  stop                       send stop immediately and disable VLM automatic execution
  move forward 25 centimeters
  move forward 50 centimeters
  turn left 15 degrees
  turn right 15 degrees
  help
  quit

Notes:
  - Client must be running before commands can reach the bridge gate.
  - If FIFO is not ready yet, this console will wait/retry.
============================================================
EOF

send_cmd() {
    local cmd="$1"

    if [ ! -p "$NAVILA_CONTROL_FIFO" ]; then
        echo "[manual-console] FIFO not ready: $NAVILA_CONTROL_FIFO"
        echo "[manual-console] Start client first, or wait until bridge gate creates the FIFO."
        return 1
    fi

    # Use timeout to avoid hanging forever if the gate is not reading.
    if command -v timeout >/dev/null 2>&1; then
        if ! timeout 2 bash -lc 'printf "%s\n" "$0" > "$1"' "$cmd" "$NAVILA_CONTROL_FIFO"; then
            echo "[manual-console] failed to send within 2s. Is client/gate running?"
            return 1
        fi
    else
        printf "%s\n" "$cmd" > "$NAVILA_CONTROL_FIFO"
    fi

    echo "[manual-console] sent: $cmd"
}

while true; do
    read -r -p "navila> " cmd || break
    cmd="$(echo "$cmd" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    case "$cmd" in
        "")
            continue
            ;;
        quit|exit)
            echo "[manual-console] exit"
            break
            ;;
        help|h|\?)
            cat <<EOF
Commands:
  go
  pause
  stop
  move forward 25 centimeters
  move forward 50 centimeters
  turn left 15 degrees
  turn right 15 degrees
  quit
EOF
            ;;
        *)
            send_cmd "$cmd" || true
            ;;
    esac
done
