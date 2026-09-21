#!/workspace/.venv/bin/python
"""Split cached agatha spreads into left/right leaves for per-leaf Kraken OCR.
Usage: split_leaves.py VOL PAGES...
"""
import sys
import os
from PIL import Image


def split(vol, page):
    pdir = f"/workspace/agatha/cache/volumes/{vol}/pages"
    src = f"{pdir}/{page:03d}.jpg"
    if not os.path.exists(src):
        print(f"MISS {src}")
        return
    img = Image.open(src)
    w, h = img.size
    mid = w // 2
    left = img.crop((0, 0, mid, h))
    right = img.crop((mid, 0, w, h))
    lp = f"{pdir}/{page:03d}_L.jpg"
    rp = f"{pdir}/{page:03d}_R.jpg"
    if not os.path.exists(lp):
        left.save(lp, quality=90)
    if not os.path.exists(rp):
        right.save(rp, quality=90)
    print(f"OK {vol} {page:03d} {w}x{h}")


vol = sys.argv[1]
pages = []
for a in sys.argv[2:]:
    pages += [int(x) for x in a.replace(",", " ").split()]
for p in pages:
    split(vol, p)
