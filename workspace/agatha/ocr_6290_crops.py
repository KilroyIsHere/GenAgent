#!/usr/bin/env python3
"""Run Kraken small on the 6290 verification crops."""
import json, subprocess

files = [
    '/workspace/agatha/cache/volumes/6290/crops/018_L_bot.jpg',
    '/workspace/agatha/cache/volumes/6290/crops/018_L_top.jpg',
    '/workspace/agatha/cache/volumes/6290/crops/017_R_bot.jpg',
    '/workspace/agatha/cache/volumes/6290/crops/017_R_top.jpg',
]
for f in files:
    payload = json.dumps({"path": f, "model": "small.safetensors"})
    r = subprocess.run(
        ['curl', '-s', '-X', 'POST', 'http://host.docker.internal:8008/ocr-path',
         '-H', 'Content-Type: application/json', '-d', payload],
        capture_output=True, text=True)
    print(f"===== {f} =====")
    print(r.stdout.strip() or r.stderr)
    print()
