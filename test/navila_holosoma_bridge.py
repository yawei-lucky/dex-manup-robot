#!/usr/bin/env python3
"""NaVILA-style mid-level action adapter for Holosoma.

This bridge converts simple text commands into ROS2 velocity/state commands for
Holosoma. Supported stdin commands include:
  move forward 25 centimeters
  move backward 25 centimeters
  move left 20 centimeters
  move right 20 centimeters
  turn left 15 degrees
  turn right 15 degrees
  stop
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
from typing import Iterable, List


class ActionType(str, Enum):
    MOVE_FORWARD = "move_forward"
    MOVE_BACKWARD = "move_backward"
    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
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
    x_error: float = 0.0
    area_ratio: float = 0.0
    within_grasp_zone: bool = False
    label: str = "target"


class NavilaTextParser:
    _MOVE_RE = re.compile(
        r"(?:move|moving)\s+"
        r"(?P<dir>forward|backward|back|left|right)\s+"
        r"(?P<val>[-+]?\d+(?:\.\d+)?)\s*"
        r"(?P<unit>m|meter|meters|cm|centimeter|centimeters)",
        re.IGNORECASE,
    )
    _TURN_RE = re.compile(
        r"turn\s+(?P<dir>left|right)\s+(?:by\s+)?"
        r"(?P<val>[-+]?\d+(?:\.\d+)?)\s*"
        r"(?P<unit>deg|degree|degrees)",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> List[MidLevelAction]:
        raw_text = text
        text_norm = text.strip().lower()
        if not text_norm:
            return []

        if text_norm in {"stop", "s", "halt"} or "stop" in text_norm:
            return [MidLevelAction(ActionType.STOP, raw_text=raw_text)]
        if "pregrasp" in text_norm or "pre-grasp" in text_norm:
            return [MidLevelAction(ActionType.PREGRASP, raw_text=raw_text)]
        if "close gripper" in text_norm or text_norm in {"grasp", "grasp now"}:
            return [MidLevelAction(ActionType.CLOSE_GRIPPER, raw_text=raw_text)]
        if "lift" in text_norm:
            return [MidLevelAction(ActionType.LIFT, raw_text=raw_text)]
        if "open gripper" in text_norm or "release" in text_norm:
            return [MidLevelAction(ActionType.OPEN_GRIPPER, raw_text=raw_text)]
        if "done" in text_norm or "finished" in text_norm:
            return [MidLevelAction(ActionType.DONE, raw_text=raw_text)]

        move_match = self._MOVE_RE.search(text_norm)
        if move_match:
            value = float(move_match.group("val"))
            unit = move_match.group("unit")
            meters = self._to_meters(value, unit)
            direction = move_match.group("dir")
            action_map = {
                "forward": ActionType.MOVE_FORWARD,
                "backward": ActionType.MOVE_BACKWARD,
                "back": ActionType.MOVE_BACKWARD,
                "left": ActionType.MOVE_LEFT,
                "right": ActionType.MOVE_RIGHT,
            }
            return [MidLevelAction(action_map[direction], value=meters, unit="m", raw_text=raw_text)]

        turn_match = self._TURN_RE.search(text_norm)
        if turn_match:
            value = float(turn_match.group("val"))
            direction = turn_match.group("dir")
            action = ActionType.TURN_LEFT if direction == "left" else ActionType.TURN_RIGHT
            return [MidLevelAction(action, value=value, unit="deg", raw_text=raw_text)]

        raise ValueError(f"Unsupported action text: {text}")

    @staticmethod
    def _to_meters(value: float, unit: str) -> float:
        unit = unit.lower()
        if unit in {"m", "meter", "meters"}:
            return value
        if unit in {"cm", "centimeter", "centimeters"}:
            return value / 100.0
        raise ValueError(f"Unsupported distance unit: {unit}")


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
    def __init__(self, align_thresh: float = 0.12, reach_area_ratio: float = 0.18) -> None:
        self.state = TaskState.SEARCH
        self.align_thresh = align_thresh
        self.reach_area_ratio = reach_area_ratio

    def step(self, obs: TargetObservation) -> List[MidLevelAction]:
        if self.state == TaskState.DONE:
            return [MidLevelAction(ActionType.DONE)]
        if self.state == TaskState.SEARCH:
            if not obs.found:
                return [MidLevelAction(ActionType.TURN_LEFT, value=18.0, unit="deg", raw_text="search left")]
            self.state = TaskState.ALIGN
        if self.state == TaskState.ALIGN:
            if not obs.found:
                self.state = TaskState.SEARCH
                return [MidLevelAction(ActionType.TURN_LEFT, value=18.0, unit="deg")]
            if abs(obs.x_error) > self.align_thresh:
                if obs.x_error < 0:
                    return [MidLevelAction(ActionType.TURN_LEFT, value=min(30.0, 60.0 * abs(obs.x_error)), unit="deg")]
                return [MidLevelAction(ActionType.TURN_RIGHT, value=min(30.0, 60.0 * abs(obs.x_error)), unit="deg")]
            self.state = TaskState.APPROACH
        if self.state == TaskState.APPROACH:
            if not obs.found:
                self.state = TaskState.SEARCH
                return [MidLevelAction(ActionType.STOP), MidLevelAction(ActionType.TURN_LEFT, value=18.0, unit="deg")]
            if abs(obs.x_error) > self.align_thresh:
                self.state = TaskState.ALIGN
                return self.step(obs)
            if obs.area_ratio < self.reach_area_ratio:
                return [MidLevelAction(ActionType.MOVE_FORWARD, value=0.60, unit="m")]
            self.state = TaskState.REACHED
        if self.state == TaskState.REACHED:
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


class BackendBase:
    def start_policy(self) -> None:
        raise NotImplementedError

    def stop_policy(self) -> None:
        raise NotImplementedError

    def walk_mode(self) -> None:
        raise NotImplementedError

    def stand_mode(self) -> None:
        raise NotImplementedError

    def init_pose(self) -> None:
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

    def init_pose(self) -> None:
        print("[dry-run] state=init")

    def send_velocity(self, vx: float, vy: float, wz: float) -> None:
        print(f"[dry-run] cmd_vel vx={vx:.3f} vy={vy:.3f} wz={wz:.3f}")

    def zero_velocity(self) -> None:
        print("[dry-run] cmd_vel vx=0 vy=0 wz=0")

    def execute_manip_action(self, action: MidLevelAction) -> None:
        print(f"[dry-run] manip action={action.action.value}")


class HolosomaRos2Backend(BackendBase):
    def __init__(self, cmd_vel_topic: str = "/cmd_vel", state_topic: str = "/holosoma/state_input") -> None:
        try:
            import rclpy
            from geometry_msgs.msg import TwistStamped
            from rclpy.node import Node
            from std_msgs.msg import String
        except Exception as exc:
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
        self._last_state_text = None

    def _publish_state(self, text: str, force: bool = False) -> None:
        if not force and text == self._last_state_text:
            return
        msg = self._String()
        msg.data = text
        self.state_pub.publish(msg)
        self._rclpy.spin_once(self.node, timeout_sec=0.01)
        self._last_state_text = text
        print(f"[ros2] state={text}")

    def start_policy(self) -> None:
        self._publish_state("start", force=True)

    def stop_policy(self) -> None:
        self._publish_state("stop", force=True)

    def walk_mode(self) -> None:
        self._publish_state("walk")

    def stand_mode(self) -> None:
        self._publish_state("stand")

    def init_pose(self) -> None:
        self._publish_state("init", force=True)

    def send_velocity(self, vx: float, vy: float, wz: float) -> None:
        msg = self._TwistStamped()
        try:
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
        self.zero_velocity()
        self.stand_mode()
        print(f"[ros2] placeholder manip action={action.action.value} (bind to arm SDK here)")


class ActionExecutor:
    def __init__(
        self,
        backend: BackendBase,
        linear_speed_mps: float = 0.45,
        angular_speed_degps: float = 60.0,
        settle_sec: float = 0.4,
        publish_hz: float = 10.0,
        bootstrap_hold_sec: float = 1.0,
    ) -> None:
        self.backend = backend
        self.linear_speed_mps = linear_speed_mps
        self.angular_speed_degps = angular_speed_degps
        self.settle_sec = settle_sec
        self.publish_hz = publish_hz
        self.bootstrap_hold_sec = bootstrap_hold_sec
        self._policy_started = False
        self._mode = None

    def bootstrap_to_stand(self) -> None:
        print("[bootstrap] init -> start -> stand")
        self.backend.init_pose()
        time.sleep(1.0)
        self.backend.start_policy()
        self._policy_started = True
        time.sleep(1.0)
        self.backend.stand_mode()
        self._mode = "stand"
        end_t = time.time() + self.bootstrap_hold_sec
        while time.time() < end_t:
            self.backend.zero_velocity()
            time.sleep(0.1)

    def ensure_started(self) -> None:
        if not self._policy_started:
            self.backend.start_policy()
            self._policy_started = True
            time.sleep(0.5)

    def ensure_walk(self) -> None:
        self.ensure_started()
        if self._mode != "walk":
            self.backend.walk_mode()
            self._mode = "walk"
            time.sleep(0.15)

    def ensure_stand(self) -> None:
        self.ensure_started()
        if self._mode != "stand":
            self.backend.stand_mode()
            self._mode = "stand"
            time.sleep(0.15)

    def hold_stand(self, duration: float | None = None) -> None:
        self.ensure_stand()
        hold = self.settle_sec if duration is None else max(0.0, duration)
        end_t = time.time() + hold
        while time.time() < end_t:
            self.backend.zero_velocity()
            time.sleep(0.1)

    def _stream_velocity(self, vx: float, vy: float, wz: float, duration: float) -> None:
        self.ensure_walk()
        dt = 1.0 / max(1e-6, self.publish_hz)
        end_t = time.time() + max(0.0, duration)
        while time.time() < end_t:
            self.backend.send_velocity(vx, vy, wz)
            time.sleep(dt)
        self.backend.zero_velocity()
        self.hold_stand(self.settle_sec)

    def run_actions(self, actions: Iterable[MidLevelAction]) -> None:
        for action in actions:
            self.run_action(action)

    def run_action(self, action: MidLevelAction) -> None:
        print(f"[exec] {action}")

        if action.action == ActionType.STOP:
            self.backend.zero_velocity()
            self.hold_stand(self.settle_sec)
            return

        if action.action in {
            ActionType.PREGRASP,
            ActionType.CLOSE_GRIPPER,
            ActionType.LIFT,
            ActionType.OPEN_GRIPPER,
            ActionType.DONE,
        }:
            self.backend.execute_manip_action(action)
            self.hold_stand(0.6)
            return

        if action.action in {ActionType.MOVE_FORWARD, ActionType.MOVE_BACKWARD}:
            distance = max(0.0, action.value)
            sign = 1.0 if action.action == ActionType.MOVE_FORWARD else -1.0
            duration = distance / max(1e-6, self.linear_speed_mps)
            self._stream_velocity(sign * self.linear_speed_mps, 0.0, 0.0, duration)
            return

        if action.action in {ActionType.MOVE_LEFT, ActionType.MOVE_RIGHT}:
            distance = max(0.0, action.value)
            sign = 1.0 if action.action == ActionType.MOVE_LEFT else -1.0
            duration = distance / max(1e-6, self.linear_speed_mps)
            self._stream_velocity(0.0, sign * self.linear_speed_mps, 0.0, duration)
            return

        if action.action in {ActionType.TURN_LEFT, ActionType.TURN_RIGHT}:
            degrees = max(0.0, action.value)
            sign = 1.0 if action.action == ActionType.TURN_LEFT else -1.0
            wz_degps = sign * self.angular_speed_degps
            wz_radps = math.radians(wz_degps)
            duration = degrees / max(1e-6, self.angular_speed_degps)
            self._stream_velocity(0.0, 0.0, wz_radps, duration)
            return

        raise ValueError(f"Unsupported action: {action.action}")


DEMO_SEQUENCE = [
    MidLevelAction(ActionType.TURN_LEFT, value=30.0, unit="deg", raw_text="turn left 30 degrees"),
    MidLevelAction(ActionType.MOVE_FORWARD, value=1.0, unit="m", raw_text="move forward 1 meter"),
    MidLevelAction(ActionType.MOVE_LEFT, value=0.2, unit="m", raw_text="move left 20 centimeters"),
    MidLevelAction(ActionType.MOVE_RIGHT, value=0.2, unit="m", raw_text="move right 20 centimeters"),
    MidLevelAction(ActionType.MOVE_BACKWARD, value=0.5, unit="m", raw_text="move backward 50 centimeters"),
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
    parser.add_argument("--linear-speed", type=float, default=0.45, help="Execution speed in m/s for translation actions")
    parser.add_argument("--angular-speed-degps", type=float, default=60.0, help="Execution angular speed in deg/s")
    parser.add_argument("--publish-hz", type=float, default=10.0, help="How often to republish cmd_vel during motion")
    parser.add_argument("--settle-sec", type=float, default=0.4, help="Stand-and-zero hold after each action")
    parser.add_argument("--bootstrap-stand", action="store_true", help="Run init->start->stand at startup")
    parser.add_argument("--skip-init", action="store_true", help="Skip initialization if robot is already prepared")
    args = parser.parse_args()

    backend = build_backend(args)
    executor = ActionExecutor(
        backend,
        linear_speed_mps=args.linear_speed,
        angular_speed_degps=args.angular_speed_degps,
        settle_sec=args.settle_sec,
        publish_hz=args.publish_hz,
    )
    text_parser = NavilaTextParser()

    if args.bootstrap_stand and not args.skip_init and not args.dry_run:
        executor.bootstrap_to_stand()

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
        print(
            "Enter commands, e.g. 'move forward 20 centimeters', "
            "'move left 20 centimeters', 'turn left 15 degrees', 'stop'. Ctrl-D to quit."
        )
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
