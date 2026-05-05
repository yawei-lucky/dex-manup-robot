#!/usr/bin/env python3
"""Preemptible NaVILA-style mid-level action adapter for Holosoma.

This bridge converts simple text commands into ROS2 velocity/state commands for
Holosoma. It is intentionally preemptible: when a new command arrives on stdin,
the currently executing motion is interrupted and the newest command takes over.

Supported stdin commands include:
  move forward 25 centimeters
  move backward 25 centimeters
  move left 20 centimeters
  move right 20 centimeters
  turn left 15 degrees
  turn right 15 degrees
  stop
  =
"""

from __future__ import annotations

import argparse
import math
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional


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

        if text_norm in {"stop", "s", "halt", "="} or "stop" in text_norm:
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
        print("[dry-run] state=start", flush=True)

    def stop_policy(self) -> None:
        print("[dry-run] state=stop", flush=True)

    def walk_mode(self) -> None:
        print("[dry-run] state=walk", flush=True)

    def stand_mode(self) -> None:
        print("[dry-run] state=stand", flush=True)

    def init_pose(self) -> None:
        print("[dry-run] state=init", flush=True)

    def send_velocity(self, vx: float, vy: float, wz: float) -> None:
        print(f"[dry-run] cmd_vel vx={vx:.3f} vy={vy:.3f} wz={wz:.3f}", flush=True)

    def zero_velocity(self) -> None:
        print("[dry-run] cmd_vel vx=0 vy=0 wz=0", flush=True)

    def execute_manip_action(self, action: MidLevelAction) -> None:
        print(f"[dry-run] manip action={action.action.value}", flush=True)


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
        self._pub_lock = threading.Lock()

        if not self._rclpy.ok():
            self._rclpy.init(args=None)
        self.node = Node("navila_holosoma_bridge")
        self.cmd_pub = self.node.create_publisher(TwistStamped, cmd_vel_topic, 10)
        self.state_pub = self.node.create_publisher(String, state_topic, 10)
        self._last_state_text = None

    def _publish_state(self, text: str, force: bool = False) -> None:
        with self._pub_lock:
            if not force and text == self._last_state_text:
                return
            msg = self._String()
            msg.data = text
            self.state_pub.publish(msg)
            self._rclpy.spin_once(self.node, timeout_sec=0.01)
            self._last_state_text = text
            print(f"[ros2] state={text}", flush=True)

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
        with self._pub_lock:
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
            print(f"[ros2] cmd_vel vx={msg.twist.linear.x:.3f} vy={msg.twist.linear.y:.3f} wz={msg.twist.angular.z:.3f}", flush=True)

    def zero_velocity(self) -> None:
        self.send_velocity(0.0, 0.0, 0.0)

    def execute_manip_action(self, action: MidLevelAction) -> None:
        self.zero_velocity()
        self.stand_mode()
        print(f"[ros2] placeholder manip action={action.action.value} (bind to arm SDK here)", flush=True)


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
        self._mode_lock = threading.Lock()

    def bootstrap_to_stand(self) -> None:
        print("[bootstrap] init -> start -> stand", flush=True)
        self.backend.init_pose()
        time.sleep(1.0)
        self.backend.start_policy()
        with self._mode_lock:
            self._policy_started = True
        time.sleep(1.0)
        self.backend.stand_mode()
        with self._mode_lock:
            self._mode = "stand"
        end_t = time.time() + self.bootstrap_hold_sec
        while time.time() < end_t:
            self.backend.zero_velocity()
            time.sleep(0.1)

    def ensure_started(self) -> None:
        with self._mode_lock:
            need_start = not self._policy_started
            if need_start:
                self._policy_started = True
        if need_start:
            self.backend.start_policy()
            time.sleep(0.3)

    def ensure_walk(self) -> None:
        self.ensure_started()
        with self._mode_lock:
            need_walk = self._mode != "walk"
            if need_walk:
                self._mode = "walk"
        if need_walk:
            self.backend.walk_mode()
            time.sleep(0.10)

    def ensure_stand(self) -> None:
        self.ensure_started()
        with self._mode_lock:
            need_stand = self._mode != "stand"
            if need_stand:
                self._mode = "stand"
        if need_stand:
            self.backend.stand_mode()
            time.sleep(0.10)

    def immediate_stop(self) -> None:
        print("[exec] immediate stop", flush=True)
        self.ensure_started()
        self.backend.zero_velocity()
        self.ensure_stand()
        self.backend.zero_velocity()

    def hold_stand(self, duration: float | None = None, cancel_event: Optional[threading.Event] = None) -> None:
        self.ensure_stand()
        hold = self.settle_sec if duration is None else max(0.0, duration)
        end_t = time.time() + hold
        while time.time() < end_t:
            if cancel_event is not None and cancel_event.is_set():
                return
            self.backend.zero_velocity()
            time.sleep(0.05)

    def _stream_velocity(self, vx: float, vy: float, wz: float, duration: float, cancel_event: threading.Event) -> None:
        self.ensure_walk()
        dt = 1.0 / max(1e-6, self.publish_hz)
        end_t = time.time() + max(0.0, duration)
        while time.time() < end_t:
            if cancel_event.is_set():
                print("[exec] motion interrupted", flush=True)
                break
            self.backend.send_velocity(vx, vy, wz)
            time.sleep(dt)
        self.backend.zero_velocity()
        if not cancel_event.is_set():
            self.hold_stand(self.settle_sec, cancel_event=cancel_event)

    def run_actions(self, actions: Iterable[MidLevelAction], cancel_event: threading.Event) -> None:
        for action in actions:
            if cancel_event.is_set():
                break
            self.run_action(action, cancel_event)

    def run_action(self, action: MidLevelAction, cancel_event: threading.Event) -> None:
        print(f"[exec] {action}", flush=True)

        if action.action == ActionType.STOP:
            self.immediate_stop()
            return

        if action.action in {
            ActionType.PREGRASP,
            ActionType.CLOSE_GRIPPER,
            ActionType.LIFT,
            ActionType.OPEN_GRIPPER,
            ActionType.DONE,
        }:
            self.backend.execute_manip_action(action)
            self.hold_stand(0.6, cancel_event=cancel_event)
            return

        if action.action in {ActionType.MOVE_FORWARD, ActionType.MOVE_BACKWARD}:
            distance = max(0.0, action.value)
            sign = 1.0 if action.action == ActionType.MOVE_FORWARD else -1.0
            duration = distance / max(1e-6, self.linear_speed_mps)
            self._stream_velocity(sign * self.linear_speed_mps, 0.0, 0.0, duration, cancel_event)
            return

        if action.action in {ActionType.MOVE_LEFT, ActionType.MOVE_RIGHT}:
            distance = max(0.0, action.value)
            sign = 1.0 if action.action == ActionType.MOVE_LEFT else -1.0
            duration = distance / max(1e-6, self.linear_speed_mps)
            self._stream_velocity(0.0, sign * self.linear_speed_mps, 0.0, duration, cancel_event)
            return

        if action.action in {ActionType.TURN_LEFT, ActionType.TURN_RIGHT}:
            degrees = max(0.0, action.value)
            sign = 1.0 if action.action == ActionType.TURN_LEFT else -1.0
            wz_radps = math.radians(sign * self.angular_speed_degps)
            duration = degrees / max(1e-6, self.angular_speed_degps)
            self._stream_velocity(0.0, 0.0, wz_radps, duration, cancel_event)
            return

        raise ValueError(f"Unsupported action: {action.action}")


