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

## 1. Start Holosoma in sim with ROS2 input

Use your existing working Holosoma command, but switch input sources from keyboard to ROS2.

Example pattern:

```bash
python3 src/holosoma_inference/holosoma_inference/run_policy.py inference:g1-29dof-loco \
  --task.model-path <PATH_TO_YOUR_ONNX> \
  --task.velocity-input ros2 \
  --task.state-input ros2 \
  --task.interface lo
```

`lo` is for sim-to-sim.
For real robot, replace it with your ethernet interface.

## 2. Test the adapter without ROS2

```bash
python3 navila_holosoma_bridge.py --dry-run --demo-sequence
```

Or:

```bash
python3 navila_holosoma_bridge.py --dry-run --stdin
```

Then type:

```text
turn left 15 degrees
move forward 75cm
stop
```

## 3. Test the target-approach FSM offline

```bash
python3 navila_holosoma_bridge.py --dry-run --scenario demo_target_scenario.jsonl
```

## 4. Test directly against Holosoma sim

In terminal A, run Holosoma with ROS2 input.

In terminal B:

```bash
python3 navila_holosoma_bridge.py --demo-sequence
```

Or:

```bash
python3 navila_holosoma_bridge.py --scenario demo_target_scenario.jsonl
```

## 5. First real system architecture

### Bottom layer
- **Navigation / locomotion**: Holosoma
- **Manipulation**: separate arm/hand primitive executor (later)

### Top layer
- First milestone: simple detector + FSM
- Later: NaVILA-like VLA or actual NaVILA prompt/model

### Middle interface (recommended)
Use a small structured action schema internally:

```python
MidLevelAction(action="move_forward", value=0.25, unit="m")
MidLevelAction(action="turn_left", value=12.0, unit="deg")
MidLevelAction(action="stop")
MidLevelAction(action="pregrasp")
MidLevelAction(action="close_gripper")
MidLevelAction(action="lift")
```

Do **not** send raw detector results directly into Holosoma.
Always convert them into mid-level actions first.

## 6. What to do next

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

## 7. Important note

NaVILA is a **navigation** system.
For your first real manipulation milestone, the fastest path is:

- use NaVILA-style mid-level navigation actions
- use Holosoma for locomotion
- use a separate primitive-based manipulation layer

Do **not** try to make NaVILA directly output low-level arm control as your first step.
