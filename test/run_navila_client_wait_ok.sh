#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$DEX_ROOT"

echo "[NaVILA Client] Waiting for manual start."
echo "[NaVILA Client] Type ok and press Enter to start receiving images."

while true; do
    read -r -p "Start NaVILA client? type ok: " ans
    ans="$(echo "$ans" | tr -d '[:space:]')"

    if [ "$ans" = "ok" ]; then
        break
    fi

    echo "Please type exactly: ok"
done

echo "[NaVILA Client] Starting client..."

bash test/run_navila_mujoco_client.sh