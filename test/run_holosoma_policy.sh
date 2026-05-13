#!/usr/bin/env bash
set -e

HOLOSOMA_ROOT="${HOLOSOMA_ROOT:-${HOME}/robotics/nav_holosoma}"
# HOLOSOMA_INTERFACE="${HOLOSOMA_INTERFACE:-lo}"
HOLOSOMA_INTERFACE="${HOLOSOMA_INTERFACE:-enp4s0}"

echo "[HOLOSOMA_POLICY] HOLOSOMA_ROOT=$HOLOSOMA_ROOT"
echo "[HOLOSOMA_POLICY] HOLOSOMA_INTERFACE=$HOLOSOMA_INTERFACE"

cd "$HOLOSOMA_ROOT"

source scripts/source_inference_setup.sh
source /opt/ros/humble/setup.bash

python3 - <<'PY'
import sys
print("[HOLOSOMA_POLICY] python:", sys.executable)
print("[HOLOSOMA_POLICY] version:", sys.version)
try:
    import rclpy
    print("[HOLOSOMA_POLICY] rclpy: ok")
except Exception as e:
    print("[HOLOSOMA_POLICY] rclpy: failed:", e)
    raise
PY

python3 src/holosoma_inference/holosoma_inference/run_policy.py inference:g1-29dof-loco \
  --task.model-path src/holosoma_inference/holosoma_inference/models/loco/g1_29dof/fastsac_g1_29dof.onnx \
  --task.velocity-input ros2 \
  --task.state-input ros2 \
  --task.interface "$HOLOSOMA_INTERFACE" \
  --secondary none