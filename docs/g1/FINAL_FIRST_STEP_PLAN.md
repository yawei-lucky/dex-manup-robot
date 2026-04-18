# Final First-Step Plan (Movement Execution Only)

## Goal

Deliver a reliable movement execution baseline focusing on safe locomotion control and stop behavior.

## Hard Boundaries

1. **In scope:** walk/turn/stop closed loop.
2. **Out of scope:** grasping, arm manipulation, and complex planning.
3. **Primary stack:** SDK2 Python.
4. **Backend policy:** `holosoma` remains compatible as a replaceable low-level backend.

## Step-1 Deliverables

1. **Connectivity & state readout**
   - establish connection status checks
   - expose health/state snapshot
2. **Motion primitives**
   - `forward(duration_ms)`
   - `turn(direction, duration_ms)`
   - `stop(reason)`
3. **Safety controls**
   - timeout watchdog
   - emergency stop (`e_stop`) path
4. **Front camera stop trigger**
   - detect hazard/target condition from front camera signal
   - trigger immediate stop

## Week-1 Demo Definition

> See target -> approach -> stable stop

Demo pass criteria:
- target event can be injected/simulated
- executor transitions to approach mode
- stop is reached without drift commands after stop

## Stage-2 (Deferred)

- arm overlay
- teleoperation integration
- VLM-level instructions
