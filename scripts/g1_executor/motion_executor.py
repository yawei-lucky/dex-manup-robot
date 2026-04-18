#!/usr/bin/env python3
"""Holosoma-first step-1 movement executor scaffold.

Scope:
- adapter entry for vx/vy/yaw_rate
- forward/turn/stop primitives
- timeout and e-stop behavior
- front-camera-triggered stop
"""

from __future__ import annotations

import argparse
import enum
import time
from dataclasses import dataclass
from typing import Protocol


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
    backend: str
    last_reason: str = ""


class VelocityBackend(Protocol):
    """Backend contract expected by the adapter layer."""

    name: str

    def connect(self) -> None:
        ...

    def send_velocity(self, vx: float, vy: float, yaw_rate: float) -> None:
        ...

    def stop(self) -> None:
        ...

    def e_stop(self) -> None:
        ...


class HolosomaBackend:
    """Mockable Holosoma backend adapter for local validation."""

    name = "holosoma"

    def __init__(self) -> None:
        self.connected = False
        self.last_velocity = (0.0, 0.0, 0.0)

    def connect(self) -> None:
        self.connected = True

    def send_velocity(self, vx: float, vy: float, yaw_rate: float) -> None:
        if not self.connected:
            raise RuntimeError("holosoma backend not connected")
        self.last_velocity = (vx, vy, yaw_rate)

    def stop(self) -> None:
        self.send_velocity(0.0, 0.0, 0.0)

    def e_stop(self) -> None:
        self.last_velocity = (0.0, 0.0, 0.0)


class SDK2FallbackBackend(HolosomaBackend):
    """Fallback backend used only when holosoma path cannot be used."""

    name = "sdk2-fallback"


class MotionExecutor:
    def __init__(self, backend: VelocityBackend, timeout_ms: int = 500) -> None:
        self.timeout_ms = timeout_ms
        self.backend = backend
        self.connected = False
        self.state = MotionState.IDLE
        self.last_reason = ""
        self._last_command_at = self._now_ms()

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def connect(self) -> None:
        self.backend.connect()
        self.connected = True
        self.last_reason = f"connected:{self.backend.name}"

    def status(self) -> ExecutorStatus:
        return ExecutorStatus(
            connected=self.connected,
            state=self.state,
            backend=self.backend.name,
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

    def validate_velocity_semantics(self) -> dict[str, tuple[float, float, float]]:
        """Produce the six directional probes required by step-1 acceptance."""
        probes = {
            "+vx": (0.2, 0.0, 0.0),
            "-vx": (-0.2, 0.0, 0.0),
            "+vy": (0.0, 0.2, 0.0),
            "-vy": (0.0, -0.2, 0.0),
            "+yaw": (0.0, 0.0, 0.4),
            "-yaw": (0.0, 0.0, -0.4),
        }
        for cmd in probes.values():
            self.backend.send_velocity(*cmd)
        self._touch()
        self.last_reason = "velocity-semantics-probed"
        return probes

    def forward(self, duration_ms: int) -> None:
        self._require_connection()
        self.backend.send_velocity(0.2, 0.0, 0.0)
        self.state = MotionState.MOVING
        self.last_reason = f"forward:{duration_ms}"
        self._touch()

    def turn(self, direction: str, duration_ms: int) -> None:
        self._require_connection()
        if direction not in ("left", "right"):
            raise ValueError("direction must be left or right")
        yaw_rate = 0.5 if direction == "left" else -0.5
        self.backend.send_velocity(0.0, 0.0, yaw_rate)
        self.state = MotionState.TURNING
        self.last_reason = f"turn:{direction}:{duration_ms}"
        self._touch()

    def stop(self, reason: str = "manual") -> None:
        self.backend.stop()
        self.state = MotionState.STOPPED
        self.last_reason = f"stop:{reason}"
        self._touch()

    def e_stop(self, reason: str = "emergency") -> None:
        self.backend.e_stop()
        self.state = MotionState.ESTOP
        self.last_reason = f"estop:{reason}"
        self._touch()

    def on_stream_fault(self, source: str = "front_camera") -> None:
        self.stop(f"stream-fault:{source}")

    def front_camera_trigger_stop(self, signal: str) -> None:
        if signal in ("hazard", "target_reached"):
            self.stop(f"camera:{signal}")

    def _require_connection(self) -> None:
        if not self.connected:
            raise RuntimeError("executor not connected")


def make_backend(backend_name: str) -> VelocityBackend:
    if backend_name == "holosoma":
        return HolosomaBackend()
    if backend_name == "sdk2-fallback":
        return SDK2FallbackBackend()
    raise ValueError(f"unsupported backend: {backend_name}")


def run_demo(timeout_ms: int, backend_name: str) -> int:
    ex = MotionExecutor(backend=make_backend(backend_name), timeout_ms=timeout_ms)
    ex.connect()
    print("status", ex.status())

    probes = ex.validate_velocity_semantics()
    print("probes", probes)

    ex.forward(120)
    print("cmd", ex.status())

    ex.turn("left", 80)
    print("cmd", ex.status())

    ex.front_camera_trigger_stop("target_reached")
    print("camera", ex.status())

    ex.forward(100)
    time.sleep((timeout_ms + 30) / 1000)
    timed_out = ex.check_timeout()
    print("timeout", timed_out, ex.status())

    ex.on_stream_fault("front_camera")
    print("stream", ex.status())

    ex.e_stop("operator")
    print("estop", ex.status())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="run step-1 demo path")
    parser.add_argument("--timeout-ms", type=int, default=500)
    parser.add_argument(
        "--backend",
        choices=("holosoma", "sdk2-fallback"),
        default="holosoma",
        help="locomotion backend (holosoma is default; sdk2-fallback is contingency)",
    )
    args = parser.parse_args()

    if args.demo:
        return run_demo(timeout_ms=args.timeout_ms, backend_name=args.backend)

    print("Use --demo to run the movement execution sample.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
