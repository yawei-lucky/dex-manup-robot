#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$DEX_ROOT"

LOG_DIR="${LOG_DIR:-${DEX_ROOT}/runtime/logs}"
INTERVAL="${VLM_VIS_INTERVAL:-3}"

# Pick newest navila_client_*.log unless caller passed an explicit path.
if [ -n "$1" ]; then
    LOG="$1"
else
    LOG="$(ls -t "$LOG_DIR"/navila_client_*.log 2>/dev/null | head -1 || true)"
fi

if [ -z "$LOG" ] || [ ! -f "$LOG" ]; then
    echo "[vis] no log found in $LOG_DIR (and none passed as \$1)"
    echo "[vis] start the closed-loop run first, then re-run this script."
    exit 1
fi

HTML="${LOG%.log}.html"

echo "[vis] log : $LOG"
echo "[vis] html: $HTML"
echo "[vis] regenerate every ${INTERVAL}s; browser auto-refreshes via <meta refresh>"

python3 test/analyze_vlm_log.py --watch --interval "$INTERVAL" "$LOG" &
WATCH_PID=$!
trap 'kill "$WATCH_PID" 2>/dev/null || true' EXIT INT TERM

# Wait briefly until the first HTML render exists, then open the browser.
for _ in $(seq 1 30); do
    if [ -s "$HTML" ]; then break; fi
    sleep 0.2
done

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$HTML" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    open "$HTML" >/dev/null 2>&1 &
else
    echo "[vis] no browser opener found; open $HTML manually"
fi

wait "$WATCH_PID"
