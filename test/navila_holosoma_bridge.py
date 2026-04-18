#!/usr/bin/env python3
"""NaVILA-style mid-level action adapter for Holosoma.

This script gives you a thin middle layer between:
  - top layer: NaVILA-style textual actions or a simple task FSM
  - bottom layer: Holosoma locomotion running with ROS2 input

Holosoma side expected configuration (from official README):
  --task.velocity-input ros2
  --task.state-input ros2
  --task.interface lo          # for sim-to-sim
or
  --task.interface <eth iface> # for real robot

Published topics:
  /cmd_vel                  geometry_msgs/msg/TwistStamped
  /holosoma/state_input     std_msgs/msg/String

State commands:
  start, stop, walk, stand, init

This file supports three workflows:
1) Parse NaVILA-style text and execute it:
      python navila_holosoma_bridge.py --stdin
2) Run a fixed demo sequence against Holosoma:
      python navila_holosoma_bridge.py --demo-sequence
3) Test a simple target-approach FSM from JSONL observations:
      python navila_holosoma_bridge.py --scenario demo.jsonl

For offline testing without ROS2 / Holosoma, add --dry-run.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional


# -----------------------------
# Mid-level action definitions
# -----------------------------

class ActionType(str, Enum):
    MOVE_FORWARD = "move_forward"
    MOVE_BACKWARD = "move_backward"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    STOP = "stop"
    PREGRASP = "pregrasp"
    CLOSE_GRIPPER = "close_gripper"
    LIFT = "lift"
    OPEN_GRIPPER = "open_gripper"
    DONE = "done"


@dataclass
class MidLevelAction:
    action: ActionType
    value: float = 0.0
    unit: str = ""
    raw_text: str = ""


@dataclass
class TargetObservation:
    found: bool
    x_error: float = 0.0          # normalized horizontal error, left:-1 ~ right:+1
    area_ratio: float = 0.0       # bbox area / image area
    within_grasp_zone: bool = False
    label: str = "target"


# -----------------------------
# NaVILA-style text parser
# -----------------------------

class NavilaTextParser:
    """Parse NaVILA-like natural language actions into structured commands.

    Supported examples:
      - moving forward 75cm
      - move forward 0.8 meters
      - turn left 15 degrees
      - turn right 30 degree
      - stop
      - pregrasp
      - close gripper
      - lift arm
    """

    _DIST_RE = re.compile(
        r"(?P<dir>move|moving)\s+(?P<fb>forward|backward)\s+(?P<val>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>m|meter|meters|cm|centimeter|centimeters)",
        re.IGNORECASE,
    )
    _TURN_RE = re.compile(
        r"turn\s+(?P<dir>left|right)\s+(?:by\s+)?(?P<val>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>deg|degree|degrees)",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> List[MidLevelAction]:
        text_norm = text.strip().lower()
        if not text_norm:
            return []

        if "stop" in text_norm:
            return [MidLevelAction(ActionType.STOP, raw_text=text)]
        if "pregrasp" in text_norm or "pre-grasp" in text_norm:
            return [MidLevelAction(ActionType.PREGRASP, raw_text=text)]
        if "close gripper" in text_norm or "grasp" == text_norm or "grasp now" in text_norm:
            return [MidLevelAction(ActionType.CLOSE_GRIPPER, raw_text=text)]
        if "lift" in text_norm:
            return [MidLevelAction(ActionType.LIFT, raw_text=text)]
        if "open gripper" in text_norm or "release" in text_norm:
            return [MidLevelAction(ActionType.OPEN_GRIPPER, raw_text=text)]
        if "done" in text_norm or "finished" in text_norm:
            return [MidLevelAction(ActionType.DONE, raw_text=text)]

        dist_match = self._DIST_RE.search(text_norm)
        if dist_match:
            val = float(dist_match.group("val"))
            unit = dist_match.group("unit")
            meters = self._to_meters(val, unit)
            fb = dist_match.group("fb")
            action = ActionType.MOVE_FORWARD if fb == "forward" else ActionType.MOVE_BACKWARD
            return [MidLevelAction(action, value=meters, unit="m", raw_text=text)]

        turn_match = self._TURN_RE.search(text_norm)
        if turn_match:
            val = float(turn_match.group("val"))
            direction = turn_match.group("dir")
            action = ActionType.TURN_LEFT if direction == "left" else ActionType.TURN_RIGHT
            return [MidLevelAction(action, value=val, unit="deg", raw_text=text)]

        raise ValueError(f"Unsupported action text: {text}")

    @staticmethod
    def _to_meters(value: float, unit: str) -> float:
        unit = unit.lower()
        if unit in {"m", "meter", "meters"}:
            return value
        if unit in {"cm", "centimeter", "centimeters"}:
            return value / 100.0
        raise ValueError(f"Unsupported distance unit: {unit}")


# -----------------------------
# Simple task FSM for target approach
# -----------------------------

class TaskState(str, Enum):
    SEARCH = "search"
    ALIGN = "align"
    APPROACH = "approach"
    REACHED = "reached"
    PREGRASP = "pregrasp"
    GRASP = "grasp"
    LIFT = "lift"
    DONE = "done"


class SimpleTargetFSM:
    """A deliberately simple first-step FSM.

    Goal:
      identify target -> approach -> stop -> pregrasp -> grasp -> lift

    This is *not* a learned manipulation policy. It is the fastest practical
    decomposition to validate the system integration.
    """

    def __init__(
        self,
        align_thresh: float = 0.12,
        reach_area_ratio: float = 0.18,
    ) -> None:
        self.state = TaskState.SEARCH
        self.align_thresh = align_thresh
        self.reach_area_ratio = reach_area_ratio

    def step(self, obs: TargetObservation) -> List[MidLevelAction]:
        if self.state == TaskState.DONE:
            return [MidLevelAction(ActionType.DONE)]

        if self.state == TaskState.SEARCH:
            if not obs.found:
                return [MidLevelAction(ActionType.TURN_LEFT, value=12.0, unit="deg", raw_text="search left")]
            self.state = TaskState.ALIGN

        if self.state == TaskState.ALIGN:
            if not obs.found:
                self.state = TaskState.SEARCH
                return [MidLevelAction(ActionType.TURN_LEFT, value=12.0, unit="deg")]
            if abs(obs.x_error) > self.align_thresh:
                if obs.x_error < 0:
                    return [MidLevelAction(ActionType.TURN_LEFT, value=min(18.0, 60.0 * abs(obs.x_error)), unit="deg")]
                return [MidLevelAction(ActionType.TURN_RIGHT, value=min(18.0, 60.0 * abs(obs.x_error)), unit="deg")]
            self.state = TaskState.APPROACH

        if self.state == TaskState.APPROACH:
            if not obs.found:
                self.state = TaskState.SEARCH
                return [MidLevelAction(ActionType.STOP), MidLevelAction(ActionType.TURN_LEFT, value=12.0, unit="deg")]
            if abs(obs.x_error) > self.align_thresh:
                self.state = TaskState.ALIGN
                return self.step(obs)
            if obs.area_ratio < self.reach_area_ratio:
                # Move in short chunks for safety and re-evaluate.
                return [MidLevelAction(ActionType.MOVE_FORWARD, value=0.25, unit="m")]
            self.state = TaskState.REACHED

        if self.state == TaskState.REACHED:
            if obs.within_grasp_zone:
                self.state = TaskState.PREGRASP
                return [MidLevelAction(ActionType.STOP)]
            # Conservative fallback: stop anyway when close enough.
            self.state = TaskState.PREGRASP
            return [MidLevelAction(ActionType.STOP)]

        if self.state == TaskState.PREGRASP:
            self.state = TaskState.GRASP
            return [MidLevelAction(ActionType.PREGRASP)]

        if self.state == TaskState.GRASP:
            self.state = TaskState.LIFT
            return [MidLevelAction(ActionType.CLOSE_GRIPPER)]

        if self.state == TaskState.LIFT:
            self.state = TaskState.DONE
            return [MidLevelAction(ActionType.LIFT)]

        return [MidLevelAction(ActionType.STOP)]


# -----------------------------
# Backends
# -----------------------------

class BackendBase:
    def start_policy(self) -> None:
        raise NotImplementedError

    def stop_policy(self) -> None:
        raise NotImplementedError

    def walk_mode(self) -> None:
        raise NotImplementedError

    def stand_mode(self) -> None:
        raise NotImplementedError

    def send_velocity(self, vx: float, vy: float, wz: float) -> None:
        raise NotImplementedError

    def zero_velocity(self) -> None:
        raise NotImplementedError

    def execute_manip_action(self, action: MidLevelAction) -> None:
        raise NotImplementedError


class DryRunBackend(BackendBase):
    def start_policy(self) -> None:
        print("[dry-run] state=start")

    def stop_policy(self) -> None:
        print("[dry-run] state=stop")

    def walk_mode(self) -> None:
        print("[dry-run] state=walk")

    def stand_mode(self) -> None:
        print("[dry-run] state=stand")

    def send_velocity(self, vx: float, vy: float, wz: float) -> None:
        print(f"[dry-run] cmd_vel vx={vx:.3f} vy={vy:.3f} wz={wz:.3f}")

    def zero_velocity(self) -> None:
        print("[dry-run] cmd_vel vx=0 vy=0 wz=0")

    def execute_manip_action(self, action: MidLevelAction) -> None:
        print(f"[dry-run] manip action={action.action.value}")


class HolosomaRos2Backend(BackendBase):
    """ROS2 backend using the official Holosoma topics.

    Holosoma README documents:
      - /cmd_vel as geometry_msgs/TwistStamped
      - /holosoma/state_input as std_msgs/String
      - commands: walk, stand, start, stop, init
    """

    def __init__(self, cmd_vel_topic: str = "/cmd_vel", state_topic: str = "/holosoma/state_input") -> None:
        try:
            import rclpy
            from geometry_msgs.msg import TwistStamped
            from rclpy.node import Node
            from std_msgs.msg import String
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "ROS2 backend requested but rclpy / geometry_msgs / std_msgs is unavailable. "
                "Use --dry-run or source your ROS2 environment first."
            ) from exc

        self._rclpy = rclpy
        self._TwistStamped = TwistStamped
        self._String = String

        if not self._rclpy.ok():
            self._rclpy.init(args=None)
        self.node = Node("navila_holosoma_bridge")
        self.cmd_pub = self.node.create_publisher(TwistStamped, cmd_vel_topic, 10)
        self.state_pub = self.node.create_publisher(String, state_topic, 10)

    def _publish_state(self, text: str) -> None:
        msg = self._String()
        msg.data = text
        self.state_pub.publish(msg)
        self._rclpy.spin_once(self.node, timeout_sec=0.01)
        print(f"[ros2] state={text}")

    def start_policy(self) -> None:
        self._publish_state("start")

    def stop_policy(self) -> None:
        self._publish_state("stop")

    def walk_mode(self) -> None:
        self._publish_state("walk")

    def stand_mode(self) -> None:
        self._publish_state("stand")

    def init_pose(self) -> None:
        self._publish_state("init")

    def send_velocity(self, vx: float, vy: float, wz: float) -> None:
        msg = self._TwistStamped()
        try:
            # Works on standard ROS2 geometry_msgs/TwistStamped.
            msg.header.stamp = self.node.get_clock().now().to_msg()
            msg.header.frame_id = "base_link"
        except Exception:
            pass
        msg.twist.linear.x = float(max(-1.0, min(1.0, vx)))
        msg.twist.linear.y = float(max(-1.0, min(1.0, vy)))
        msg.twist.angular.z = float(max(-1.0, min(1.0, wz)))
        self.cmd_pub.publish(msg)
        self._rclpy.spin_once(self.node, timeout_sec=0.01)
        print(f"[ros2] cmd_vel vx={msg.twist.linear.x:.3f} vy={msg.twist.linear.y:.3f} wz={msg.twist.angular.z:.3f}")

    def zero_velocity(self) -> None:
        self.send_velocity(0.0, 0.0, 0.0)

    def execute_manip_action(self, action: MidLevelAction) -> None:
        # Placeholder by design: manipulation should be bound to your arm/hand executor.
        self.zero_velocity()
        print(f"[ros2] placeholder manip action={action.action.value} (bind to arm SDK here)")


# -----------------------------
# Executor
# -----------------------------

class ActionExecutor:
    def __init__(
        self,
        backend: BackendBase,
        linear_speed_mps: float = 0.25,
        angular_speed_degps: float = 35.0,
        settle_sec: float = 0.2,
    ) -> None:
        self.backend = backend
        self.linear_speed_mps = linear_speed_mps
        self.angular_speed_degps = angular_speed_degps
        self.settle_sec = settle_sec

    def run_actions(self, actions: Iterable[MidLevelAction]) -> None:
        for action in actions:
            self.run_action(action)

    def run_action(self, action: MidLevelAction) -> None:
        print(f"[exec] {action}")
        if action.action == ActionType.STOP:
            self.backend.zero_velocity()
            self.backend.stand_mode()
            return

        if action.action in {ActionType.PREGRASP, ActionType.CLOSE_GRIPPER, ActionType.LIFT, ActionType.OPEN_GRIPPER, ActionType.DONE}:
            self.backend.execute_manip_action(action)
            return

        self.backend.start_policy()
        self.backend.walk_mode()

        if action.action in {ActionType.MOVE_FORWARD, ActionType.MOVE_BACKWARD}:
            distance = max(0.0, action.value)
            sign = 1.0 if action.action == ActionType.MOVE_FORWARD else -1.0
            duration = distance / max(1e-6, self.linear_speed_mps)
            self.backend.send_velocity(sign * self.linear_speed_mps, 0.0, 0.0)
            time.sleep(duration)
            self.backend.zero_velocity()
            time.sleep(self.settle_sec)
            return

        if action.action in {ActionType.TURN_LEFT, ActionType.TURN_RIGHT}:
            degrees = max(0.0, action.value)
            sign = 1.0 if action.action == ActionType.TURN_LEFT else -1.0
            wz_degps = sign * self.angular_speed_degps
            wz_radps = math.radians(wz_degps)
            duration = degrees / max(1e-6, self.angular_speed_degps)
            self.backend.send_velocity(0.0, 0.0, wz_radps)
            time.sleep(duration)
            self.backend.zero_velocity()
            time.sleep(self.settle_sec)
            return

        raise ValueError(f"Unsupported action: {action.action}")


# -----------------------------
# CLI helpers
# -----------------------------

DEMO_SEQUENCE = [
    MidLevelAction(ActionType.TURN_LEFT, value=15.0, unit="deg", raw_text="turn left 15 degrees"),
    MidLevelAction(ActionType.MOVE_FORWARD, value=0.8, unit="m", raw_text="move forward 0.8 meters"),
    MidLevelAction(ActionType.TURN_RIGHT, value=10.0, unit="deg", raw_text="turn right 10 degrees"),
    MidLevelAction(ActionType.MOVE_FORWARD, value=0.5, unit="m", raw_text="move forward 0.5 meters"),
    MidLevelAction(ActionType.STOP, raw_text="stop"),
]


def load_scenario(path: Path) -> List[TargetObservation]:
    obs_list: List[TargetObservation] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            data = json.loads(line)
            obs_list.append(TargetObservation(**data))
    return obs_list


def build_backend(args: argparse.Namespace) -> BackendBase:
    if args.dry_run:
        return DryRunBackend()
    return HolosomaRos2Backend(cmd_vel_topic=args.cmd_vel_topic, state_topic=args.state_topic)


def main() -> int:
    parser = argparse.ArgumentParser(description="NaVILA-style middle adapter for Holosoma")
    parser.add_argument("--dry-run", action="store_true", help="Print commands instead of publishing ROS2 topics")
    parser.add_argument("--stdin", action="store_true", help="Read one NaVILA-style text command per line from stdin")
    parser.add_argument("--demo-sequence", action="store_true", help="Execute a fixed demo action sequence")
    parser.add_argument("--scenario", type=Path, default=None, help="JSONL target-observation scenario for FSM testing")
    parser.add_argument("--cmd-vel-topic", type=str, default="/cmd_vel")
    parser.add_argument("--state-topic", type=str, default="/holosoma/state_input")
    parser.add_argument("--linear-speed", type=float, default=0.25, help="Execution speed in m/s for distance actions")
    parser.add_argument("--angular-speed-degps", type=float, default=35.0, help="Execution angular speed in deg/s")
    args = parser.parse_args()

    backend = build_backend(args)
    executor = ActionExecutor(backend, linear_speed_mps=args.linear_speed, angular_speed_degps=args.angular_speed_degps)
    text_parser = NavilaTextParser()

    if args.demo_sequence:
        executor.run_actions(DEMO_SEQUENCE)
        return 0

    if args.scenario is not None:
        fsm = SimpleTargetFSM()
        for obs in load_scenario(args.scenario):
            actions = fsm.step(obs)
            print(f"[fsm] state={fsm.state} obs={obs} -> actions={actions}")
            executor.run_actions(actions)
        return 0

    if args.stdin:
        print("Enter NaVILA-style commands, e.g. 'move forward 75cm', 'turn left 15 degrees', 'stop'. Ctrl-D to quit.")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            actions = text_parser.parse(line)
            executor.run_actions(actions)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
