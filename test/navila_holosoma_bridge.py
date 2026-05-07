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
    def wait_until_ready(self, timeout_sec: float = 0.0) -> bool:
        return True

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
        self.cmd_vel_topic = cmd_vel_topic
        self.state_topic = state_topic

        if not self._rclpy.ok():
            self._rclpy.init(args=None)
        self.node = Node("navila_holosoma_bridge")
        self.cmd_pub = self.node.create_publisher(TwistStamped, cmd_vel_topic, 10)
        self.state_pub = self.node.create_publisher(String, state_topic, 10)
        self._last_state_text = None

    def wait_until_ready(self, timeout_sec: float = 0.0) -> bool:
        if timeout_sec <= 0:
            return True
        print(
            "[ros2] waiting for Holosoma subscribers "
            f"cmd_vel={self.cmd_vel_topic}, state={self.state_topic}, timeout={timeout_sec:.1f}s",
            flush=True,
        )
        deadline = time.time() + timeout_sec
        last_report = 0.0
        while time.time() < deadline:
            self._rclpy.spin_once(self.node, timeout_sec=0.05)
            cmd_subs = self.cmd_pub.get_subscription_count()
            state_subs = self.state_pub.get_subscription_count()
            if cmd_subs > 0 and state_subs > 0:
                print(
                    f"[ros2] Holosoma subscribers ready: cmd_vel={cmd_subs}, state={state_subs}",
                    flush=True,
                )
                return True
            now = time.time()
            if now - last_report > 1.0:
                print(f"[ros2] waiting... cmd_vel_subs={cmd_subs}, state_subs={state_subs}", flush=True)
                last_report = now
        print("[ros2] subscriber wait timed out; continuing anyway", flush=True)
        return False

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
        self._stop_event = threading.Event()

    def bootstrap_to_stand(self, skip_init_pose: bool = False) -> None:
        if skip_init_pose:
            print("[bootstrap] start -> stand (skipping init_pose)", flush=True)
        else:
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

    def hold_stand(self, duration: float | None = None) -> None:
        self.ensure_stand()
        hold = self.settle_sec if duration is None else max(0.0, duration)
        end_t = time.time() + hold
        while time.time() < end_t:
            self.backend.zero_velocity()
            time.sleep(0.1)

    def emergency_stop(self) -> None:
        self._stop_event.set()
        self.backend.zero_velocity()
        print("[stop] emergency stop", flush=True)

    def _stream_velocity(self, vx: float, vy: float, wz: float, duration: float) -> None:
        self._stop_event.clear()
        self.ensure_walk()
        dt = 1.0 / max(1e-6, self.publish_hz)
        end_t = time.time() + max(0.0, duration)
        while time.time() < end_t:
            if self._stop_event.is_set():
                print("[stop] motion interrupted", flush=True)
                break
            self.backend.send_velocity(vx, vy, wz)
            time.sleep(dt)
        self.backend.zero_velocity()
        if not self._stop_event.is_set():
            self.hold_stand(self.settle_sec)

    def run_actions(self, actions: Iterable[MidLevelAction]) -> None:
        for action in actions:
            self.run_action(action)

    def run_action(self, action: MidLevelAction) -> None:
        print(f"[exec] {action}", flush=True)

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
            wz_radps = math.radians(sign * self.angular_speed_degps)
            duration = degrees / max(1e-6, self.angular_speed_degps)
            self._stream_velocity(0.0, 0.0, wz_radps, duration)
            return

        raise ValueError(f"Unsupported action: {action.action}")


def build_backend(args: argparse.Namespace) -> BackendBase:
    if args.dry_run:
        return DryRunBackend()
    return HolosomaRos2Backend(cmd_vel_topic=args.cmd_vel_topic, state_topic=args.state_topic)


def main() -> int:
    parser = argparse.ArgumentParser(description="NaVILA-style middle adapter for Holosoma")
    parser.add_argument("--dry-run", action="store_true", help="Print commands instead of publishing ROS2 topics")
    parser.add_argument("--stdin", action="store_true", help="Read one text command per line from stdin")
    parser.add_argument("--cmd-vel-topic", type=str, default="/cmd_vel")
    parser.add_argument("--state-topic", type=str, default="/holosoma/state_input")
    parser.add_argument("--linear-speed", type=float, default=0.45, help="Execution speed in m/s for translation actions")
    parser.add_argument("--angular-speed-degps", type=float, default=60.0, help="Execution angular speed in deg/s")
    parser.add_argument("--publish-hz", type=float, default=10.0, help="How often to republish cmd_vel during motion")
    parser.add_argument("--settle-sec", type=float, default=0.4, help="Stand-and-zero hold after each action")
    parser.add_argument("--bootstrap-stand", action="store_true", help="Run init->start->stand at startup")
    parser.add_argument("--wait-for-subscribers", action="store_true", help="Wait for Holosoma ROS2 subscribers before bootstrap")
    parser.add_argument("--subscriber-wait-timeout", type=float, default=30.0, help="Seconds to wait for ROS2 subscribers")
    parser.add_argument("--skip-init", action="store_true", help="Skip initialization if robot is already prepared")
    parser.add_argument("--no-init-pose", action="store_true", help="Skip init_pose step during bootstrap (use when restarting client while robot is already standing)")
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
        if args.wait_for_subscribers:
            backend.wait_until_ready(args.subscriber_wait_timeout)
        executor.bootstrap_to_stand(skip_init_pose=args.no_init_pose)

    if not args.stdin:
        parser.print_help()
        return 0

    print("Enter commands, e.g. 'move forward 20 centimeters', 'turn left 15 degrees', 'stop'. Ctrl-D to quit.", flush=True)

    _STOP_TOKENS = {"stop"}
    cmd_queue: queue.Queue[str | None] = queue.Queue()

    def _stdin_reader() -> None:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            if line in _STOP_TOKENS:
                executor.emergency_stop()
                drained = 0
                while True:
                    try:
                        cmd_queue.get_nowait()
                        drained += 1
                    except queue.Empty:
                        break
                if drained:
                    print(f"[stop] drained {drained} queued command(s)", flush=True)
            else:
                cmd_queue.put(line)
        cmd_queue.put(None)  # EOF sentinel

    threading.Thread(target=_stdin_reader, daemon=True).start()

    while True:
        try:
            line = cmd_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if line is None:
            break
        try:
            actions = text_parser.parse(line)
        except Exception as exc:
            print(f"[parse] unsupported command dropped: {line} ({exc})", flush=True)
            continue
        executor.run_actions(actions)

    print("[bridge] stdin closed; stopping robot", flush=True)
    executor.immediate_stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
