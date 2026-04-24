#!/usr/bin/env bash

NAME="center_mid"
OUTDIR="test/navila_box_testset/static/$NAME"
SRC="test/navila_box_testset/static/$NAME.jpg"

if [ ! -f "$SRC" ]; then
  echo "Source image not found: $SRC"
  exit 1
fi

mkdir -p "$OUTDIR"

for i in $(seq 1 8); do
  cp "$SRC" "$OUTDIR/frame_$(printf '%06d' "$i").jpg"
done

echo "Done: $OUTDIR"