#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import IO, Deque, List, Optional

from PIL import Image


class ImageWindowNotReady(RuntimeError):
    def __init__(self, path: Path, exc: OSError) -> None:
        self.path = path
        self.original_error = exc
        super().__init__(f"Image is not ready: {path} ({exc})")


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
        try:
            self.proc.stdin.write(command + "\n")
            self.proc.stdin.flush()
        except BrokenPipeError as exc:
            raise RuntimeError(
                "Bridge process is not accepting commands. "
                "Check --bridge-cmd and the bridge terminal output."
            ) from exc

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
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
            except ProcessLookupError:
                pass


def encode_image_to_base64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def load_images(paths: List[Path]) -> List[Image.Image]:
    images: List[Image.Image] = []
    for path in paths:
        try:
            with Image.open(path) as image:
                images.append(image.convert("RGB").copy())
        except OSError as exc:
            raise ImageWindowNotReady(path, exc) from exc
    return images


def sample_to_n_frames(images: List[Image.Image], n: int = 8) -> List[Image.Image]:
    if len(images) == 0:
        raise ValueError("No images provided.")
    if n < 1:
        raise ValueError("n must be >= 1.")

    if len(images) < n:
        pad = [Image.new("RGB", images[-1].size, (0, 0, 0)) for _ in range(n - len(images))]
        images = pad + images
    elif len(images) > n:
        total = len(images)
        indices = [int(i * (total - 1) / (n - 1)) for i in range(n - 1)] if n > 1 else []
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
    text = text.strip().lower()
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[。．]+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def extract_target_assessment(text: str) -> tuple[Optional[str], Optional[str]]:
    """Parse 'target_state: <position>, <distance>' from VLM output.

    Returns (position, distance); either may be None if not found.
    """
    cleaned = _cleanup_text(text)
    m = re.search(
        r"target_(?:state|side)\s*:\s*(left|right|center|not\s+visible)"
        r"(?:\s*,\s*(far\s+away|near|very\s+close))?",
        cleaned,
        re.IGNORECASE,
    )
    if not m:
        return None, None
    side = re.sub(r"\s+", " ", m.group(1).strip().lower())
    dist = re.sub(r"\s+", " ", m.group(2).strip().lower()) if m.group(2) else None
    return side, dist


def action_from_assessment(side: Optional[str], dist: Optional[str]) -> str:
    """Fallback navigation action derived purely from target_state when the model omits an action line."""
    if side == "not visible":
        return "turn left 30 degrees"
    if side == "left":
        return "turn left 15 degrees"
    if side == "right":
        return "turn right 15 degrees"
    if side == "center":
        if dist in ("near", "very close"):
            return "stop"
        return "move forward 20 centimeters"
    return "move forward 20 centimeters"


def command_from_model_action(model_dir: str, side: Optional[str], dist: Optional[str]) -> str:
    """Trust the model's directional decision; let target_state inform only the magnitude."""
    if model_dir == "stop":
        return "stop"
    if model_dir == "move_forward":
        return "move forward 20 centimeters"
    if model_dir in ("turn_left", "turn_right"):
        # Wider sweep when searching (target lost), smaller correction when aligning to a visible target.
        deg = 30 if side in (None, "not visible") else 15
        verb = "turn left" if model_dir == "turn_left" else "turn right"
        return f"{verb} {deg} degrees"
    return "stop"


def normalize_direction(text: Optional[str]) -> Optional[str]:
    """Collapse any action phrase to a coarse direction category, ignoring numeric values."""
    if not text:
        return None
    s = text.lower()
    if "stop" in s:
        return "stop"
    if "turn" in s and "left" in s:
        return "turn_left"
    if "turn" in s and "right" in s:
        return "turn_right"
    if "forward" in s or "move" in s:
        return "move_forward"
    return None


def extract_model_action(text: str) -> Optional[str]:
    """Parse 'action: <action>' from VLM output and return its direction category."""
    cleaned = _cleanup_text(text)
    m = re.search(r"action\s*:\s*([^\n]+)", cleaned, re.IGNORECASE)
    if not m:
        return None
    return normalize_direction(m.group(1))


def extract_model_action_text(text: str) -> Optional[str]:
    """Backwards-compatible single-action accessor — returns the first Action line."""
    actions = extract_model_actions(text)
    return actions[0] if actions else None


