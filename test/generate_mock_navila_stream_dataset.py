#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image, ImageDraw

W = 640
H = 480
SKY = (185, 205, 235)
ROAD = (95, 95, 95)
LINE = (220, 220, 220)
SIDE = (180, 180, 180)
BOX = (255, 180, 60)
HUD_BG = (20, 20, 20)
HUD_FG = (245, 245, 245)


def draw_hud(draw: ImageDraw.ImageDraw, frame_idx: int) -> None:
    draw.rounded_rectangle([18, 18, 300, 78], radius=10, fill=HUD_BG, outline=HUD_FG)
    draw.text((30, 30), f"mock G1-like egocentric | f{frame_idx + 1}", fill=HUD_FG)


def draw_perspective_corridor(draw: ImageDraw.ImageDraw, vanish_x: float) -> None:
    horizon_y = int(H * 0.45)
    top_y = int(H * 0.55)
    left_bottom = 0
    right_bottom = W
    left_top = int(max(40, vanish_x - 110))
    right_top = int(min(W - 40, vanish_x + 110))

    draw.rectangle([0, 0, W, horizon_y], fill=SKY)
    draw.polygon([(left_bottom, H), (left_top, top_y), (right_top, top_y), (right_bottom, H)], fill=ROAD)

    lane_center = int(vanish_x)
    draw.line([(W * 0.5, H), (lane_center, top_y)], fill=LINE, width=4)
    draw.line([(W * 0.22, H), (vanish_x - 52, top_y)], fill=SIDE, width=2)
    draw.line([(W * 0.78, H), (vanish_x + 52, top_y)], fill=SIDE, width=2)


def draw_square_box(draw: ImageDraw.ImageDraw, center_x: float, center_y: float, size: float) -> None:
    half = size / 2.0
    x1 = int(center_x - half)
    y1 = int(center_y - half)
    x2 = int(center_x + half)
    y2 = int(center_y + half)
    draw.rectangle([x1, y1, x2, y2], outline=BOX, width=5)


def save_forward(seq_dir: Path) -> None:
    seq_dir.mkdir(parents=True, exist_ok=True)
    for i in range(8):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_perspective_corridor(draw, vanish_x=W * 0.5)
        draw_square_box(draw, center_x=W * 0.5, center_y=H * 0.42, size=34 + i * 16)
        draw_hud(draw, i)
        img.save(seq_dir / f"frame_{i + 1:02d}.jpg", quality=95)


def save_turn_left(seq_dir: Path) -> None:
    seq_dir.mkdir(parents=True, exist_ok=True)
    vanish_x_values = [320, 334, 350, 370, 395, 420, 445, 470]
    box_centers = [None, None, None, (95, 215, 28), (125, 212, 38), (155, 208, 52), (190, 205, 66), (225, 202, 80)]

    for i in range(8):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_perspective_corridor(draw, vanish_x=vanish_x_values[i])
        if box_centers[i] is not None:
            cx, cy, size = box_centers[i]
            draw_square_box(draw, center_x=cx, center_y=cy, size=size)
        draw_hud(draw, i)
        img.save(seq_dir / f"frame_{i + 1:02d}.jpg", quality=95)


def save_turn_right(seq_dir: Path) -> None:
    seq_dir.mkdir(parents=True, exist_ok=True)
    vanish_x_values = [320, 306, 290, 270, 245, 220, 195, 170]
    box_centers = [None, None, None, (545, 215, 28), (515, 212, 38), (485, 208, 52), (450, 205, 66), (415, 202, 80)]

    for i in range(8):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_perspective_corridor(draw, vanish_x=vanish_x_values[i])
        if box_centers[i] is not None:
            cx, cy, size = box_centers[i]
            draw_square_box(draw, center_x=cx, center_y=cy, size=size)
        draw_hud(draw, i)
        img.save(seq_dir / f"frame_{i + 1:02d}.jpg", quality=95)


def save_stop(seq_dir: Path) -> None:
    seq_dir.mkdir(parents=True, exist_ok=True)
    for i in range(8):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_perspective_corridor(draw, vanish_x=W * 0.5)
        draw_square_box(draw, center_x=W * 0.5, center_y=H * 0.39, size=130)
        draw_hud(draw, i)
        img.save(seq_dir / f"frame_{i + 1:02d}.jpg", quality=95)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic image-stream dataset for NaVILA client testing")
    parser.add_argument("--out-dir", type=Path, default=Path("test/mock_navila_stream_dataset"))
    args = parser.parse_args()

    root = args.out_dir
    save_forward(root / "forward")
    save_turn_left(root / "turn_left")
    save_turn_right(root / "turn_right")
    save_stop(root / "stop")

    print(f"Synthetic dataset written to: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
