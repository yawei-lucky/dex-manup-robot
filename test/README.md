# NaVILA ↔ Holosoma Adapter

Converts NaVILA-style mid-level navigation actions into Holosoma ROS2 commands.

- Top layer: VLM / NaVILA policy (optional)
- Middle layer: `move forward 75cm`, `turn left 15 degrees`, `stop`
- Bottom layer: Holosoma locomotion via `/cmd_vel` + `/holosoma/state_input`

---

## Quick Start: One-Key Closed-Loop Sim

Launches a 4-pane Terminator layout: MuJoCo camera stream, Holosoma policy, NaVILA client + bridge, manual control console.

```bash
# Default: no VLM, manual keyboard control only
bash test/launch_navila_closed_loop.sh

# With VLM inference enabled
1: start the NaVILA VLM server

conda activate navila-server
cd ~/NaVILA-Bench

python scripts/vlm_server.py \
  --model_path ~/models/navila-llama3-8b-8f \
  --port 54321

2: NAVILA_NO_VLM=0 VLM_HOST=<server-ip> VLM_PORT=54321 bash test/launch_navila_closed_loop.sh

# Real robot (no MuJoCo stream, slower speeds, real network interface)
NAVILA_MODE=real HOLOSOMA_INTERFACE=enp4s0 bash test/launch_navila_closed_loop.sh

# Real robot + VLM (first start the vlm server as in sim)
NAVILA_MODE=real HOLOSOMA_INTERFACE=enp4s0 NAVILA_NO_VLM=0 VLM_HOST=<ip> bash test/launch_navila_closed_loop.sh
```

Key environment variables:

| Variable | Default | Description |
|---|---|---|
| `NAVILA_MODE` | `sim` | `sim` or `real` |
| `NAVILA_NO_VLM` | `1` | `1` = skip VLM inference, manual only |
| `VLM_HOST` / `VLM_PORT` | `100.110.59.37` / `54321` | VLM server address |
| `HOLOSOMA_INTERFACE` | `lo` (sim) / `enp4s0` (real) | ROS2 network interface |
| `NAVILA_NO_INIT_POSE` | `0` | `1` = skip init_pose on bridge restart (prevents collapse when robot is already standing) |

---

## Standalone: Policy + Bridge Keyboard Test

Use this to verify robot locomotion before running the full closed-loop pipeline.

```bash
# Terminal A: start Holosoma policy
HOLOSOMA_INTERFACE=lo bash test/run_holosoma_policy.sh      # sim
HOLOSOMA_INTERFACE=enp4s0 bash test/run_holosoma_policy.sh  # real robot

# Terminal B: start bridge with keyboard stdin
source /opt/ros/humble/setup.bash
python3 test/navila_holosoma_bridge.py --stdin --bootstrap-stand

# Then type commands:
# move forward 50 centimeters
# turn left 15 degrees
# stop
```

---

## System Architecture

```
navila_stream_client.py          ← reads images, optionally calls VLM
        │
navila_bridge_gate.py            ← gates VLM forwarding (go/pause), manages FIFO
        │
navila_holosoma_bridge.py        ← translates actions → ROS2 /cmd_vel + state_input
        │
Holosoma policy node             ← locomotion control
        │
Robot (MuJoCo sim or real G1)
```

Bootstrap sequence on bridge start (`--bootstrap-stand`):
1. `init_pose` — reset to initial pose (skipped with `NAVILA_NO_INIT_POSE=1`)
2. `start_policy` — activate Holosoma policy
3. `stand_mode` — command robot to stand

---

## One-Time Setup

### Allow `ufw status` without password

The Holosoma policy startup script calls `sudo ufw status` to check firewall state. Run this once to avoid the password prompt every time:

```bash
echo "kylin ALL=(ALL) NOPASSWD: /usr/sbin/ufw status" | sudo tee /etc/sudoers.d/kylin-ufw-status
```

Run in any terminal. Requires your password once. After that, policy startup is fully automatic.

---

## Motion Parameters

All parameters are set via environment variables before launching the client or standalone bridge.

### Keyboard step size (manual console)

| Variable | Default | Description |
|---|---|---|
| `NAVILA_MANUAL_STEP_CM` | `20` | Distance per arrow key press (cm) |
| `NAVILA_MANUAL_TURN_DEG` | `15` | Angle per 1/0 key press (degrees) |

```bash
# Example: larger steps
NAVILA_MANUAL_STEP_CM=50 NAVILA_MANUAL_TURN_DEG=30 bash test/launch_navila_closed_loop.sh
```

### Bridge speed and timing

| Variable | Sim default | Real default | Description |
|---|---|---|---|
| `NAVILA_LINEAR_SPEED` | `0.45` | `0.20` | Linear speed (m/s) |
| `NAVILA_ANGULAR_SPEED_DEGPS` | `60.0` | `30.0` | Angular speed (deg/s) |
| `NAVILA_PUBLISH_HZ` | `10.0` | `10.0` | cmd_vel publish rate (Hz) |
| `NAVILA_SETTLE_SEC` | `0.4` | `0.4` | Pause after motion before next command (s) |

```bash
# Example: slower real robot
NAVILA_MODE=real HOLOSOMA_INTERFACE=enp4s0 \
  NAVILA_LINEAR_SPEED=0.15 NAVILA_ANGULAR_SPEED_DEGPS=20 \
  bash test/launch_navila_closed_loop.sh
```

Step distance and duration are computed from speed:

```
duration = distance_m / linear_speed        # e.g. 50cm / 0.45m/s = 1.11s
duration = angle_deg / angular_speed_degps  # e.g. 30deg / 60deg/s = 0.5s
```
