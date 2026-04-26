#!/usr/bin/env python3
from __future__ import annotations

import argparse
import queue
import re
import shlex
import subprocess
import sys
import threading
from typing import Optional


TURN_RE = re.compile(
    r"\bturn\s+(left|right)\s+(?:by\s+)?([-+]?\d+(?:\.\d+)?)\s*(deg|degree|degrees)\b",
    re.IGNORECASE,
)
MOVE_RE = re.compile(
    r"\b(?:move|moving)\s+forward\s+([-+]?\d+(?:\.\d+)?)\s*(cm|centimeter|centimeters|m|meter|meters)\b",
    re.IGNORECASE,
)


def normalize_command(text: str) -> Optional[str]:
    """Return a bridge-compatible command, or None if the text is unsupported."""
    cleaned = text.strip().lower()
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"[。．]+", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    if cleaned in {"s", "stop", "halt"} or re.fullmatch(r"command:\s*stop", cleaned):
        return "stop"

    if cleaned.startswith("command:"):
        cleaned = cleaned.split(":", 1)[1].strip()
    if cleaned.startswith("manual:"):
        cleaned = cleaned.split(":", 1)[1].strip()
    if cleaned.startswith("manual "):
        cleaned = cleaned[len("manual "):].strip()
    if cleaned.startswith("cmd "):
        cleaned = cleaned[len("cmd "):].strip()

    turn_match = TURN_RE.search(cleaned)
    if turn_match:
        direction = turn_match.group(1).lower()
        value = float(turn_match.group(2))
        value = max(1.0, min(180.0, value))
        value_str = f"{int(value)}" if value.is_integer() else f"{value:.1f}"
        return f"turn {direction} {value_str} degrees"

    move_match = MOVE_RE.search(cleaned)
    if move_match:
        value = float(move_match.group(1))
        unit = move_match.group(2).lower()
        if value <= 0:
            return "stop"
        if unit in {"cm", "centimeter", "centimeters"}:
            value_str = f"{int(value)}" if value.is_integer() else f"{value:.1f}"
            return f"move forward {value_str} centimeters"
        value_str = f"{int(value)}" if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")
        return f"move forward {value_str} meters"

    return None


class BridgeProcess:
    def __init__(self, bridge_cmd: str) -> None:
        self.bridge_cmd = bridge_cmd
        self.proc: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self.proc = subprocess.Popen(
            shlex.split(self.bridge_cmd),
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        print(f"[gate] bridge started: {self.bridge_cmd}", flush=True)

    def send(self, command: str, source: str) -> None:
        if self.proc is None or self.proc.stdin is None:
            print(f"[gate] bridge not available; drop {source}: {command}", flush=True)
            return
        with self._lock:
            try:
                print(f"[gate] forward {source}: {command}", flush=True)
                self.proc.stdin.write(command + "\n")
                self.proc.stdin.flush()
            except BrokenPipeError:
                print("[gate] bridge pipe is broken. Check run_navila_bridge_ros2.sh output.", flush=True)

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.stdin is not None:
                try:
                    self.proc.stdin.close()
                except BrokenPipeError:
                    pass
        finally:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass


def stdin_reader(out_queue: "queue.Queue[tuple[str, str]]") -> None:
    """Read automatic VLM commands from stdin, which is connected to navila_stream_client."""
    for line in sys.stdin:
        line = line.strip()
        if line:
            out_queue.put(("vlm", line))


def tty_reader(out_queue: "queue.Queue[tuple[str, str]]") -> None:
    """Read manual commands from the current terminal even though stdin is used by the client pipe."""
    try:
        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tty:
            for line in tty:
                line = line.strip()
                if line:
                    out_queue.put(("manual", line))
    except Exception as exc:
        print(f"[gate] manual tty input disabled: {exc}", flush=True)


def print_help() -> None:
    print("[gate] manual commands:", flush=True)
    print("[gate]   go                         enable VLM commands", flush=True)
    print("[gate]   pause | hold               disable VLM commands and send stop", flush=True)
    print("[gate]   stop                       send stop immediately and disable VLM commands", flush=True)
    print("[gate]   move forward 25 centimeters", flush=True)
    print("[gate]   turn left 15 degrees", flush=True)
    print("[gate]   turn right 15 degrees", flush=True)
    print("[gate]   help", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate NaVILA VLM commands before forwarding to Holosoma bridge")
    parser.add_argument(
        "--bridge-cmd",
        default="bash test/run_navila_bridge_ros2.sh",
        help="Actual bridge command that receives normalized commands on stdin.",
    )
    parser.add_argument("--require-go", action="store_true", help="Start with VLM command forwarding disabled until manual 'go'.")
    parser.add_argument("--no-manual", action="store_true", help="Disable manual /dev/tty command input.")
    args = parser.parse_args()

    bridge = BridgeProcess(args.bridge_cmd)
    bridge.start()

    events: "queue.Queue[tuple[str, str]]" = queue.Queue()
    threading.Thread(target=stdin_reader, args=(events,), daemon=True).start()
    if not args.no_manual:
        threading.Thread(target=tty_reader, args=(events,), daemon=True).start()

    auto_enabled = not args.require_go
    print("[gate] VLM command forwarding: " + ("enabled" if auto_enabled else "locked, waiting for manual 'go'"), flush=True)
    print_help()

    try:
        while True:
            source, text = events.get()
            lower = text.strip().lower()

            if source == "manual":
                if lower in {"go", "g"}:
                    auto_enabled = True
                    print("[gate] VLM command forwarding enabled.", flush=True)
                    continue

                if lower in {"pause", "hold", "lock"}:
                    auto_enabled = False
                    print("[gate] VLM command forwarding disabled. Sending stop.", flush=True)
                    bridge.send("stop", source="manual")
                    continue

                if lower in {"help", "h", "?"}:
                    print_help()
                    continue

                if lower in {"stop", "s", "halt"}:
                    auto_enabled = False
                    print("[gate] manual stop; VLM command forwarding disabled.", flush=True)
                    bridge.send("stop", source="manual")
                    continue

                manual_cmd = normalize_command(text)
                if manual_cmd is None:
                    print(f"[gate] unsupported manual command: {text}", flush=True)
                    print("[gate] type 'help' for supported commands.", flush=True)
                    continue
                bridge.send(manual_cmd, source="manual")
                continue

            # Automatic VLM command path.
            vlm_cmd = normalize_command(text)
            if vlm_cmd is None:
                print(f"[gate] unsupported VLM command dropped: {text}", flush=True)
                continue

            if not auto_enabled:
                print(f"[gate] VLM command gated; type 'go' to enable. queued command not sent: {vlm_cmd}", flush=True)
                continue

            bridge.send(vlm_cmd, source="vlm")

    except KeyboardInterrupt:
        print("[gate] interrupted", flush=True)
        return 130
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
