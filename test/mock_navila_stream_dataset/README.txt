Mock NaVILA stream dataset

This is a synthetic image-stream dataset for testing:
- test/navila_min_client.py
- test/navila_folder_stream_client.py
- your existing bridge

Folders:
- forward
- turn_left
- turn_right
- stop

Each folder contains 8 JPG frames named frame_01.jpg ... frame_08.jpg

Example:
python test/navila_min_client.py --task "Go to the doorway." --images mock_navila_stream_dataset/turn_left/*.jpg --raw

These are synthetic G1-like first-person mock images, not real NaVILA or Unitree captures.
