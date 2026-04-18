#!/usr/bin/env python3
"""Step-1 movement executor scaffold.

Scope:
- connection status read
- forward/turn/stop primitives
- timeout and e-stop behavior
- front-camera-triggered stop
"""

from __future__ import annotations

import argparse
import enum
import time
from dataclasses import dataclass


class MotionState(str, enum.Enum):
    IDLE = "idle"
    MOVING = "moving"
    TURNING = "turning"
    STOPPED = "stopped"
    ESTOP = "estop"


@dataclass
class ExecutorStatus:
    connected: bool
    state: MotionState
    last_reason: str = ""


class MotionExecutor:
    def __init__(self, timeout_ms: int = 500) -> None:
        self.timeout_ms = timeout_ms
        self.connected = False
        self.state = MotionState.IDLE
        self.last_reason = ""
        self._last_command_at = self._now_ms()

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def connect(self) -> None:
        self.connected = True
        self.last_reason = "connected"

    def status(self) -> ExecutorStatus:
        return ExecutorStatus(
            connected=self.connected,
            state=self.state,
            last_reason=self.last_reason,
        )

    def _touch(self) -> None:
        self._last_command_at = self._now_ms()

    def check_timeout(self) -> bool:
        elapsed = self._now_ms() - self._last_command_at
        if elapsed > self.timeout_ms and self.state not in (MotionState.STOPPED, MotionState.ESTOP):
            self.stop("timeout")
            return True
        return False

    def forward(self, duration_ms: int) -> None:
        self._require_connection()
        self.state = MotionState.MOVING
        self.last_reason = f"forward:{duration_ms}"
        self._touch()

    def turn(self, direction: str, duration_ms: int) -> None:
        self._require_connection()
        if direction not in ("left", "right"):
            raise ValueError("direction must be left or right")
        self.state = MotionState.TURNING
        self.last_reason = f"turn:{direction}:{duration_ms}"
        self._touch()

    def stop(self, reason: str = "manual") -> None:
        self.state = MotionState.STOPPED
        self.last_reason = f"stop:{reason}"
        self._touch()

    def e_stop(self, reason: str = "emergency") -> None:
        self.state = MotionState.ESTOP
        self.last_reason = f"estop:{reason}"
        self._touch()

    def front_camera_trigger_stop(self, signal: str) -> None:
        if signal in ("hazard", "target_reached"):
            self.stop(f"camera:{signal}")

    def _require_connection(self) -> None:
        if not self.connected:
            raise RuntimeError("executor not connected")


def run_demo(timeout_ms: int) -> int:
    ex = MotionExecutor(timeout_ms=timeout_ms)
    ex.connect()
    print("status", ex.status())

    ex.forward(120)
    print("cmd", ex.status())

    ex.turn("left", 80)
    print("cmd", ex.status())

    ex.front_camera_trigger_stop("target_reached")
    print("camera", ex.status())

    # Show timeout path in demo by issuing movement then waiting past timeout.
    ex.forward(100)
    time.sleep((timeout_ms + 30) / 1000)
    timed_out = ex.check_timeout()
    print("timeout", timed_out, ex.status())

    ex.e_stop("operator")
    print("estop", ex.status())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="run step-1 demo path")
    parser.add_argument("--timeout-ms", type=int, default=500)
    args = parser.parse_args()

    if args.demo:
        return run_demo(timeout_ms=args.timeout_ms)

    print("Use --demo to run the movement execution sample.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
