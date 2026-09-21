#!/workspace/agatha/.venv_pil/bin/python
"""Find the exact Zorckens line on 6290 p18_L by strip-OCRing the lower half."""
import json, subprocess, os
from PIL import Image

f = '/workspace/agatha/crop_6290_strips.py'
src = os.path.dirname(f)  # not needed
img = Image.open('/workspace/agatha/cache/volumes/6290/pages/018_L.jpg')
w, h = img.size
# lower half in 10 strips of 150px each
strips = []
for i in range(10):
    top = int(h*0.50) + i*150
    bot = top + 150
    c = img.crop((0, top, w, min(bot, h)))
    c = c.resize((c.width*3, c.height*3), Image.LANCZOS)
    p = f'/workspace/agatha/cache/volumes/6290/crops/018_L_strip{i:02d}.jpg'
    c.save(p)
    strips.append(p)

for p in strips:
    r = subprocess.run(
        ['curl', '-s', '-X', 'POST', 'http://host.docker.internal:8008/ocr-path',
         '-H', 'Content-Type: application/json',
         '-d', json.dumps({'path': p, 'model': 'small.safetensors'})],
        capture_output=True, text=True)
    print(f"===== {os.path.basename(p)} =====")
    print(r.stdout.strip() or '(empty)')
    print()
