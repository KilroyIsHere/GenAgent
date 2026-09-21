#!/usr/bin/env python3
"""Full Zorrokens variant scan across 6290 per-leaf OCR (1712-1720)."""
import os, re

PD = '/workspace/agatha/cache/volumes/6290/pages'
# open-ended 18th-c. variant families (Zor/Zorke/Zorr)
pat = re.compile(r'zorr?e?k|zorck|zorok|zorons|zoron\b|zorke|zorrons|zorckens|zorrok',
                 re.I)
hits = []
for fn in sorted(os.listdir(PD)):
    if not fn.endswith('.ocr.txt'):
        continue
    p = os.path.join(PD, fn)
    lines = open(p, errors='replace').read().splitlines()
    for i, line in enumerate(lines):
        if pat.search(line):
            # context: month header candidates in same leaf
            ctx = lines[max(0, i-3):i+4]
            hits.append((fn, i, line, ctx))

print(f"TOTAL LINES MATCHING VARIANT PATTERN: {len(hits)}\n")
for fn, i, line, ctx in hits:
    print(f"--- {fn} line {i}: {line!r}")
    for c in ctx:
        if c != line:
            print(f"    ctx: {c!r}")
    print()
