#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2


def save_frame(frame_bgr, out_path: Path, jpeg_quality: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(
        str(out_path),
        frame_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
    )
    if not ok:
        raise RuntimeError(f"Failed to save frame: {out_path}")


def resolve_output_dir(base_output_dir: Path, video_path: Path, use_video_stem_dir: bool) -> Path:
    if use_video_stem_dir:
        return base_output_dir / video_path.stem
    return base_output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a video into time-ordered JPG frames for navila_folder_stream_client")
    parser.add_argument("--video", type=Path, required=True, help="Input video path")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output folder for JPG frames, or a parent folder when --use-video-stem-dir is enabled")
    parser.add_argument("--use-video-stem-dir", action="store_true", help="Create a subfolder named after the video file stem and save frames there")
    parser.add_argument("--sample-fps", type=float, default=2.0, help="Frame sampling rate from the source video")
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--resize-width", type=int, default=0, help="Optional resize width; 0 keeps original size")
    parser.add_argument("--resize-height", type=int, default=0, help="Optional resize height; 0 keeps original size")
    parser.add_argument("--stream", action="store_true", help="Write frames one by one with a time delay to simulate a live image stream")
    parser.add_argument("--stream-interval-sec", type=float, default=0.5, help="Delay between written frames when --stream is used")
    parser.add_argument("--clear-output", action="store_true", help="Remove old JPG files in the resolved output directory before writing")
    parser.add_argument("--prefix", type=str, default="frame")
    args = parser.parse_args()

    if not args.video.exists() or not args.video.is_file():
        raise SystemExit(f"Invalid video file: {args.video}")
    if args.sample_fps <= 0:
        raise SystemExit("--sample-fps must be > 0")

    output_dir = resolve_output_dir(args.output_dir, args.video, args.use_video_stem_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.clear_output:
        for p in output_dir.glob("*.jpg"):
            p.unlink()
        manifest_path = output_dir / "manifest.json"
        if manifest_path.exists():
            manifest_path.unlink()

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit(f"Failed to open video: {args.video}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if src_fps <= 0:
        src_fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / src_fps if total_frames > 0 else 0.0

    step = max(1, int(round(src_fps / args.sample_fps)))
    written = 0
    frame_idx = 0
    manifest = {
        "video": str(args.video),
        "resolved_output_dir": str(output_dir),
        "source_fps": src_fps,
        "sample_fps": args.sample_fps,
        "frame_step": step,
        "duration_sec": duration_sec,
        "written_frames": [],
    }

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_idx % step == 0:
            if args.resize_width > 0 and args.resize_height > 0:
                frame = cv2.resize(frame, (args.resize_width, args.resize_height), interpolation=cv2.INTER_AREA)

            t_sec = frame_idx / src_fps
            out_name = f"{args.prefix}_{written + 1:06d}_t{int(round(t_sec * 1000)):09d}ms.jpg"
            out_path = output_dir / out_name
            save_frame(frame, out_path, args.jpeg_quality)
            manifest["written_frames"].append({
                "file": out_name,
                "source_frame_index": frame_idx,
                "time_sec": t_sec,
            })
            written += 1

            if args.stream:
                print(f"[stream] wrote {out_name}", flush=True)
                time.sleep(args.stream_interval_sec)

        frame_idx += 1

    cap.release()
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote {written} frames to: {output_dir}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
