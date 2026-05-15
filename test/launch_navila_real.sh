#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NAVILA_MODE=real \
NAVILA_NO_VLM=0 \
VLM_HOST=localhost \
VLM_PORT="${VLM_PORT:-54321}" \
HOLOSOMA_INTERFACE="${HOLOSOMA_INTERFACE:-enp4s0}" \
bash "$SCRIPT_DIR/launch_navila_closed_loop.sh"
