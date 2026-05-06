#!/usr/bin/env bash
set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$DEX_ROOT"

source /opt/ros/humble/setup.bash

EXTRA_ARGS=("$@")
WAIT_FOR_SUBSCRIBERS_ARGS=()
if [ "${NAVILA_WAIT_FOR_SUBSCRIBERS:-1}" = "1" ]; then
  WAIT_FOR_SUBSCRIBERS_ARGS=(
    --wait-for-subscribers
    --subscriber-wait-timeout "${NAVILA_SUBSCRIBER_WAIT_TIMEOUT:-30.0}"
  )
fi

# Keep bridge logs readable in the client pane:
# - print every non-cmd_vel line
# - print only the first cmd_vel line of each continuous cmd_vel block
# This does not change ROS2 publishing; it only filters terminal/log output.
exec /usr/bin/python3 test/navila_holosoma_bridge.py \
  --stdin \
  --cmd-vel-topic "${CMD_VEL_TOPIC:-/cmd_vel}" \
  --state-topic "${STATE_TOPIC:-/holosoma/state_input}" \
  --linear-speed "${NAVILA_LINEAR_SPEED:-0.45}" \
  --angular-speed-degps "${NAVILA_ANGULAR_SPEED_DEGPS:-60.0}" \
  --publish-hz "${NAVILA_PUBLISH_HZ:-10.0}" \
  --settle-sec "${NAVILA_SETTLE_SEC:-0.4}" \
  "${WAIT_FOR_SUBSCRIBERS_ARGS[@]}" \
  "${EXTRA_ARGS[@]}" \
  2>&1 | awk '
    /\[ros2\] cmd_vel/ {
      if (!in_cmd_vel_block) {
        print;
        fflush();
        in_cmd_vel_block = 1;
      }
      next;
    }
    {
      in_cmd_vel_block = 0;
      print;
      fflush();
    }
  '
# /usr/bin/python3 test/navila_holosoma_bridge.py --stdin --bootstrap-stand