class PreemptiveActionRunner:
    def __init__(self, executor: ActionExecutor) -> None:
        self.executor = executor
        self._cond = threading.Condition()
        self._latest_actions: Optional[List[MidLevelAction]] = None
        self._latest_raw = ""
        self._cancel_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def submit(self, actions: List[MidLevelAction], raw_text: str) -> None:
        if not actions:
            return
        with self._cond:
            self._cancel_event.set()
            self._latest_actions = actions
            self._latest_raw = raw_text
            self._cond.notify()
        if any(a.action == ActionType.STOP for a in actions):
            # Do not wait for worker loop; publish stop immediately from stdin thread.
            self.executor.immediate_stop()

    def _worker_loop(self) -> None:
        while True:
            with self._cond:
                while self._latest_actions is None:
                    self._cond.wait()
                actions = self._latest_actions
                raw = self._latest_raw
                self._latest_actions = None
                self._cancel_event = threading.Event()
                cancel_event = self._cancel_event
            print(f"[runner] executing latest command: {raw}", flush=True)
            try:
                self.executor.run_actions(actions, cancel_event)
            except Exception as exc:
                print(f"[runner] action execution failed: {exc}", flush=True)
                try:
                    self.executor.immediate_stop()
                except Exception as stop_exc:
                    print(f"[runner] immediate stop after failure failed: {stop_exc}", flush=True)


def build_backend(args: argparse.Namespace) -> BackendBase:
    if args.dry_run:
        return DryRunBackend()
    return HolosomaRos2Backend(cmd_vel_topic=args.cmd_vel_topic, state_topic=args.state_topic)


def main() -> int:
    parser = argparse.ArgumentParser(description="Preemptible NaVILA-style middle adapter for Holosoma")
    parser.add_argument("--dry-run", action="store_true", help="Print commands instead of publishing ROS2 topics")
    parser.add_argument("--stdin", action="store_true", help="Read one text command per line from stdin")
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

    if not args.stdin:
        parser.print_help()
        return 0

    runner = PreemptiveActionRunner(executor)
    print("Enter commands, e.g. 'move forward 20 centimeters', 'turn left 15 degrees', 'stop', '='. Ctrl-D to quit.", flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            actions = text_parser.parse(line)
        except Exception as exc:
            print(f"[parse] unsupported command dropped: {line} ({exc})", flush=True)
            continue
        runner.submit(actions, line)

    print("[bridge] stdin closed; stopping robot", flush=True)
    executor.immediate_stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
