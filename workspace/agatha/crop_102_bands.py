#!/usr/bin/env python3
"""Crop 6141 p102 (Kraken EMPTY x4) into 4 wide horizontal bands for the
vision aux-model tie-break. Wide bands > narrow (Kraken/vision lesson)."""
from PIL import Image
im = Image.open('/workspace/agatha/cache/volumes/6141/pages/102.jpg')
w, h = im.size
print('page size:', w, h)
n = 4
overlap = 30
for i in range(n):
    top = max(0, h * i // n - (overlap if i > 0 else 0))
    bot = min(h, h * (i + 1) // n + (overlap if i < n - 1 else 0))
    im.crop((0, top, w, bot)).save(
        f'/workspace/agatha/cache/volumes/6141/pages/102_band{i+1}.png')
    print(f'band {i+1}: rows {top}-{bot}')
print('done')
