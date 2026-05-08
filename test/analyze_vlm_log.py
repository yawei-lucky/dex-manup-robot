#!/usr/bin/env python3
"""
Analyze NaVILA VLM decision log and generate an HTML report.

Usage:
  python test/analyze_vlm_log.py runtime/logs/navila_client_XXX.log
  python test/analyze_vlm_log.py --watch runtime/logs/navila_client_XXX.log
  python test/analyze_vlm_log.py --out report.html runtime/logs/navila_client_XXX.log
"""
from __future__ import annotations

import argparse
import base64
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Decision:
    request_idx: int
    img_dir: Optional[str]
    first_frame: Optional[str]
    last_frame: Optional[str]
    raw_vlm: str
    target_state: Optional[str]  # parsed from target_state: in raw VLM text
    target_side: Optional[str]   # from [target_side] line
    distance: Optional[str]      # from [distance] line
    command: Optional[str]


def parse_log(log_path: Path) -> List[Decision]:
    decisions: List[Decision] = []

    req_idx: Optional[int] = None
    img_dir: Optional[str] = None
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None
    raw_lines: List[str] = []
    in_raw = False
    target_side: Optional[str] = None
    distance: Optional[str] = None
    command: Optional[str] = None

    def flush() -> None:
        nonlocal req_idx, img_dir, first_frame, last_frame, raw_lines, in_raw
        nonlocal target_side, distance, command
        if req_idx is not None:
            raw_text = "\n".join(raw_lines).strip()
            ts: Optional[str] = None
            m = re.search(r"^target_state\s*:\s*(.+)", raw_text, re.IGNORECASE | re.MULTILINE)
            if m:
                ts = m.group(1).strip()
            decisions.append(Decision(
                request_idx=req_idx,
                img_dir=img_dir,
                first_frame=first_frame,
                last_frame=last_frame,
                raw_vlm=raw_text,
                target_state=ts,
                target_side=target_side,
                distance=distance,
                command=command,
            ))
        req_idx = None
        img_dir = None
        first_frame = None
        last_frame = None
        raw_lines = []
        in_raw = False
        target_side = None
        distance = None
        command = None

    with log_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")

            # Window section header → new decision record
            m = re.match(r"=+ request (\d+) \| window =+", line)
            if m:
                flush()
                req_idx = int(m.group(1))
                continue

            # Non-window section headers → stop raw mode
            if re.match(r"=+ request \d+ \| (vlm|bridge) =+", line):
                in_raw = False
                continue

            if req_idx is None:
                continue

            # Window summary line
            m = re.match(
                r"\[window\] \d+ frames \| dir=(.+?) \| first=(.+?) \| last=(.+?)$",
                line,
            )
            if m:
                img_dir = m.group(1).strip()
                first_frame = m.group(2).strip()
                last_frame = m.group(3).strip()
                continue

            # Raw VLM block start
            if line == "[raw]":
                in_raw = True
                continue

            # Lines that end the raw block
            if in_raw and (
                line.startswith("[target_side]")
                or line.startswith("command:")
                or line.startswith("[bridge]")
                or line.startswith("[gate]")
                or line.startswith("[no-vlm]")
            ):
                in_raw = False
                # fall through to handle this line normally

            if in_raw:
                raw_lines.append(line)
                continue

            # Extracted target_side
            m = re.match(r"\[target_side\] (.+)$", line)
            if m:
                target_side = m.group(1).strip()
                continue

            # Distance assessment line
            m = re.match(r"\[distance\] (.+)$", line)
            if m:
                distance = m.group(1).strip()
                continue

            # Final command
            m = re.match(r"command: (.+)$", line)
            if m:
                command = m.group(1).strip()
                continue

    flush()
    return decisions


def _frame_num(name: str) -> Optional[int]:
    m = re.match(r"[a-z]+_(\d+)", name)
    return int(m.group(1)) if m else None


def find_window_frames(
    img_dir: str,
    first_frame: str,
    last_frame: str,
    embed: bool,
    images_dir_override: Optional[Path],
) -> List[Tuple[str, str]]:
    """Return list of (src, filename) for the 8 frames in a window."""
    dir_path = images_dir_override or Path(img_dir)
    first_num = _frame_num(first_frame)
    last_num = _frame_num(last_frame)

    if not dir_path.exists() or first_num is None or last_num is None:
        return []

    frames: List[Path] = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        n = _frame_num(p.name)
        if n is not None and first_num <= n <= last_num:
            frames.append(p)

    frames.sort(key=lambda p: _frame_num(p.name) or 0)

    result = []
    for p in frames:
        if embed:
            try:
                data = p.read_bytes()
                b64 = base64.b64encode(data).decode("ascii")
                src = f"data:image/jpeg;base64,{b64}"
            except OSError:
                src = ""
        else:
            src = f"file://{p.resolve()}"
        result.append((src, p.name))
    return result


