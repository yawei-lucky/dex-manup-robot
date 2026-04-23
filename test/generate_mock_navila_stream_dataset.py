#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image, ImageDraw

W = 640
H = 480


def draw_corridor(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle([0, 0, W, int(H * 0.45)], fill=(185, 205, 235))
    draw.polygon([(0, H), (W * 0.33, H * 0.55), (W * 0.67, H * 0.55), (W, H)], fill=(95, 95, 95))
    draw.line([(W * 0.5, H), (W * 0.5, H * 0.55)], fill=(220, 220, 220), width=4)
    draw.line([(W * 0.25, H), (W * 0.42, H * 0.55)], fill=(180, 180, 180), width=2)
    draw.line([(W * 0.75, H), (W * 0.58, H * 0.55)], fill=(180, 180, 180), width=2)


def draw_robot_hud(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.rounded_rectangle([18, 18, 250, 78], radius=10, fill=(20, 20, 20), outline=(245, 245, 245))
    draw.text((30, 30), text, fill=(255, 255, 255))


def save_sequence(seq_dir: Path, kind: str) -> None:
    seq_dir.mkdir(parents=True, exist_ok=True)

    for i in range(8):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_corridor(draw)

        if kind == "forward":
            size = 30 + i * 18
            x = W // 2
            y = int(H * 0.42)
            draw.rectangle([x - size, y - size, x + size, y + size], outline=(255, 70, 70), width=5)
            draw_robot_hud(draw, f"mock G1 view | forward | f{i+1}")

        elif kind == "turn_left":
            x = int(W * (0.68 - i * 0.05))
            y = int(H * 0.43)
            draw.rectangle([x - 36, y - 36, x + 36, y + 36], outline=(255, 180, 60), width=5)
            draw.polygon([(70, H//2), (130, H//2 - 30), (130, H//2 + 30)], fill=(255, 255, 0))
            draw_robot_hud(draw, f"mock G1 view | left | f{i+1}")

        elif kind == "turn_right":
            x = int(W * (0.32 + i * 0.05))
            y = int(H * 0.43)
            draw.rectangle([x - 36, y - 36, x + 36, y + 36], outline=(60, 220, 255), width=5)
            draw.polygon([(W - 70, H//2), (W - 130, H//2 - 30), (W - 130, H//2 + 30)], fill=(255, 255, 0))
            draw_robot_hud(draw, f"mock G1 view | right | f{i+1}")

        elif kind == "stop":
            draw.rectangle([W//2 - 70, int(H * 0.34), W//2 + 70, int(H * 0.34) + 140], outline=(255, 255, 255), width=4)
            draw.text((W//2 - 22, int(H * 0.34) + 50), "STOP", fill=(255, 80, 80))
            draw_robot_hud(draw, f"mock G1 view | stop | f{i+1}")

        else:
            raise ValueError(f"Unknown sequence kind: {kind}")

        img.save(seq_dir / f"frame_{i+1:02d}.jpg", quality=95)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic image-stream dataset for NaVILA client testing")
    parser.add_argument("--out-dir", type=Path, default=Path("test/mock_navila_stream_dataset"))
    args = parser.parse_args()

    root = args.out_dir
    save_sequence(root / "forward", "forward")
    save_sequence(root / "turn_left", "turn_left")
    save_sequence(root / "turn_right", "turn_right")
    save_sequence(root / "stop", "stop")

    print(f"Synthetic dataset written to: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