def extract_model_actions(text: str) -> list[str]:
    """Return ALL VLM action strings, in the order they appear.

    Order of preference:
    1. Every explicit "Action: <text>" line (supports 1+ actions per response).
    2. Last non-empty line that is NOT the "Reason:" line (legacy free-form path).

    We deliberately do not fall back to the entire cleaned text — words like
    "stop"/"stopping" inside the Reason paragraph would otherwise be picked up
    by vlm_to_bridge_cmd and falsely turn every command into "stop".
    """
    cleaned = _cleanup_text(text)
    matches = re.findall(r"action\s*:\s*([^\n]+)", cleaned, re.IGNORECASE)
    actions = [m.strip().rstrip(".") for m in matches if m.strip()]
    if actions:
        return actions
    for line in reversed(cleaned.splitlines()):
        candidate = line.strip().rstrip(".")
        if not candidate:
            continue
        if candidate.startswith("reason:"):
            continue
        return [candidate]
    return []


def extract_reason_line(text: str) -> Optional[str]:
    """Return the content of the 'Reason:' line, if present."""
    cleaned = _cleanup_text(text)
    m = re.search(r"reason\s*:\s*([^\n]+)", cleaned, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().rstrip(".")


_LOST_KEYWORDS = ("not visible", "never seen", "never-seen", "lost", "out of view", "no longer visible")


def is_reason_lost(reason: Optional[str]) -> bool:
    """True when the Reason line indicates the target is currently lost / unseen."""
    if not reason:
        return False
    r = reason.lower()
    return any(kw in r for kw in _LOST_KEYWORDS)


_DIRECTION_TOKENS = (
    ("lost-was-right", "right"),
    ("lost-was-left", "left"),
    ("front-right", "right"),
    ("front-left", "left"),
    ("right", "right"),
    ("left", "left"),
    ("center", "center"),
)


_DIRECTION_TOKEN_MAP = dict(_DIRECTION_TOKENS)


def extract_reason_side(reason: Optional[str]) -> Optional[str]:
    """Return 'right' / 'left' / 'center' based on the direction keyword in the Reason line.

    Strategy: prefer the second comma-separated field (the structured 'direction'
    slot). Fall back to scanning the whole Reason for an enumerated token, but only
    match enumerated tokens; never let free-form prose like "left side of the desk"
    leak a direction.
    """
    if not reason:
        return None
    r = reason.lower()
    parts = [p.strip() for p in r.split(",")]
    if len(parts) >= 2 and parts[1] in _DIRECTION_TOKEN_MAP:
        return _DIRECTION_TOKEN_MAP[parts[1]]
    for token, side in _DIRECTION_TOKENS:
        if re.search(rf"(?:^|[\s,]){re.escape(token)}(?:$|[\s,])", r):
            return side
    return None


def turn_direction_of(cmd: str) -> Optional[str]:
    """Return 'left' / 'right' if cmd is a turn command, else None."""
    s = cmd.lower()
    if "turn left" in s:
        return "left"
    if "turn right" in s:
        return "right"
    return None


def flip_turn_direction(cmd: str, target_dir: str) -> str:
    """Rewrite a 'turn left/right N degrees' command to use target_dir, preserving magnitude."""
    other = "right" if target_dir == "left" else "left"
    return re.sub(rf"\bturn\s+{other}\b", f"turn {target_dir}", cmd, count=1, flags=re.IGNORECASE)


_VLM_TURN_RE = re.compile(
    r"turn\s+(?P<dir>left|right)\s+(?:by\s+)?(?P<val>[0-9]+(?:\.[0-9]+)?)\s*(?:deg(?:rees?)?|°)?",
    re.IGNORECASE,
)
_VLM_MOVE_RE = re.compile(
    r"(?:move|moving|go)\s+(?P<dir>forward|backward|back)\s+"
    r"(?P<val>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>m|meter|meters|cm|centimeter|centimeters)?",
    re.IGNORECASE,
)
_BRIDGE_DEFAULT_MAP = {
    "turn_left":    "turn left 30 degrees",
    "turn_right":   "turn right 30 degrees",
    "move_forward": "move forward 25 centimeters",
}


def vlm_to_bridge_cmd(action_text: Optional[str]) -> str:
    """Convert raw VLM action text into a bridge-parseable command string.

    Preserves the magnitude the VLM outputs when present; falls back to
    normalize_direction + fixed defaults when no numbers are found.
    """
    if not action_text:
        return "stop"

    s = action_text.lower()

    if "stop" in s:
        return "stop"

    turn_m = _VLM_TURN_RE.search(s)
    if turn_m:
        return f"turn {turn_m.group('dir')} {turn_m.group('val')} degrees"

    move_m = _VLM_MOVE_RE.search(s)
    if move_m:
        d = move_m.group("dir")
        d = "backward" if d == "back" else d
        val = move_m.group("val")
        raw_unit = (move_m.group("unit") or "").lower()
        unit = "centimeters" if raw_unit in ("cm", "centimeter", "centimeters") else "meters"
        return f"move {d} {val} {unit}"

    # No numeric value found — fall back to category + default magnitude
    category = normalize_direction(action_text)
    return _BRIDGE_DEFAULT_MAP.get(category or "", "stop")



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


def list_ordered_image_paths(images_dir: Path, pattern: str, sort_by: str) -> List[Path]:
    paths: List[Path] = []
    mtimes: dict[Path, int] = {}
    for path in images_dir.glob(pattern):
        if path.name.startswith("."):
            continue
        try:
            if not path.is_file():
                continue
            mtimes[path] = path.stat().st_mtime_ns
        except OSError:
            continue
        paths.append(path)

    if sort_by == "mtime":
        paths.sort(key=lambda p: (mtimes[p], p.name))
    else:
        paths.sort(key=_natural_key)
    return paths


def get_latest_image_paths(images_dir: Path, pattern: str, keep_last: int, sort_by: str) -> List[Path]:
    return list_ordered_image_paths(images_dir, pattern, sort_by)[-keep_last:]


_tty: Optional[IO[str]] = None
_header_lines: int = 0


def _setup_sticky_header(args: argparse.Namespace, instruction: str) -> None:
    """Pin a header at the top of the terminal using ANSI scroll region.

    Writes to /dev/tty so stdout (log file) is never polluted by escape codes.
    """
    global _tty, _header_lines
    try:
        _tty = io.open("/dev/tty", "w", encoding="utf-8")
    except OSError:
        return

    cols, rows = shutil.get_terminal_size((80, 24))
    sep = "─" * cols
    task_line = instruction.splitlines()[0][: cols - 11]
    lines = [
        sep,
        f"  Server : {args.host}:{args.port}   Images: {args.images_dir}",
        f"  Task   : {task_line}",
        sep,
    ]
    _header_lines = len(lines)

    buf = ["\033[2J\033[H"]          # clear screen, cursor home
    for line in lines:
        buf.append(line + "\n")
    buf.append(f"\033[{_header_lines + 1};{rows}r")  # scroll region below header
    buf.append(f"\033[{rows};1H")                     # cursor to bottom of scroll region

    _tty.write("".join(buf))
    _tty.flush()


def _teardown_sticky_header() -> None:
    global _tty
    if _tty is None:
        return
    try:
        _tty.write("\033[r")   # reset scroll region to full screen
        _tty.flush()
        _tty.close()
    except OSError:
        pass
    _tty = None


def _print_separator(label: str, request_index: int) -> None:
    print(f"\n========== request {request_index:04d} | {label} ==========", flush=True)


def _window_summary(image_paths: List[Path]) -> str:
    if not image_paths:
        return "0 frames"
    first = image_paths[0]
    last = image_paths[-1]
    parent = first.parent
    same_parent = all(p.parent == parent for p in image_paths)
    parent_text = str(parent) if same_parent else "mixed-dirs"
    return (
        f"{len(image_paths)} frames | dir={parent_text} | "
        f"first={first.name} | last={last.name}"
    )


def log_and_save_window(
    image_paths: List[Path],
    save_window_dir: Optional[Path],
    save_window_manifest: Optional[Path],
    request_index: int,
    verbose_window_log: bool = False,
) -> None:
    _print_separator("window", request_index)
    print(f"[window] {_window_summary(image_paths)}", flush=True)
    if verbose_window_log:
        for idx, path in enumerate(image_paths, start=1):
            print(f"[window] {idx:02d}. {path}", flush=True)

    if save_window_dir is not None:
        window_dir = save_window_dir / f"window_{request_index:04d}"
        window_dir.mkdir(parents=True, exist_ok=True)
        for idx, path in enumerate(image_paths, start=1):
            dst = window_dir / f"{idx:02d}_{path.name}"
            shutil.copy2(path, dst)
        meta = {
            "request_index": request_index,
            "ordered_paths": [str(p) for p in image_paths],
        }
        (window_dir / "window.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if save_window_manifest is not None:
        save_window_manifest.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "request_index": request_index,
            "ordered_paths": [str(p) for p in image_paths],
        }
        with save_window_manifest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


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
    parser.add_argument("--ingest-mode", choices=["window_scan", "sequential"], default="window_scan", help="window_scan repeatedly inspects the latest window; sequential buffers new images one by one in order")
    parser.add_argument("--interval-sec", type=float, default=1.0)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run one inference only")
    parser.add_argument("--bridge-cmd", type=str, default=None, help="Example: 'python test/navila_holosoma_bridge_v0.py --stdin --dry-run'")
    parser.add_argument("--dedupe", action="store_true", help="Do not resend the same normalized command twice in a row")
    parser.add_argument("--min-images", type=int, default=1)
    parser.add_argument("--require-full-window", action="store_true", help="Wait until the buffered window contains --keep-last real images before sending to the server")
    parser.add_argument("--save-window-dir", type=Path, default=None, help="Optional directory to save each 8-frame window sent to the server")
    parser.add_argument("--save-window-manifest", type=Path, default=None, help="Optional JSONL file that records the ordered image paths for every request")
    parser.add_argument("--verbose-window-log", action="store_true", help="Print every image path in the 8-frame window. By default only a one-line window summary is printed.")
    parser.add_argument("--no-vlm", action="store_true", help="Skip VLM inference; images are still collected and bridge/manual control work normally")
    parser.add_argument("--ignore-existing", action="store_true", help="In sequential mode, ignore images already present at startup and wait for fresh stream frames")
    args = parser.parse_args()

    if not args.images_dir.exists() or not args.images_dir.is_dir():
        raise SystemExit(f"Invalid images directory: {args.images_dir}")

    instruction = load_instruction(args.task, args.prompt_json)
    _setup_sticky_header(args, instruction)
    bridge = BridgeWriter(args.bridge_cmd)
    bridge.start()

    effective_min_images = args.keep_last if args.require_full_window else args.min_images

    last_sent_cmd: Optional[str] = None
    last_signature: Optional[str] = None
    last_displayed_dir: Optional[str] = None
    seen_paths: set[str] = set()
    sequential_buffer: Deque[Path] = deque(maxlen=args.keep_last)
    request_index = 0
    stop_streak = 0  # consecutive VLM responses whose only command was 'stop'
    STOP_CONFIRM_N = 3  # require this many consecutive stops before actually halting
    last_visible_side: Optional[str] = None  # 'right' / 'left' / 'center' from the last non-lost Reason
    search_dir_lock: Optional[str] = None    # 'right' / 'left' enforced while searching

    if args.ingest_mode == "sequential" and args.ignore_existing:
        existing_paths = list_ordered_image_paths(args.images_dir, args.pattern, args.sort_by)
        seen_paths.update(str(path.resolve()) for path in existing_paths)
        if existing_paths:
            print(
                f"[startup] ignoring {len(existing_paths)} existing images; waiting for fresh stream frames",
                flush=True,
            )

    try:
        while True:
            if args.ingest_mode == "sequential":
                ordered_paths = list_ordered_image_paths(args.images_dir, args.pattern, args.sort_by)
                new_paths = [p for p in ordered_paths if str(p.resolve()) not in seen_paths]
                if not new_paths:
                    time.sleep(args.interval_sec)
                    continue
                for path in new_paths:
                    seen_paths.add(str(path.resolve()))
                    sequential_buffer.append(path)
                image_paths = list(sequential_buffer)
                signature = "|".join(p.name for p in image_paths)
            else:
                image_paths = get_latest_image_paths(args.images_dir, args.pattern, args.keep_last, args.sort_by)
                if args.sort_by == "mtime":
                    signature = "|".join(f"{p.name}:{int(p.stat().st_mtime_ns)}" for p in image_paths)
                else:
                    signature = "|".join(p.name for p in image_paths)
                if signature == last_signature and not args.once:
                    time.sleep(args.interval_sec)
                    continue

            if len(image_paths) < effective_min_images:
                print(f"[wait] found {len(image_paths)} images, need at least {effective_min_images}", flush=True)
                if args.once:
                    return 1
                time.sleep(args.interval_sec)
                continue

            try:
                images = load_images(image_paths)
            except ImageWindowNotReady as exc:
                last_signature = None
                if args.ingest_mode == "sequential":
                    sequential_buffer = deque(
                        (path for path in sequential_buffer if path.exists() and path != exc.path),
                        maxlen=args.keep_last,
                    )
                print(
                    "[wait] image window changed while loading "
                    f"({exc.path.name}: {exc.original_error.__class__.__name__}); retrying",
                    flush=True,
                )
                if args.once:
                    return 1
                time.sleep(args.interval_sec)
                continue

            last_signature = signature
            request_index += 1
            log_and_save_window(
                image_paths,
                args.save_window_dir,
                args.save_window_manifest,
                request_index,
                verbose_window_log=args.verbose_window_log,
            )
            images = sample_to_n_frames(images, n=args.keep_last)

            if args.no_vlm:
                _print_separator("vlm", request_index)
                print("[no-vlm] skipping inference — use manual control console", flush=True)
            else:
                # Bare-bones path: trust the VLM's action line verbatim. No
                # magnitude inference, no target_state-derived fallback action.
                # If the action line is missing, default to stop for safety.
                print(f"[vlm] querying {args.host}:{args.port}...", flush=True)
                _t0 = time.time()
                raw_output = send_request(args.host, args.port, images, instruction)
                print(f"[vlm] response in {time.time() - _t0:.2f}s", flush=True)

                reason_line = extract_reason_line(raw_output)
                if reason_line:
                    print(f"Reason: {reason_line}", flush=True)

                action_texts = extract_model_actions(raw_output)
                if not action_texts:
                    final_cmds = ["stop"]
                else:
                    final_cmds = [vlm_to_bridge_cmd(a) for a in action_texts]

                # ---- Search-mode override ----
                # When the VLM reports the target as lost, force the robot to
                # rotate in place toward the side where it was last reliably
                # seen. Never alternate search direction, never advance forward
                # while searching.
                target_lost = is_reason_lost(reason_line)
                reason_side = extract_reason_side(reason_line)

                if not target_lost:
                    if reason_side in ("right", "left"):
                        last_visible_side = reason_side
                    search_dir_lock = None
                else:
                    stop_streak = 0  # don't accumulate stop confirmations while searching
                    if search_dir_lock is None:
                        if last_visible_side in ("right", "left"):
                            search_dir_lock = last_visible_side
                            origin = f"last_visible_side={last_visible_side}"
                        else:
                            vlm_turn = next(
                                (turn_direction_of(c) for c in final_cmds if turn_direction_of(c)),
                                None,
                            )
                            search_dir_lock = vlm_turn or "right"
                            origin = "VLM turn" if vlm_turn else "default=right"
                        print(
                            f"[search] target lost; locking search direction to {search_dir_lock} ({origin})",
                            flush=True,
                        )

                    forced = []
                    for cmd in final_cmds:
                        td = turn_direction_of(cmd)
                        if td is None:
                            # Drop forward/stop while searching — robot must spin in place.
                            print(f"[search] suppressing non-turn command while lost: {cmd}", flush=True)
                            continue
                        if td != search_dir_lock:
                            flipped = flip_turn_direction(cmd, search_dir_lock)
                            print(
                                f"[search] flipping wrong-way turn: {cmd} → {flipped}",
                                flush=True,
                            )
                            forced.append(flipped)
                        else:
                            forced.append(cmd)
                    if not forced:
                        forced = [f"turn {search_dir_lock} 30 degrees"]
                    final_cmds = forced

                # ---- Stop-hysteresis (skipped while searching above) ----
                vlm_says_stop = (
                    not target_lost
                    and len(final_cmds) == 1
                    and final_cmds[0] == "stop"
                )
                if vlm_says_stop:
                    stop_streak += 1
                    if stop_streak < STOP_CONFIRM_N:
                        held = "move forward 0.1 meters"
                        print(
                            f"[stop-hysteresis] stop #{stop_streak}/{STOP_CONFIRM_N} held; sending {held} instead",
                            flush=True,
                        )
                        final_cmds = [held]
                    else:
                        print(
                            f"[stop-hysteresis] stop confirmed ({stop_streak} in a row); forwarding stop",
                            flush=True,
                        )
                elif not target_lost:
                    stop_streak = 0

                for cmd in final_cmds:
                    print(f"Bridge COMMAND: {cmd}", flush=True)
                    if args.dedupe and cmd == last_sent_cmd:
                        continue
                    bridge.send(cmd)
                    last_sent_cmd = cmd

            if args.once:
                return 0

            time.sleep(args.interval_sec)
    finally:
        bridge.close()
        _teardown_sticky_header()


if __name__ == "__main__":
    raise SystemExit(main())