def _cmd_color_class(cmd: Optional[str]) -> str:
    if cmd is None:
        return "cmd-unknown"
    c = cmd.lower()
    if "stop" in c:
        return "cmd-stop"
    if "turn left" in c:
        return "cmd-turn-left"
    if "turn right" in c:
        return "cmd-turn-right"
    if "forward" in c:
        return "cmd-forward"
    if "backward" in c:
        return "cmd-backward"
    return "cmd-unknown"


def _build_stats_html(decisions: List[Decision]) -> str:
    counts: Dict[str, int] = {}
    for d in decisions:
        key = d.command or "(none)"
        counts[key] = counts.get(key, 0) + 1

    total = len(decisions)
    if total == 0:
        return ""

    color_map = {
        "move forward": "#1a6635",
        "stop": "#6b1414",
        "turn left": "#143460",
        "turn right": "#5a3200",
        "move backward": "#4a3800",
    }

    rows = []
    for cmd, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        color = "#444"
        for k, v in color_map.items():
            if k in cmd.lower():
                color = v
                break
        bar_w = max(4, int(pct * 2))
        bar = f'<span class="bar" style="width:{bar_w}px; background:{color}"></span>'
        rows.append(
            f'<div class="stat-row">{bar} '
            f'<span class="stat-cmd">{cmd}</span>'
            f'<span class="stat-cnt">{cnt} ({pct:.0f}%)</span></div>'
        )
    return "\n".join(rows)


def _build_step_html(
    d: Decision,
    embed: bool,
    images_dir_override: Optional[Path],
) -> str:
    color_cls = _cmd_color_class(d.command)
    cmd_label = d.command or "(no command)"

    frames_html = ""
    if d.img_dir and d.first_frame and d.last_frame:
        frames = find_window_frames(
            d.img_dir, d.first_frame, d.last_frame, embed, images_dir_override
        )
        if frames:
            imgs = []
            for src, name in frames:
                if src:
                    imgs.append(f'<img src="{src}" title="{name}" loading="lazy">')
                else:
                    imgs.append(f'<div class="no-img">{name}</div>')
            frames_html = '<div class="frames">' + "".join(imgs) + "</div>"
        else:
            short_dir = Path(d.img_dir).name
            frames_html = f'<div class="no-img-wide">images not found ({short_dir})</div>'

    meta_parts = []
    if d.target_side:
        meta_parts.append(f"position: {d.target_side}")
    if d.distance:
        meta_parts.append(f"distance: {d.distance}")
    elif d.target_state and not d.target_side:
        meta_parts.append(f"target_state: {d.target_state}")
    meta_html = (
        '<div class="meta">' + " &nbsp;|&nbsp; ".join(meta_parts) + "</div>"
        if meta_parts
        else ""
    )

    raw_escaped = (
        d.raw_vlm.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )

    return (
        f'<div class="step">'
        f'<div class="step-header">'
        f'<span class="req-num">#{d.request_idx:04d}</span>'
        f'<span class="cmd-badge {color_cls}">{cmd_label}</span>'
        f"</div>"
        f"{frames_html}"
        f"{meta_html}"
        f'<div class="vlm-text">{raw_escaped}</div>'
        f"</div>"
    )


