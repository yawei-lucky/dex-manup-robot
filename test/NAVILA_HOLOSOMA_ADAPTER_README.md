# NaVILA ↔ Holosoma middle adapter

This is the fastest practical first step for your project.

## What this adapter does

It **does not** replace Holosoma.
It converts **NaVILA-style mid-level actions** into **Holosoma ROS2 commands**.

- Top layer: detector / NaVILA-like VLA / task FSM
- Middle layer: `move forward 75cm`, `turn left 15 degrees`, `stop`, `pregrasp`, `close gripper`
- Bottom layer: Holosoma locomotion via ROS2

## Why this is the right first step

NaVILA's released VLA inference script outputs **turn / move forward / stop** style language actions.
Holosoma officially supports ROS2 input for locomotion using:
- `/cmd_vel` (`geometry_msgs/TwistStamped`)
- `/holosoma/state_input` (`std_msgs/String`)

That makes Holosoma a very clean real/sim backend for NaVILA-style middle actions.

## 1. Quick Start: Offline Testing (No Holosoma/ROS2)

**Best for rapid debugging before running full sim.**

```bash
# Dry-run demo sequence
python3 navila_holosoma_bridge.py --dry-run --demo-sequence

# Or interactive stdin mode
python3 navila_holosoma_bridge.py --dry-run --stdin
# Then type: move forward 0.5 meters, turn left 30 degrees, stop
```

## 2. Full Sim-to-Sim Workflow: MuJoCo + Holosoma Policy + Bridge

### Terminal A: Start MuJoCo environment

```bash
source scripts/source_mujoco_setup.sh
python src/holosoma/holosoma/run_sim.py robot:g1-29dof
```

Then in the MuJoCo window:
- Press `8` to lower gantry until robot touches ground
- Press `9` to remove gantry

### Terminal B: Launch Holosoma policy with ROS2 input

```bash
source scripts/source_inference_setup.sh
python3 src/holosoma_inference/holosoma_inference/run_policy.py inference:g1-29dof-loco \
  --task.model-path src/holosoma_inference/holosoma_inference/models/loco/g1_29dof/fastsac_g1_29dof.onnx \
  --task.velocity-input ros2 \
  --task.state-input ros2 \
  --task.interface lo \
  --secondary none
```

Then in policy terminal:
- Press `]` to activate the policy
- Press `=` to enter walking mode

### Terminal C: Run the NaVILA bridge

**Important: Python version**  
If running Python 3.13, switch to Python 3.10 and source ROS2 setup:
```bash
source /opt/ros/humble/setup.bash
```

**Option 1: Demo sequence with bootstrap (recommended for sim)**
```bash
python3 navila_holosoma_bridge.py --demo-sequence --bootstrap-stand
```

**Option 2: FSM-driven by observations (from JSONL file)**
```bash
python3 navila_holosoma_bridge.py --scenario demo_target_scenario.jsonl --bootstrap-stand
```

**Option 3: Interactive commands**
```bash
python3 navila_holosoma_bridge.py --stdin --bootstrap-stand
# Type: move forward 0.5 meters, turn left 15 degrees, stop
```

### Speed parameters for G1

The adapter uses fixed execution speeds (configurable):
- Linear speed: `0.45 m/s` (default) — balanced for simulation
- Angular speed: `60.0 deg/s` (default)
- Publish frequency: `10.0 Hz` (default) — maintains continuous cmd_vel streaming
- Settle time: `0.4 sec` (default) — hold standing after each action

For custom movement speeds:
```bash
python3 navila_holosoma_bridge.py --stdin --linear-speed 0.25 --angular-speed-degps 35
```

For bootstrap mode (recommended for simulation startup):
```bash
python3 navila_holosoma_bridge.py --demo-sequence --bootstrap-stand
```

Fine-tune execution timing:
```bash
python3 navila_holosoma_bridge.py --scenario demo_target_scenario.jsonl --bootstrap-stand --skip-init
```

**Note:** G1 can handle faster speeds in real sim, but start conservative for safety.

## 3. System Architecture

### Bottom layer
- **Navigation / locomotion**: Holosoma
- **Manipulation**: separate arm/hand primitive executor (later)

### Top layer
- First milestone: simple detector + FSM
- Later: NaVILA-like VLA or actual NaVILA prompt/model

### Middle interface (recommended)
Use a small structured action schema internally:

**Navigation actions:**
```python
MidLevelAction(action="move_forward", value=0.5, unit="m")
MidLevelAction(action="move_backward", value=0.25, unit="m")
MidLevelAction(action="turn_left", value=30.0, unit="deg")
MidLevelAction(action="turn_right", value=15.0, unit="deg")
MidLevelAction(action="stop")
```

**Manipulation actions:**
```python
MidLevelAction(action="pregrasp")
MidLevelAction(action="close_gripper")
MidLevelAction(action="open_gripper")
MidLevelAction(action="lift")
MidLevelAction(action="done")
```

Do **not** send raw detector results directly into Holosoma.
Always convert them into mid-level actions first.

## 4. What to do next

### Phase A: navigation only
- replace mock scenario with real detector output
- keep manipulation actions as placeholders
- validate: identify target -> approach -> stop

### Phase B: fixed grasp primitive
- bind `PREGRASP`, `CLOSE_GRIPPER`, `LIFT` to your arm/hand code
- do not train a grasp policy first
- use fixed poses / primitive motions first

### Phase C: replace rule-based top layer
- use NaVILA-like prompt + image history
- still keep the same middle interface

## 5. Important note

NaVILA is a **navigation** system.
For your first real manipulation milestone, the fastest path is:

- use NaVILA-style mid-level navigation actions
- use Holosoma for locomotion
- use a separate primitive-based manipulation layer

Do **not** try to make NaVILA directly output low-level arm control as your first step.
