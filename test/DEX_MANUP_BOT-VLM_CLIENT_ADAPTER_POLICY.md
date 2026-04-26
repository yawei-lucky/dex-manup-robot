# NaVILA VLM Client for Holosoma MuJoCo

This README describes the current workflow for using NaVILA as a high-level VLM/VLA navigation module with the Holosoma MuJoCo G1 simulation.

The main workflow is:

```text
Holosoma MuJoCo camera -> image stream folder -> sequential VLM client -> NaVILA server -> navigation command
```

The older folder-only tests are kept at the end as backup/debug workflows.

---

## 1. Recommended workflow: Holosoma MuJoCo camera stream

### Terminal 1: start the NaVILA VLM server

```bash
conda activate navila-server
cd ~/NaVILA-Bench

python scripts/vlm_server.py \
  --model_path ~/models/navila-llama3-8b-8f \
  --port 54321
```

Expected server-side message:

```text
VLM Server listening on localhost:54321
```

---

### Terminal 2: start Holosoma MuJoCo and write camera frames

```bash
cd ~/robotics/holosoma

bash scripts/run_navila_mujoco_stream.sh
```

This script should enable the MuJoCo camera stream and write images to:

```text
runtime/navila_mujoco_stream
```

Check that images are being generated:

```bash
ls -lh runtime/navila_mujoco_stream | tail
```

Expected image filenames look like:

```text
frame_000001_t0000000000ms.jpg
frame_000002_t0000000500ms.jpg
frame_000003_t0000001000ms.jpg
```

The compiled Holosoma/MuJoCo camera name should be:

```text
robot_head_nav
```

---

### Terminal 3: start the dex-manup-robot VLM client

```bash
cd ~/robotics/dex-manup-robot

bash test/run_navila_mujoco_client.sh
```

This script reads the MuJoCo camera image stream and sends 8-frame windows to the NaVILA server using sequential mode.

The core command is:

```bash
python test/navila_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/prompt_bag_area.json \
  --images-dir ~/robotics/holosoma/runtime/navila_mujoco_stream \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.2 \
  --save-window-dir runtime/navila_windows \
  --raw
```

Recommended output checks:

```text
[window] frames sent to server in order:
  01. ...
  ...
  08. ...

[raw]:
target_state: center, far away
action: move forward 50 centimeters

command: move forward 50 centimeters
```

At this stage, do not connect real motion execution until the raw VLM outputs are reasonable and stable.

---

## 2. Recommended startup order

Use three terminals.

### Terminal 1

```bash
conda activate navila-server
cd ~/NaVILA-Bench

python scripts/vlm_server.py \
  --model_path ~/models/navila-llama3-8b-8f \
  --port 54321
```

### Terminal 2

```bash
cd ~/robotics/holosoma
bash scripts/run_navila_mujoco_stream.sh

ls -lh runtime/navila_mujoco_stream | tail
```

### Terminal 3

```bash
cd ~/robotics/dex-manup-robot
bash test/run_navila_mujoco_client.sh
```

---

## 3. Expected data flow

```text
Holosoma MuJoCo
  - G1 simulation
  - robot_head_nav camera
  - writes ordered JPG frames

dex-manup-robot client
  - watches image folder
  - sequentially buffers new images
  - waits until 8 real frames are available
  - sends the 8-frame window to NaVILA server
  - normalizes VLM text into command format

NaVILA server
  - receives images + prompt
  - returns raw VLM navigation output
```

---

## 4. Important client parameters

### `--ingest-mode sequential`

Reads newly generated images one by one. This is the correct mode for MuJoCo camera streaming.

### `--require-full-window`

The client waits until it has 8 real images before sending a request.

### `--keep-last 8`

The client maintains an 8-frame history window.

### `--sort-by name`

Images are sorted by filename. This matches generated names such as:

```text
frame_000001_t0000000000ms.jpg
frame_000002_t0000000500ms.jpg
```

### `--save-window-dir`

Saves every 8-frame window sent to the VLM server. This is useful for debugging exactly what the model saw.

---

## 5. Holosoma stream script

Recommended script path:

```text
~/robotics/holosoma/scripts/run_navila_mujoco_stream.sh
```

Example content:

```bash
#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOLOSOMA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$HOLOSOMA_ROOT"

source scripts/source_mujoco_setup.sh

export NAVILA_MUJOCO_STREAM=1
export NAVILA_MUJOCO_CAMERA="${NAVILA_MUJOCO_CAMERA:-robot_head_nav}"
export NAVILA_MUJOCO_STREAM_DIR="${NAVILA_MUJOCO_STREAM_DIR:-${HOLOSOMA_ROOT}/runtime/navila_mujoco_stream}"
export NAVILA_MUJOCO_WIDTH="${NAVILA_MUJOCO_WIDTH:-640}"
export NAVILA_MUJOCO_HEIGHT="${NAVILA_MUJOCO_HEIGHT:-480}"
export NAVILA_MUJOCO_FRAME_INTERVAL="${NAVILA_MUJOCO_FRAME_INTERVAL:-0.5}"
export NAVILA_MUJOCO_CLEAN_START="${NAVILA_MUJOCO_CLEAN_START:-1}"

mkdir -p "$NAVILA_MUJOCO_STREAM_DIR"

echo "[NAVILA_MUJOCO] HOLOSOMA_ROOT=$HOLOSOMA_ROOT"
echo "[NAVILA_MUJOCO] STREAM_DIR=$NAVILA_MUJOCO_STREAM_DIR"
echo "[NAVILA_MUJOCO] CAMERA=$NAVILA_MUJOCO_CAMERA"

python src/holosoma/holosoma/run_sim.py robot:g1-29dof
```

