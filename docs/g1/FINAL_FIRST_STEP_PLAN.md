# Final First-Step Plan (Holosoma-First Movement Execution)

## Goal

Deliver a safe and testable locomotion execution loop by treating Holosoma as the fixed walking backend, then validating only the thin adapter path.

## Hard Boundaries

1. **In scope:** walk/turn/stop closed loop and safety stop behavior.
2. **Out of scope:** grasping, arm manipulation, and complex planning.
3. **Primary backend:** Holosoma locomotion policy/control interface.
4. **Fallback backend:** SDK2 only if Holosoma cannot provide reliable stop/control entry.

## Why this changed

- Holosoma is a humanoid RL training/deployment framework (not just a tiny velocity wrapper).
- For this stage, the fastest path is **adapter validation**, not rebuilding walking from low-level SDK primitives.

## Step-1 Deliverables

1. **Adapter entry validation**
   - identify control entry that accepts `vx`, `vy`, `yaw_rate`
   - verify sign conventions for `+/-vx`, `+/-vy`, `+/-yaw_rate`
2. **Motion primitives mapped through adapter**
   - `forward(duration_ms)`
   - `turn(direction, duration_ms)`
   - `stop(reason)`
3. **Safety controls**
   - timeout watchdog -> `stop`
   - emergency stop (`e_stop`) path
   - process/stream fault -> `stop`
4. **Front camera stop trigger**
   - image thread emits `hazard` / `target_reached`
   - control thread executes immediate stop

## Week-1 Demo Definition

> See target -> approach -> stable stop

Demo pass criteria:
- adapter path is validated end-to-end (`upper-layer output -> Holosoma entry -> robot motion result`)
- stop remains reliable on timeout, e-stop, and camera-trigger conditions
- loop latency is acceptable for approach-and-stop behavior

## Stage-2 (Deferred)

- arm overlay
- teleoperation integration
- VLM-level instructions
