#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$DEX_ROOT"

source /opt/ros/humble/setup.bash

exec /usr/bin/python3 test/navila_holosoma_bridge.py \
  --stdin \
  --cmd-vel-topic "${CMD_VEL_TOPIC:-/cmd_vel}" \
  --state-topic "${STATE_TOPIC:-/holosoma/state_input}" \
  --linear-speed "${NAVILA_LINEAR_SPEED:-0.45}" \
  --angular-speed-degps "${NAVILA_ANGULAR_SPEED_DEGPS:-60.0}" \
  --publish-hz "${NAVILA_PUBLISH_HZ:-10.0}" \
  --settle-sec "${NAVILA_SETTLE_SEC:-0.4}"