---

## 6. dex-manup-robot client script

Recommended script path:

```text
~/robotics/dex-manup-robot/test/run_navila_mujoco_client.sh
```

Example content:

```bash
#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$DEX_ROOT"

HOLOSOMA_ROOT="${HOLOSOMA_ROOT:-${HOME}/robotics/holosoma}"

IMAGES_DIR="${IMAGES_DIR:-${HOLOSOMA_ROOT}/runtime/navila_mujoco_stream}"
WINDOW_DIR="${WINDOW_DIR:-${DEX_ROOT}/runtime/navila_windows}"
PROMPT_JSON="${PROMPT_JSON:-test/navila_box_testset/prompt_bag_area.json}"

mkdir -p "$WINDOW_DIR"

echo "[NAVILA_CLIENT] DEX_ROOT=$DEX_ROOT"
echo "[NAVILA_CLIENT] HOLOSOMA_ROOT=$HOLOSOMA_ROOT"
echo "[NAVILA_CLIENT] IMAGES_DIR=$IMAGES_DIR"
echo "[NAVILA_CLIENT] WINDOW_DIR=$WINDOW_DIR"
echo "[NAVILA_CLIENT] PROMPT_JSON=$PROMPT_JSON"

python test/navila_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json "$PROMPT_JSON" \
  --images-dir "$IMAGES_DIR" \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.2 \
  --save-window-dir "$WINDOW_DIR" \
  --raw
```

If Holosoma is not under `~/robotics/holosoma`, override the path:

```bash
HOLOSOMA_ROOT=/path/to/holosoma bash test/run_navila_mujoco_client.sh
```

Or directly specify the image directory:

```bash
IMAGES_DIR=/path/to/navila_mujoco_stream bash test/run_navila_mujoco_client.sh
```

---

## 7. Prompt file

Recommended prompt file:

```text
test/navila_box_testset/prompt_bag_area.json
```

The first-layer task should focus on navigating to the target area, not fine-grained object manipulation.

Example task intent:

```text
Find and approach the table area with the black bag-like object on it.
```

The VLM should output:

```text
target_state: <left/right/center/not visible>, <far away/near/very close>
action: <one navigation action>
```

The final normalized client output is:

```text
command: <normalized command>
```

---

## 8. Optional: bridge to execution

Only enable this after the VLM outputs are stable.

Dry-run example:

```bash
python test/navila_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/prompt_bag_area.json \
  --images-dir ~/robotics/holosoma/runtime/navila_mujoco_stream \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.2 \
  --save-window-dir runtime/navila_windows \
  --bridge-cmd "python test/navila_holosoma_bridge_v0.py --stdin --dry-run" \
  --dedupe \
  --raw
```

Remove `--dry-run` only after confirming safety.

---

# Backup workflows: folder-based tests

These workflows are kept for debugging the VLM and prompt without running MuJoCo.

---

## A. One-shot test with an 8-image folder

Use this when a folder already contains at least 8 ordered images.

```bash
python test/navila_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/prompt_bag_area.json \
  --images-dir test/navila_box_testset/forward \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --once \
  --raw
```

---

## B. Sequential folder test

Use this when another process keeps adding images into a folder.

```bash
python test/navila_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/prompt_bag_area.json \
  --images-dir test/navila_box_testset/video/forward \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.2 \
  --raw
```

---

## C. Repeat one static image into 8 frames

```bash
mkdir -p test/navila_box_testset/static/center_far

src="test/navila_box_testset/static.jpg"

for i in $(seq 1 8); do
  cp "$src" "test/navila_box_testset/static/center_far/frame_$(printf '%06d' "$i").jpg"
done
```

Then run:

```bash
python test/navila_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/prompt_bag_area.json \
  --images-dir test/navila_box_testset/static/center_far \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --once \
  --raw
```

---

## D. Save the exact 8-frame window

```bash
python test/navila_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/prompt_bag_area.json \
  --images-dir test/navila_box_testset/forward \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --once \
  --save-window-dir runtime/navila_windows_debug \
  --raw
```

This saves the exact images sent to the server, which is useful for diagnosing unexpected VLM outputs.

---

## Notes

- `navila_min_client.py` is deprecated and should not be used.
- Prefer `navila_stream_client.py` for both static folder tests and MuJoCo camera stream tests.
- Use `--ingest-mode sequential` for live image streams.
- Use `--once` for fixed folder tests.
- Keep the high-level VLM command slow and stable first; low-level Holosoma control runs separately.
