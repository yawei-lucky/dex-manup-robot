# NaVILA VLM client integration guide

This note only covers the **top-layer VLM connection**:

- run NaVILA as a VLM server
- send image history + task text
- receive one textual navigation command
- optionally pipe that command into the existing bridge

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

### Existing client
- `test/navila_min_client.py`

This script:
- reads 1 to N image files
- pads / samples them to 8 frames
- sends them to NaVILA VLM server
- receives raw text output
- normalizes it into a bridge-friendly command

---

## 3. Expected overall flow

```text
camera frames / saved images
        |
        v
test/navila_min_client.py
        |
        v
NaVILA VLM server
        |
        v
single textual command
        |
        v
existing bridge script
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
- default port in the minimal client is also `54321`

---

## 5. Run the minimal client

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

## 6. Pipe directly into the existing bridge

The existing bridge accepts one textual command per line from stdin.

So the smallest connection is:

```bash
python test/navila_min_client.py \
  --task "Go to the doorway." \
  --images frame1.jpg frame2.jpg frame3.jpg frame4.jpg frame5.jpg frame6.jpg frame7.jpg frame8.jpg \
| python test/navila_holosoma_bridge_v0.py --stdin --dry-run
```

Replace `--dry-run` when you are ready to use the real backend.

---

## 7. Input format used by the client

The client sends a JSON payload to the NaVILA VLM server through TCP socket.

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

## 8. Frame handling in the client

`test/navila_min_client.py` expects **1 to N** input images.

Behavior:
- if fewer than 8 images are given, it pads to 8 frames
- if more than 8 images are given, it samples them down to 8 frames
- if exactly 8 images are given, it uses them directly

This matches the released NaVILA evaluation idea of using fixed-length image history.

---

## 9. Output normalization

The client keeps only bridge-friendly textual commands.

Accepted output forms include:
- `stop`
- `move forward 50 centimeters`
- `move forward 0.5 meters`
- `turn left 15 degrees`
- `turn right 30 degrees`

If NaVILA outputs something outside the supported pattern, the client falls back to:

```text
stop
```

This is for safety and parser stability.

---

## 10. Current limitation

The current client reads image files from disk.

That is intentional for the first integration step.

So the present version is:
- good for offline testing
- good for recorded image sequences
- good for prompt / output-format debugging

The next step later is simple:
- replace `--images ...` with recent frames from a live image buffer

The socket protocol and output normalization can stay unchanged.

---

## 11. Recommended first test

1. start NaVILA VLM server
2. prepare 8 images from your own forward-facing camera view
3. run `test/navila_min_client.py`
4. check the raw output with `--raw`
5. verify the final normalized command can be parsed by your bridge

This should be done before any live camera integration.

---

## 12. Summary

For the current stage, the required top-layer integration is already minimal:

- NaVILA VLM server generates one text command
- `test/navila_min_client.py` is the adapter
- the existing bridge consumes the final text

So the only missing part later is replacing disk images with a live image source.
