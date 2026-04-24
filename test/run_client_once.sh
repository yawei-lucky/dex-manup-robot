#!/usr/bin/env bash

SCENE_NAME="${1:-forward}"
JSON="prompt_bag_area"

python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/${JSON}.json \
  --images-dir "test/navila_box_testset/${SCENE_NAME}" \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --once \
  --raw