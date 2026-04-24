# NaVILA VLM client integration guide

This note only covers the current top-layer VLM integration in this repo.

It documents how to:
- run NaVILA as a VLM server
- feed image history into the current client
- test with a fixed 8-image folder
- test with discretized video frames
- test with continuously appended images
- optionally send normalized commands into the existing bridge

It does not change the middle layer or low-level controller.

---

## 1. Current entry points

### Main client
- `test/navila_folder_stream_client.py`

This is the current client to use.
It supports:
- `--prompt-json` for JSON prompt files
- one-shot testing with `--once`
- continuous folder watching
- sequential ingest for one-by-one incoming frames
- raw VLM output printing
- saving the exact 8-frame window sent to the server
- optional bridge streaming through stdin

### Video to frame conversion
- `test/video_to_frame_stream.py`

This script converts a video into time-ordered JPG frames.
It can either:
- extract all frames first for offline testing
- or write frames one by one with delays to simulate a live image stream

### Example dataset / prompt area
- `test/navila_box_testset/`

Typical contents in this folder:
- `test/navila_box_testset/video/` for source videos
- `test/navila_box_testset/<video_stem>/` for extracted frames
- `test/navila_box_testset/navila_square_box_prompt.json` or another prompt JSON

`test/navila_min_client.py` is no longer the recommended path and is not covered here.

---

## 2. Overall flow

```text
saved images / extracted video frames / continuously appended frames
        |
        v
navila_folder_stream_client.py
        |
        v
NaVILA VLM server
        |
        v
normalized text command
        |
        v
optional bridge stdin
```

---

## 3. Start NaVILA VLM server

Run this inside the NaVILA / NaVILA-Bench environment:

```bash
python scripts/vlm_server.py --model_path /path/to/navila-llama3-8b-8f --port 54321
```

Notes:
- replace `/path/to/navila-llama3-8b-8f` with the actual checkpoint path
- the client examples below assume `localhost:54321`

---

## 4. Prompt JSON format

The current client reads the `prompt` field from a JSON file.
A typical file looks like this:

```json
{
  "task": "find and approach the teddy bear",
  "target_object": "teddy bear",
  "prompt": "Task: find and approach the teddy bear.\n\n..."
}
```

Notes:
- `prompt` is the field actually sent to the VLM server
- `task` and `target_object` are kept for organization and readability
- if `--prompt-json` is given, it takes priority over `--task`

---

## 5. Convert one video into a same-name frame folder

Example:

```bash
python test/video_to_frame_stream.py \
  --video test/navila_box_testset/video/forward.mp4 \
  --output-dir test/navila_box_testset \
  --use-video-stem-dir \
  --sample-fps 2.0 \
  --clear-output
```

This creates:

```text
test/navila_box_testset/forward/
```

with files like:

```text
frame_000001_t000000000ms.jpg
frame_000002_t000000500ms.jpg
...
```

So the extracted frame folder name matches the video stem.

---

## 6. One-shot test with one folder containing 8 ordered images

This is the simplest and most stable offline test.

```bash
python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/navila_square_box_prompt.json \
  --images-dir test/navila_box_testset/forward \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --once \
  --raw
```

What this does:
- reads the folder once
- orders images by filename
- takes the latest 8 images
- sends them to the VLM server once
- prints the raw output and the normalized command

Typical output shape:

```text
[window] frames sent to server in order:
  01. ...
  ...
  08. ...
[raw]
target_state: right, far away
action: turn right by 15 degrees
command: turn right 15 degrees
```

---

## 7. Continuous test with one-by-one incoming images

This mode is useful when images are appended gradually into a folder.

```bash
python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/navila_square_box_prompt.json \
  --images-dir test/navila_box_testset/forward \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.5 \
  --raw
```

Key behavior:
- new frames are discovered one by one
- the client buffers them internally in order
- nothing is sent until the buffer contains 8 real images
- after that, every new image updates the sliding 8-frame window

This is the current recommended mode for continuously appended frame folders.

---

## 8. Simulate a live image stream from a video

