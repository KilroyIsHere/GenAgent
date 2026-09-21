#!/usr/bin/env python3
"""Split cached page JPGs into L/R leaves for OCR (no PIL needed)."""
import struct, sys, subprocess, os

def jpg_size(path):
    with open(path, 'rb') as f:
        d = f.read()
    i = 2
    while i < len(d) - 8:
        if d[i] == 0xFF and d[i+1] in (0xC0, 0xC2, 0xC3):
            h, w = struct.unpack('>HH', d[i+5:i+9])
            return w, h
        i += 1
    raise ValueError('no SOF found')

vol = '6260'
for n in (205, 206, 204):
    src = f'cache/volumes/{vol}/pages/{n}.jpg'
    w, h = jpg_size(src)
    for side, box in (('L', f'0,0,{w//2},{h}'), ('R', f'{w//2},0,{w - w//2},{h}')):
        out = f'cache/crops/{vol}/{n}_{side}.png'
        if os.path.exists(out):
            continue
        subprocess.run(['magick', src, '-crop', box, '+repage', out], check=True)
    print(n, w, h)
