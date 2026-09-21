#!/usr/bin/env python3
import json, subprocess
f = '/workspace/agatha/cache/volumes/6290/crops/018_L_half_2x.jpg'
r = subprocess.run(
    ['curl', '-s', '-X', 'POST', 'http://host.docker.internal:8008/ocr-path',
     '-H', 'Content-Type: application/json',
     '-d', json.dumps({'path': f, 'model': 'small.safetensors'})],
    capture_output=True, text=True)
print(r.stdout.strip() or r.stderr)