_CSS = """
* { box-sizing: border-box; }
body { background: #1a1a1a; color: #eee; font-family: monospace; margin: 0; padding: 16px; }
h2 { color: #ccc; margin: 0 0 16px 0; font-size: 16px; }
.stats { background: #252525; padding: 14px 16px; margin-bottom: 20px;
         border-radius: 8px; border: 1px solid #333; }
.stats-title { font-weight: bold; color: #ccc; margin-bottom: 10px; }
.stat-row { display: flex; align-items: center; gap: 8px; margin: 5px 0; font-size: 12px; }
.bar { display: inline-block; height: 12px; vertical-align: middle; border-radius: 2px; flex-shrink: 0; }
.stat-cmd { color: #ccc; }
.stat-cnt { color: #888; }
.step { background: #252525; padding: 14px; margin-bottom: 10px;
        border-radius: 8px; border: 1px solid #333; }
.step-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.req-num { color: #666; font-size: 12px; min-width: 48px; }
.cmd-badge { padding: 3px 10px; border-radius: 4px; font-weight: bold; font-size: 12px; }
.cmd-forward  { background: #1a6635; color: #9effc1; }
.cmd-stop     { background: #6b1414; color: #ffaaaa; }
.cmd-turn-left  { background: #143460; color: #88ccff; }
.cmd-turn-right { background: #5a3200; color: #ffcc88; }
.cmd-backward { background: #4a3800; color: #ffe088; }
.cmd-unknown  { background: #333; color: #999; }
.frames { display: grid; grid-template-columns: repeat(8, 1fr); gap: 3px; margin-bottom: 8px; }
.frames img { width: 100%; aspect-ratio: 4/3; border-radius: 3px; object-fit: cover;
              cursor: pointer; transition: transform 0.1s; display: block; }
.frames img:hover { transform: scale(1.04); }
.no-img { width: 100%; aspect-ratio: 4/3; background: #333; border-radius: 3px;
          display: flex; align-items: center; justify-content: center;
          color: #555; font-size: 10px; text-align: center; padding: 4px; }
.no-img-wide { height: 28px; background: #2a2a2a; border-radius: 3px;
               display: flex; align-items: center; padding: 0 8px;
               color: #555; font-size: 11px; margin-bottom: 6px; }
.meta { margin: 4px 0 6px 0; color: #fa0; font-size: 11px; }
.vlm-text { background: #111; padding: 7px 10px; border-radius: 4px;
            font-size: 11px; white-space: pre-wrap; color: #888; line-height: 1.5; }
"""


def generate_html(
    decisions: List[Decision],
    log_path: Path,
    watch: bool,
    embed: bool,
    newest_first: bool,
    images_dir_override: Optional[Path],
) -> str:
    refresh_meta = '<meta http-equiv="refresh" content="3">' if watch else ""
    ordered = list(reversed(decisions)) if newest_first else decisions
    total = len(decisions)
    stats_html = _build_stats_html(decisions)
    steps_html = "\n".join(_build_step_html(d, embed, images_dir_override) for d in ordered)
    updated = time.strftime("%Y-%m-%d %H:%M:%S")
    watch_note = "  ·  auto-refresh 3s" if watch else ""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  {refresh_meta}
  <title>VLM Log — {log_path.name}</title>
  <style>{_CSS}</style>
</head>
<body>
  <h2>VLM Log — {log_path.name}</h2>
  <div class="stats">
    <div class="stats-title">{total} decisions &nbsp;·&nbsp; updated {updated}{watch_note}</div>
    {stats_html}
  </div>
  {steps_html}
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze NaVILA VLM decision log → HTML report"
    )
    parser.add_argument("log", type=Path, help="Log file path")
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Output HTML path (default: <log>.html)",
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="Regenerate every 3s; browser auto-refreshes",
    )
    parser.add_argument(
        "--interval", type=float, default=3.0,
        help="Regeneration interval in seconds (default: 3)",
    )
    parser.add_argument(
        "--embed", action="store_true",
        help="Embed images as base64 (larger file, works without image dir)",
    )
    parser.add_argument(
        "--oldest-first", action="store_true",
        help="Show oldest decision at top (default: newest first)",
    )
    parser.add_argument(
        "--images-dir", type=Path, default=None,
        help="Override image directory from log (useful if images were moved)",
    )
    args = parser.parse_args()

    if not args.log.exists():
        print(f"Error: log file not found: {args.log}", file=sys.stderr)
        return 1

    out_path = args.out or args.log.with_suffix(".html")
    newest_first = not args.oldest_first

    def generate() -> None:
        decisions = parse_log(args.log)
        html = generate_html(
            decisions, args.log, args.watch, args.embed, newest_first, args.images_dir
        )
        out_path.write_text(html, encoding="utf-8")
        print(f"[analyze] {len(decisions)} decisions → {out_path}", flush=True)

    generate()

    if args.watch:
        print(
            f"[analyze] watching {args.log.name} — open {out_path} in browser",
            flush=True,
        )
        try:
            while True:
                time.sleep(args.interval)
                generate()
        except KeyboardInterrupt:
            print("\n[analyze] stopped.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
