#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List

import zmq


DEFAULT_OUT_DIR = Path.home() / "robotics/holosoma/runtime_image_file/navila_mujoco_stream"


def list_jpgs(out_dir: Path) -> List[Path]:
    """Return visible jpg files ordered by zero-padded filename."""
    return sorted(
        [p for p in out_dir.glob("*.jpg") if p.is_file() and not p.name.startswith(".")],
        key=lambda p: p.name,
    )


def clear_stream_dir(out_dir: Path) -> None:
    """Remove old stream images and unfinished hidden temp files."""
    for pattern in ("*.jpg", ".*.jpg", ".*.tmp"):
        for path in out_dir.glob(pattern):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass


def cleanup_old_files(out_dir: Path, max_files: int) -> None:
    """Keep directory scans cheap by retaining only recent jpg files."""
    if max_files <= 0:
        return

    jpgs = list_jpgs(out_dir)
    extra = len(jpgs) - max_files
    if extra <= 0:
        return

    for path in jpgs[:extra]:
        try:
            path.unlink()
        except OSError:
            pass


def make_socket(context: zmq.Context, server: str, timeout_ms: int) -> zmq.Socket:
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(server)
    return socket


def atomic_write_bytes(final_path: Path, data: bytes) -> None:
    """Write a complete image via hidden temp file, then atomic rename.

    navila_stream_client ignores files whose names start with '.', so it will not
    consume a half-written image.
    """
    tmp_path = final_path.with_name(f".{final_path.name}.tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(final_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pull RGB JPEG frames from a Psi0-style G1 RealSense ZMQ server "
            "and save them as an image-folder stream for navila_stream_client."
        )
    )
    parser.add_argument(
        "--server",
        type=str,
        required=True,
        help="ZMQ endpoint of the G1 RealSense server, e.g. tcp://192.168.123.164:5556",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Directory for saved jpg stream frames. Default: {DEFAULT_OUT_DIR}",
    )
    parser.add_argument("--fps", type=float, default=10.0, help="Host-side frame saving rate.")
    parser.add_argument("--prefix", type=str, default="real", help="Output filename prefix.")
    parser.add_argument("--start-index", type=int, default=0, help="Initial frame index.")
    parser.add_argument("--timeout-ms", type=int, default=2000, help="ZMQ send/receive timeout.")
    parser.add_argument(
        "--max-files",
        type=int,
        default=500,
        help="Keep only the latest N jpg files to avoid expensive directory scans. <=0 disables cleanup.",
    )
    parser.add_argument(
        "--clear-dir",
        action="store_true",
        help="Remove existing jpg/temp files from --out-dir before starting.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional JSONL manifest recording saved frames.",
    )
    args = parser.parse_args()

    if args.fps <= 0:
        raise SystemExit("--fps must be positive")
    if args.start_index < 0:
        raise SystemExit("--start-index must be non-negative")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.clear_dir:
        clear_stream_dir(args.out_dir)
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)

    context = zmq.Context()
    socket = make_socket(context, args.server, args.timeout_ms)

    period = 1.0 / args.fps
    frame_id = args.start_index
    saved = 0
    last_print = time.monotonic()

    print(f"[real_camera_client] server={args.server}", flush=True)
    print(f"[real_camera_client] out_dir={args.out_dir}", flush=True)
    print(f"[real_camera_client] fps={args.fps}", flush=True)
    print(f"[real_camera_client] max_files={args.max_files}", flush=True)

    try:
        while True:
            t0 = time.monotonic()

            try:
                # Psi0's REP server does not inspect request content; any bytes are enough.
                socket.send(b"rgb")
                parts = socket.recv_multipart()
            except zmq.error.Again:
                print("[real_camera_client] request timeout; reconnecting...", flush=True)
                socket.close(0)
                socket = make_socket(context, args.server, args.timeout_ms)
                time.sleep(0.2)
                continue

            if not parts or not parts[0]:
                print("[real_camera_client] empty frame from server", flush=True)
                time.sleep(period)
                continue

            # Psi0 server returns multipart [rgb_jpg, ir_jpg, depth_raw].
            rgb_jpg = parts[0]
            final_path = args.out_dir / f"{args.prefix}_{frame_id:06d}.jpg"
            atomic_write_bytes(final_path, rgb_jpg)

            if args.manifest is not None:
                record = {
                    "frame_id": frame_id,
                    "path": str(final_path),
                    "timestamp_host": time.time(),
                    "bytes": len(rgb_jpg),
                    "num_parts": len(parts),
                }
                with args.manifest.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            frame_id += 1
            saved += 1

            if saved % 20 == 0:
                cleanup_old_files(args.out_dir, args.max_files)

            now = time.monotonic()
            if now - last_print >= 2.0:
                print(
                    f"[real_camera_client] saved={saved} last={final_path.name} "
                    f"size={len(rgb_jpg) / 1024:.1f}KB",
                    flush=True,
                )
                last_print = now

            elapsed = time.monotonic() - t0
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[real_camera_client] stopped", flush=True)
        return 0
    finally:
        socket.close(0)
        context.term()


if __name__ == "__main__":
    raise SystemExit(main())
