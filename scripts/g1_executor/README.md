# g1_executor

Holosoma-first step-1 movement executor scaffold.

## Files

- `motion_executor.py`: adapter-oriented closed-loop motion executor demo.
- `dispatcher_templates.py`: command templates and velocity semantic probes.
- `watchdog_sim.py`: tiny watchdog timeout simulation helper.

## Quick checks

```bash
python scripts/g1_executor/motion_executor.py --demo --backend holosoma --timeout-ms 200
python scripts/g1_executor/dispatcher_templates.py
python -m py_compile scripts/g1_executor/motion_executor.py scripts/g1_executor/dispatcher_templates.py scripts/g1_executor/watchdog_sim.py
```
