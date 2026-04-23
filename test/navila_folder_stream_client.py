#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from PIL import Image


class BridgeWriter:
    def __init__(self, bridge_cmd: Optional[str]) -> None:
        self.bridge_cmd = bridge_cmd
        self.proc: Optional[subprocess.Popen[str]] = None

    def start(self) -> None:
        if not self.bridge_cmd:
            return
        self.proc = subprocess.Popen(
            shlex.split(self.bridge_cmd),
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def send(self, command: str) -> None:
        if self.proc is None or self.proc.stdin is None:
            return
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        finally:
            self.proc.terminate()
            self.proc.wait(timeout=3)


def encode_image_to_base64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def load_images(paths: List[Path]) -> List[Image.Image]:
    return [Image.open(p).convert("RGB") for p in paths]


def sample_to_8_frames(images: List[Image.Image]) -> List[Image.Image]:
    if len(images) == 0:
        raise ValueError("No images provided.")

    if len(images) < 8:
        pad = [Image.new("RGB", images[-1].size, (0, 0, 0)) for _ in range(8 - len(images))]
        images = pad + images
    elif len(images) > 8:
        n = len(images)
        indices = [int(i * (n - 1) / 7) for i in range(7)]
        images = [images[i] for i in indices] + [images[-1]]

    return images


def send_request(host: str, port: int, images: List[Image.Image], instruction: str) -> str:
    payload = {
        "images": [encode_image_to_base64(img) for img in images],
        "query": instruction,
    }
    data = json.dumps(payload).encode("utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.sendall(len(data).to_bytes(8, "big"))
        s.sendall(data)

        size_data = s.recv(8)
        if len(size_data) != 8:
            raise RuntimeError("Failed to read response size.")
        size = int.from_bytes(size_data, "big")

        response_data = b""
        while len(response_data) < size:
            packet = s.recv(4096)
            if not packet:
                break
            response_data += packet

    return json.loads(response_data.decode("utf-8"))


def _cleanup_text(text: str) -> str:
    line = text.strip().splitlines()[0].strip().lower()
    line = line.replace("\u00a0", " ")
    line = re.sub(r"[。．]+$", "", line)
    line = re.sub(r"\s+", " ", line)
    return line


def normalize_navila_output(text: str) -> str:
    line = _cleanup_text(text)

    stop_match = re.search(r"\bstop\b", line, re.IGNORECASE)
    turn_match = re.search(
        r"\bturn\s+(left|right)\s+(?:by\s+)?([-+]?\d+(?:\.\d+)?)\s*(deg|degree|degrees)\b",
        line,
        re.IGNORECASE,
    )
    move_match = re.search(
        r"\b(?:move|moving)\s+forward\s+([-+]?\d+(?:\.\d+)?)\s*(cm|centimeter|centimeters|m|meter|meters)\b",
        line,
        re.IGNORECASE,
    )

    if turn_match:
        direction = turn_match.group(1).lower()
        value = float(turn_match.group(2))
        value = max(1.0, min(180.0, value))
        value_str = f"{int(value)}" if value.is_integer() else f"{value:.1f}"
        return f"turn {direction} {value_str} degrees"

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

    if stop_match:
        return "stop"

    return "stop"


def build_instruction(user_task: str) -> str:
    return (
        f"{user_task}\n"
        "Output exactly one next action for navigation. "
        "The action should be one of: turn left by a specific degree, "
        "turn right by a specific degree, move forward a certain distance, or stop."
    )


def load_instruction(task: Optional[str], prompt_json: Optional[Path]) -> str:
    if prompt_json is not None:
        if not prompt_json.exists():
            raise SystemExit(f"Invalid prompt JSON file: {prompt_json}")
        elif not prompt_json.is_file():
            raise SystemExit(f"Prompt JSON file is not a regular file: {prompt_json}")
        try:
            data = json.loads(prompt_json.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(f"Failed to parse prompt JSON: {prompt_json}\n{exc}") from exc
        if not isinstance(data, dict):
            raise SystemExit("Prompt JSON must be an object.")
        prompt = data.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise SystemExit("Prompt JSON must contain a non-empty string field named 'prompt'.")
        return prompt

    if task is None or not task.strip():
        raise SystemExit("Provide either --task or --prompt-json.")
    return build_instruction(task)


def _natural_key(path: Path):
    parts = re.split(r"(\d+)", path.name)
    key = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return key


def get_latest_image_paths(images_dir: Path, pattern: str, keep_last: int, sort_by: str) -> List[Path]:
    paths = [p for p in images_dir.glob(pattern) if p.is_file()]
    if sort_by == "mtime":
        paths.sort(key=lambda p: (p.stat().st_mtime_ns, p.name))
    else:
        paths.sort(key=_natural_key)
    return paths[-keep_last:]


def main() -> int:
    parser = argparse.ArgumentParser(description="NaVILA folder stream client")
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=54321)
    parser.add_argument("--task", type=str, default=None)
    parser.add_argument("--prompt-json", type=Path, default=None, help="Path to a JSON prompt file containing at least a 'prompt' field")
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--pattern", type=str, default="*.jpg")
    parser.add_argument("--keep-last", type=int, default=8, help="How many latest files to consider before pad/sample")
    parser.add_argument("--sort-by", choices=["name", "mtime"], default="name", help="How to order frames before taking the latest window")
    parser.add_argument("--interval-sec", type=float, default=1.0)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run one inference only")
    parser.add_argument("--bridge-cmd", type=str, default=None, help="Example: 'python test/navila_holosoma_bridge_v0.py --stdin --dry-run'")
    parser.add_argument("--dedupe", action="store_true", help="Do not resend the same normalized command twice in a row")
    parser.add_argument("--min-images", type=int, default=1)
    args = parser.parse_args()

    if not args.images_dir.exists() or not args.images_dir.is_dir():
        raise SystemExit(f"Invalid images directory: {args.images_dir}")

    instruction = load_instruction(args.task, args.prompt_json)
    bridge = BridgeWriter(args.bridge_cmd)
    bridge.start()

    last_sent_cmd: Optional[str] = None
    last_signature: Optional[str] = None

    try:
        while True:
            image_paths = get_latest_image_paths(args.images_dir, args.pattern, args.keep_last, args.sort_by)
            if len(image_paths) < args.min_images:
                print(f"[wait] found {len(image_paths)} images, need at least {args.min_images}", flush=True)
                if args.once:
                    return 1
                time.sleep(args.interval_sec)
                continue

            if args.sort_by == "mtime":
                signature = "|".join(f"{p.name}:{int(p.stat().st_mtime_ns)}" for p in image_paths)
            else:
                signature = "|".join(p.name for p in image_paths)
            if signature == last_signature and not args.once:
                time.sleep(args.interval_sec)
                continue
            last_signature = signature

            images = load_images(image_paths)
            images = sample_to_8_frames(images)
            raw_output = send_request(args.host, args.port, images, instruction)
            final_cmd = normalize_navila_output(raw_output)

            if args.raw:
                print(f"[raw] {raw_output}", flush=True)
            print(final_cmd, flush=True)

            should_send = True
            if args.dedupe and final_cmd == last_sent_cmd:
                should_send = False

            if should_send:
                bridge.send(final_cmd)
                last_sent_cmd = final_cmd

            if args.once:
                return 0

            time.sleep(args.interval_sec)
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
