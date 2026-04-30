#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$DEX_ROOT"

NAVILA_CONTROL_FIFO="${NAVILA_CONTROL_FIFO:-${DEX_ROOT}/runtime/navila_control.fifo}"
STEP_CM="${NAVILA_MANUAL_STEP_CM:-20}"
TURN_DEG="${NAVILA_MANUAL_TURN_DEG:-15}"

mkdir -p "$(dirname "$NAVILA_CONTROL_FIFO")"

clear || true
cat <<EOF
============================================================
 NaVILA Manual Control Console
============================================================

Start / restart commands:

  # full closed-loop split launcher
  bash test/launch_navila_closed_loop.sh

  # real-robot closed-loop launcher
  NAVILA_MODE=real HOLOSOMA_INTERFACE=enp4s0 bash test/launch_navila_closed_loop.sh

  # manual console only
  bash test/run_navila_manual_console.sh

  # client only
  bash test/run_navila_mujoco_client.sh

  # Holosoma policy only
  HOLOSOMA_INTERFACE=enp4s0 bash test/run_holosoma_policy.sh

Control FIFO:
  $NAVILA_CONTROL_FIFO

Keyboard control:
  ↑      move forward ${STEP_CM} centimeters
  ↓      move backward ${STEP_CM} centimeters
  ←      move left ${STEP_CM} centimeters
  →      move right ${STEP_CM} centimeters
  n      turn left ${TURN_DEG} degrees
  m      turn right ${TURN_DEG} degrees
  space  stop
  =      emergency stop / stand still
  g      go / enable VLM automatic bridge execution
  p      pause / disable VLM automatic execution and send stop
  q      quit this console

Text commands are also supported:
  go
  pause
  stop
  =
  move forward 25 centimeters
  move backward 25 centimeters
  move left 20 centimeters
  move right 20 centimeters
  turn left 15 degrees
  turn right 15 degrees
  help
  quit

Notes:
  - Client must be running before commands can reach the bridge gate.
  - If FIFO is not ready yet, this console will print a warning and keep running.
============================================================
EOF

send_cmd() {
    local cmd="$1"

    if [ ! -p "$NAVILA_CONTROL_FIFO" ]; then
        echo "[manual-console] FIFO not ready: $NAVILA_CONTROL_FIFO"
        echo "[manual-console] Start client first, or wait until bridge gate creates the FIFO."
        return 1
    fi

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

print_help() {
    cat <<EOF
Commands:
  Arrow keys: ↑/↓/←/→ translate by ${STEP_CM} cm
  n / m: turn left/right by ${TURN_DEG} deg
  space / =: stop immediately and stand still
  g: go
  p: pause
  q: quit

Text commands:
  go
  pause
  stop
  =
  move forward 25 centimeters
  move backward 25 centimeters
  move left 20 centimeters
  move right 20 centimeters
  turn left 15 degrees
  turn right 15 degrees
  quit
EOF
}

handle_text_cmd() {
    local cmd="$1"
    cmd="$(echo "$cmd" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    case "$cmd" in
        "")
            return 0
            ;;
        quit|exit)
            echo "[manual-console] exit"
            exit 0
            ;;
        help|h|\?)
            print_help
            ;;
        *)
            send_cmd "$cmd" || true
            ;;
    esac
}

handle_key() {
    local key="$1"

    case "$key" in
        up)
            send_cmd "move forward ${STEP_CM} centimeters" || true
            ;;
        down)
            send_cmd "move backward ${STEP_CM} centimeters" || true
            ;;
        left)
            send_cmd "move left ${STEP_CM} centimeters" || true
            ;;
        right)
            send_cmd "move right ${STEP_CM} centimeters" || true
            ;;
        n)
            send_cmd "turn left ${TURN_DEG} degrees" || true
            ;;
        m)
            send_cmd "turn right ${TURN_DEG} degrees" || true
            ;;
        g)
            send_cmd "go" || true
            ;;
        p)
            send_cmd "pause" || true
            ;;
        stop)
            send_cmd "stop" || true
            ;;
        q)
            echo "[manual-console] exit"
            exit 0
            ;;
        h)
            print_help
            ;;
    esac
}

while true; do
    printf "navila-key> "
    IFS= read -rsn1 key || break
    echo

    case "$key" in
        $'\x1b')
            IFS= read -rsn2 -t 0.2 rest || rest=""
            case "$rest" in
                "[A") handle_key up ;;
                "[B") handle_key down ;;
                "[D") handle_key left ;;
                "[C") handle_key right ;;
                *) echo "[manual-console] unknown escape key" ;;
            esac
            ;;
        "n") handle_key n ;;
        "m") handle_key m ;;
        "g") handle_key g ;;
        "p") handle_key p ;;
        " ") handle_key stop ;;
        "=") handle_key stop ;;
        "q") handle_key q ;;
        "h") handle_key h ;;
        ":")
            read -r -p "navila> " cmd || break
            handle_text_cmd "$cmd"
            ;;
        *)
            echo "[manual-console] key not mapped: '$key'"
            echo "[manual-console] use arrows, n/m, space/=, g, p, h, q, or ':' for text command."
            ;;
    esac
done
