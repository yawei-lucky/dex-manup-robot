#!/usr/bin/env python3
"""Dispatcher command templates for Holosoma-first movement execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DispatchCommand:
    name: str
    payload: dict[str, Any]


def build_set_velocity(vx: float, vy: float, yaw_rate: float) -> DispatchCommand:
    return DispatchCommand("set_velocity", {"vx": vx, "vy": vy, "yaw_rate": yaw_rate})


def build_forward(duration_ms: int, speed: float = 0.2) -> DispatchCommand:
    return DispatchCommand("forward", {"duration_ms": duration_ms, "speed": speed})


def build_turn(direction: str, duration_ms: int, yaw_rate: float = 0.6) -> DispatchCommand:
    if direction not in ("left", "right"):
        raise ValueError("direction must be left or right")
    return DispatchCommand(
        "turn",
        {
            "direction": direction,
            "duration_ms": duration_ms,
            "yaw_rate": yaw_rate,
        },
    )


def build_stop(reason: str = "manual") -> DispatchCommand:
    return DispatchCommand("stop", {"reason": reason})


def build_e_stop(reason: str = "emergency") -> DispatchCommand:
    return DispatchCommand("e_stop", {"reason": reason})


def build_velocity_semantic_probe() -> list[DispatchCommand]:
    return [
        build_set_velocity(0.2, 0.0, 0.0),
        build_set_velocity(-0.2, 0.0, 0.0),
        build_set_velocity(0.0, 0.2, 0.0),
        build_set_velocity(0.0, -0.2, 0.0),
        build_set_velocity(0.0, 0.0, 0.4),
        build_set_velocity(0.0, 0.0, -0.4),
    ]


def main() -> int:
    templates = [
        *build_velocity_semantic_probe(),
        build_forward(120),
        build_turn("left", 80),
        build_stop("camera:target_reached"),
        build_e_stop("operator"),
    ]
    for cmd in templates:
        print(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