You can combine the video extractor with the folder client.

Terminal 1: NaVILA server

Terminal 2: folder client

```bash
python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/navila_square_box_prompt.json \
  --images-dir test/navila_box_testset/forward \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.5 \
  --raw
```

Terminal 3: stream frames into that folder

```bash
python test/video_to_frame_stream.py \
  --video test/navila_box_testset/video/forward.mp4 \
  --output-dir test/navila_box_testset \
  --use-video-stem-dir \
  --sample-fps 2.0 \
  --stream \
  --stream-interval-sec 0.5 \
  --clear-output
```

This produces a file-based live stream without any extra image socket.

---

## 9. Save exactly which 8 images were sent to the server

The client can record the actual 8-frame window used for each request.

### Save copied windows
```bash
--save-window-dir test/navila_box_testset/sent_windows
```

This creates directories like:

```text
test/navila_box_testset/sent_windows/window_0001/
test/navila_box_testset/sent_windows/window_0002/
```

Each window folder contains:
- the 8 images in server order
- `window.json`

### Save a JSONL manifest
```bash
--save-window-manifest test/navila_box_testset/sent_windows.jsonl
```

This appends one record per request with the ordered image paths.

Combined example:

```bash
python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/navila_square_box_prompt.json \
  --images-dir test/navila_box_testset/right \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --once \
  --raw \
  --save-window-dir test/navila_box_testset/sent_windows \
  --save-window-manifest test/navila_box_testset/sent_windows.jsonl
```

---

## 10. Optional bridge integration

The existing bridge accepts one text command per line from stdin.

The folder client can keep the bridge alive and send commands into it.

```bash
python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/navila_square_box_prompt.json \
  --images-dir test/navila_box_testset/forward \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.5 \
  --dedupe \
  --bridge-cmd "python test/navila_holosoma_bridge_v0.py --stdin --dry-run"
```

Important:
- the displayed line is printed as `command: ...`
- the actual payload sent to the bridge is still only the normalized command text
- debug-only information such as target state is not sent to the bridge

---

## 11. Current output behavior

The client prints three kinds of information.

### A. Window debug
Before sending a request, it prints the 8 images sent to the server in order.

### B. Raw VLM output
With `--raw`, it prints the raw text returned by the VLM.
This can be one line or multiple lines.

### C. Final normalized action
The final displayed action is printed as:

```text
command: turn right 15 degrees
```

The bridge still receives:

```text
turn right 15 degrees
```

So the `command:` prefix is only for display.

---

## 12. Filename and ordering notes

Recommended naming for extracted or hand-prepared images:

```text
frame_000001.jpg
frame_000002.jpg
...
frame_000008.jpg
```

or the timestamped form generated by `video_to_frame_stream.py`:

```text
frame_000001_t000000000ms.jpg
frame_000002_t000000500ms.jpg
...
```

Recommendations:
- prefer `--sort-by name` when filenames are monotonic and time-ordered
- keep image format consistent inside one test folder
- if your command uses `--pattern "*.jpg"`, PNG files in the same folder will be ignored
- avoid ad-hoc names such as many `copy`, `copy 2`, `copy 3` variants for formal testing

---

## 13. Minimal recommended workflows

### Workflow A: offline verification from an extracted video
1. convert one video into a same-name frame folder
2. run the one-shot 8-image test with `--once`
3. inspect the raw output and saved window if needed

### Workflow B: continuous file-based streaming
1. start the NaVILA server
2. start the folder client in sequential mode
3. append frames gradually into the watched folder
4. optionally connect the bridge

---

## 14. Summary

For the current repo state, the practical and maintained path is:
- use `test/navila_folder_stream_client.py`
- use `test/video_to_frame_stream.py` for video discretization
- use `--once` for fixed 8-image tests
- use `--ingest-mode sequential --require-full-window` for continuous appended-image tests
- use `--save-window-dir` / `--save-window-manifest` when you need exact server-window traceability

So the remaining real-world step later is only to replace saved frames with your actual image source while keeping the same client interface.
