#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import socket
from pathlib import Path
from typing import List

from PIL import Image


ALLOWED_PATTERNS = [
    re.compile(r"^\s*stop\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(move|moving)\s+forward\s+([-+]?\d+(?:\.\d+)?)\s*(cm|centimeter|centimeters|m|meter|meters)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*turn\s+(left|right)\s+(?:by\s+)?([-+]?\d+(?:\.\d+)?)\s*(deg|degree|degrees)\s*$",
        re.IGNORECASE,
    ),
]


def encode_image_to_base64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def load_images(paths: List[Path]) -> List[Image.Image]:
    images: List[Image.Image] = []
    for p in paths:
        images.append(Image.open(p).convert("RGB"))
    return images


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


def normalize_navila_output(text: str) -> str:
    line = text.strip().splitlines()[0].strip()
    line = re.sub(r"[。．]+$", "", line)
    line = re.sub(r"\s+", " ", line)

    for pat in ALLOWED_PATTERNS:
        m = pat.match(line)
        if not m:
            continue

        if "stop" in line.lower():
            return "stop"

        if "turn" in line.lower():
            direction = m.group(1).lower()
            value = float(m.group(2))
            value = max(1.0, min(180.0, value))
            value_str = f"{int(value)}" if value.is_integer() else f"{value:.1f}"
            return f"turn {direction} {value_str} degrees"

        if "move" in line.lower():
            value = float(m.group(2))
            unit = m.group(3).lower()

            if unit in {"cm", "centimeter", "centimeters"}:
                if value <= 0:
                    return "stop"
                value_str = f"{int(value)}" if value.is_integer() else f"{value:.1f}"
                return f"move forward {value_str} centimeters"

            if unit in {"m", "meter", "meters"}:
                if value <= 0:
                    return "stop"
                value_str = f"{int(value)}" if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")
                return f"move forward {value_str} meters"

    return "stop"


def build_instruction(user_task: str) -> str:
    return (
        f'{user_task}\n'
        "Output exactly one next action for navigation. "
        "The action should be one of: turn left by a specific degree, "
        "turn right by a specific degree, move forward a certain distance, or stop."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal NaVILA client")
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=54321)
    parser.add_argument("--task", type=str, required=True, help="Instruction/task text")
    parser.add_argument(
        "--images",
        type=str,
        nargs="+",
        required=True,
        help="1 to N image paths; client will pad/sample to 8 frames",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw model output before normalization",
    )
    args = parser.parse_args()

    image_paths = [Path(p) for p in args.images]
    images = load_images(image_paths)
    images = sample_to_8_frames(images)

    instruction = build_instruction(args.task)
    raw_output = send_request(args.host, args.port, images, instruction)
    final_cmd = normalize_navila_output(raw_output)

    if args.raw:
        print("[raw]", raw_output)
    print(final_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
