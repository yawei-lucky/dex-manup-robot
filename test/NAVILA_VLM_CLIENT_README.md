# NaVILA VLM client integration guide

This note only covers the **top-layer VLM connection**:

- run NaVILA as a VLM server
- send image history + task text
- receive textual navigation commands
- optionally stream those commands into the existing bridge

It does **not** change the middle layer or low-level controller.

---

## 1. Goal

Use NaVILA as a **text-action generator**.

Input:
- recent image history
- task instruction text

Output:
- `turn left 15 degrees`
- `turn right 30 degrees`
- `move forward 50 centimeters`
- `stop`

The returned text can be sent directly to the existing bridge script.

---

## 2. Files

### Single-shot client
- `test/navila_min_client.py`

This script:
- reads 1 to N image files
- pads / samples them to 8 frames
- sends them to NaVILA VLM server
- receives raw text output
- normalizes it into a bridge-friendly command

### Folder-stream client
- `test/navila_folder_stream_client.py`

This script:
- watches a folder of incoming images
- repeatedly takes the latest frames
- sends them to NaVILA VLM server
- prints normalized textual commands continuously
- can optionally keep a bridge process alive and write commands into its stdin

### Mock dataset generator
- `test/generate_mock_navila_stream_dataset.py`

This script creates a synthetic test dataset for:
- `forward`
- `turn_left`
- `turn_right`
- `stop`

---

## 3. Expected overall flow

```text
camera frames / saved images
        |
        v
client adapter
        |
        v
NaVILA VLM server
        |
        v
text command
        |
        v
existing bridge script
```

Two practical modes are supported:

### Mode A: one-shot offline test
```text
saved 8 images -> navila_min_client.py -> one text command
```

### Mode B: folder-based continuous stream
```text
image folder -> navila_folder_stream_client.py -> continuous text commands -> bridge stdin
```

---

## 4. Start NaVILA VLM server

Run this inside the NaVILA-Bench / NaVILA environment:

```bash
python scripts/vlm_server.py --model_path /path/to/navila-llama3-8b-8f --port 54321
```

Notes:
- replace `/path/to/navila-llama3-8b-8f` with the actual checkpoint path
- default host is `localhost`
- default port in both clients is also `54321`

---

## 5. Run the minimal one-shot client

Example:

```bash
python test/navila_min_client.py \
  --host localhost \
  --port 54321 \
  --task "Go to the doorway." \
  --images frame1.jpg frame2.jpg frame3.jpg frame4.jpg frame5.jpg frame6.jpg frame7.jpg frame8.jpg \
  --raw
```

Example output:

```text
[raw] Turn left 15 degrees
turn left 15 degrees
```

Meaning:
- the first line is the raw NaVILA output
- the second line is the normalized command for the bridge

---

## 6. Run the folder-stream client

Example:

```bash
python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --task "Go to the doorway." \
  --images-dir test/mock_navila_stream_dataset/turn_left \
  --pattern "*.jpg" \
  --interval-sec 1.0 \
  --raw
```

Useful options:
- `--once`: run only one inference and exit
- `--dedupe`: do not resend the same normalized command twice in a row
- `--min-images N`: wait until at least `N` images exist in the folder
- `--keep-last N`: use the latest `N` files before pad/sample to 8 frames

One-shot folder test:

```bash
python test/navila_folder_stream_client.py \
  --task "Go to the doorway." \
  --images-dir test/mock_navila_stream_dataset/turn_left \
  --once \
  --raw
```

---

## 7. Keep the bridge alive and stream commands continuously

The existing bridge accepts one textual command per line from stdin.

The folder-stream client can launch the bridge once and keep writing commands into it.

Example:

```bash
python test/navila_folder_stream_client.py \
  --task "Go to the doorway." \
  --images-dir test/mock_navila_stream_dataset/turn_left \
  --interval-sec 1.0 \
  --dedupe \
  --bridge-cmd "python test/navila_holosoma_bridge_v0.py --stdin --dry-run"
```

This means:
- the bridge process is started once
- the client keeps watching the image folder
- each new normalized text command is written into the bridge stdin
- if `--dedupe` is enabled, repeated identical commands are suppressed

So for continuous use, you do **not** need to restart the bridge every time.

---

## 8. Pipe directly into the existing bridge for one-shot use

The smallest one-time connection is still:

```bash
python test/navila_min_client.py \
  --task "Go to the doorway." \
  --images frame1.jpg frame2.jpg frame3.jpg frame4.jpg frame5.jpg frame6.jpg frame7.jpg frame8.jpg \
| python test/navila_holosoma_bridge_v0.py --stdin --dry-run
```

Replace `--dry-run` when you are ready to use the real backend.

---

## 9. Input format used by the clients

Both clients send a JSON payload to the NaVILA VLM server through TCP socket.

Payload structure:

```json
{
  "images": ["<base64_jpeg>", "<base64_jpeg>", "..."],
  "query": "task text"
}
```

Protocol:
1. send 8-byte big-endian payload size
2. send JSON bytes
3. receive 8-byte response size
4. receive response body

This matches the released `scripts/vlm_server.py` protocol.

---

## 10. Frame handling

### `test/navila_min_client.py`
This client expects **1 to N** input image files.

Behavior:
- if fewer than 8 images are given, it pads to 8 frames
- if more than 8 images are given, it samples them down to 8 frames
- if exactly 8 images are given, it uses them directly

### `test/navila_folder_stream_client.py`
This client:
- scans a folder
- sorts images by modification time
- takes the latest `--keep-last` files
- pads / samples them to 8 frames
- sends them to the VLM server

This keeps the input format aligned with the released NaVILA evaluation idea of fixed-length image history.

---

## 11. Output normalization

The clients keep only bridge-friendly textual commands.

Accepted output forms include:
- `stop`
- `move forward 50 centimeters`
- `move forward 0.5 meters`
- `turn left 15 degrees`
- `turn right 30 degrees`

If NaVILA outputs something outside the supported pattern, the clients fall back to:

```text
stop
```

This is for safety and parser stability.

---

## 12. Generate a mock image-stream dataset

You can generate a synthetic dataset for quick testing:

```bash
python test/generate_mock_navila_stream_dataset.py
```

Default output:

```text
test/mock_navila_stream_dataset
```

Generated sequences:
- `forward/`
- `turn_left/`
- `turn_right/`
- `stop/`

Custom output directory:

```bash
python test/generate_mock_navila_stream_dataset.py --out-dir /your/path/mock_navila_stream_dataset
```

This dataset is useful for:
- client debugging
- bridge integration testing
- folder-stream loop verification

It is synthetic and only intended for pipeline validation.

---

## 13. Recommended test order

1. start NaVILA VLM server
2. generate the mock dataset or prepare your own 8 images
3. test `test/navila_min_client.py`
4. test `test/navila_folder_stream_client.py --once`
5. test `test/navila_folder_stream_client.py --bridge-cmd ...`
6. later replace folder images with your real camera export / cache

This order isolates problems cleanly.

---

## 14. Summary

For the current stage, the top-layer integration is already practical:

- NaVILA VLM server generates text commands
- `test/navila_min_client.py` supports one-shot offline testing
- `test/navila_folder_stream_client.py` supports folder-based continuous streaming
- the existing bridge can stay alive and continuously receive commands through stdin

So the remaining real-world step later is only to replace synthetic or saved images with your actual image source.
