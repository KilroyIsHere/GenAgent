#!/usr/bin/env python3
"""Scan Kraken OCR outputs for ZORROKENS variants (raw OCR, no correction).
Usage: scan_zorrozens.py  [vol pages...]   (no args = all cached OCR files)
Prints candidate lines; ZORROKENS is a rare surname so any 'zor' + 'k/en'
shape is printed. Confidence tiers are assigned during review, not here.
"""
import re, glob, os, sys

# variants the small model may emit for Zorrokens: zorroken(s), zorro,
# zorsen, zorrkens, zorokens, zoorkeens, zorrkens... keep it wide:
PATTERN = re.compile(r"do[ur]{1,2}[ek]?\s*[a-z]{0,8}", re.I)  # rough first pass
TIGHT = re.compile(r"do[ur]r?k?e?n", re.I)

vols = []
args = sys.argv[1:]
if args:
    vols = []
    i = 0
    while i < len(args):
        if args[i].isdigit():
            v = args[i]; i += 1
            pages = []
            while i < len(args) and args[i].isdigit():
                pages.append(args[i]); i += 1
            vols.append((v, pages))
        else:
            i += 1
else:
    vols = [None]

for vol in vols:
    if vol is None:
        files = sorted(glob.glob("/workspace/agatha/cache/volumes/*/pages/*.ocr.txt"))
        for f in files:
            for ln, line in enumerate(open(f, errors="replace"), 1):
                if TIGHT.search(line):
                    print(f"{f}:{ln}: {line.rstrip()}")
    else:
        v, pages = vol
        for p in pages:
            for s in ("L", "R"):
                f = f"/workspace/agatha/cache/volumes/{v}/pages/{p:03d}_{s}.ocr.txt"
                if not os.path.exists(f):
                    continue
                for ln, line in enumerate(open(f, errors="replace"), 1):
                    if TIGHT.search(line):
                        print(f"{f}:{ln}: {line.rstrip()}")
print("=== done ===")
