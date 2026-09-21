#!/usr/bin/env python3
"""Phase 4 — D/F-band discovery (TEST on one volume).
For a volume: OCR a coarse stride of pages, print page -> (leading surnames +
any 'Littera <X>' header) so we can bracket where the D..F surname block sits.
Cache-first; safe because no OCR batch is running."""
import sys, re, json, os, subprocess, glob
sys.path.insert(0, '/workspace/agatha')
import agatha_cache as ac

VOL = sys.argv[1]
STRIDE = int(sys.argv[2]) if len(sys.argv) > 2 else 4
URL = 'http://host.docker.internal:8008/ocr-path'
PDIR = f'/workspace/agatha/cache/volumes/{VOL}/pages'
idx = json.load(open(f'/workspace/agatha/cache/volumes/{VOL}/index.json'))
n = len(idx)
probe = list(range(1, n + 1, STRIDE))
print(f"{VOL}: n_pages={n} probe_stride={STRIDE} -> {len(probe)} probe pages", flush=True)

def get_ocr(p):
    img = f'{PDIR}/{p:03d}.jpg'
    out = f'{img}.ocr.txt'
    if not (os.path.exists(img) and os.path.getsize(img) > 10000):
        try: ac.cmd_get(VOL, p)
        except SystemExit as e: print(f"  get p{p} fail {e}"); return None
    # split via PIL venv (reuse existing splits)
    subprocess.run(['/workspace/agatha/.venv_pil/bin/python', '/workspace/agatha/split_leaves.py', VOL, str(p)],
                   capture_output=True, text=True)
    txt = ''
    for s in ('L', 'R'):
        lf = f'{PDIR}/{p:03d}_{s}.ocr.txt'
        src = f'{PDIR}/{p:03d}_{s}.jpg'
        if os.path.exists(src) and os.path.getsize(src) > 10000:
            if not (os.path.exists(lf) and os.path.getsize(lf) > 0):
                subprocess.run(['curl', '-sS', '-X', 'POST', URL, '-H', 'Content-Type: application/json',
                                '-d', json.dumps({'path': src, 'model': 'small.safetensors'}), '-o', lf],
                               capture_output=True, text=True, timeout=300)
            if os.path.exists(lf) and os.path.getsize(lf) > 0:
                txt += open(lf, errors='ignore').read() + '\n'
    return txt

# serial is fine for a probe (~20 pages)
out = {}
for i, p in enumerate(probe):
    txt = get_ocr(p)
    if txt is None:
        out[p] = 'GETFAIL'; continue
    lines = [l.strip() for l in txt.split('\n') if l.strip()]
    # leading tokens (surname) — first ~8 short-ish tokens
    lead = []
    for l in lines[:12]:
        for t in re.findall(r"[A-Za-z][A-Za-z'’\-]{2,}", l):
            lead.append(t[0].upper())
            if len(lead) >= 6: break
        if len(lead) >= 6: break
    lit = re.findall(r'(?i)littera\s*([A-Z])', txt)
    out[p] = dict(lead=lead, lit=lit, sample=lines[:4])
    print(f"p{p:03d} lead={''.join(lead):6} lit={lit} :: {lines[:2]}", flush=True)
json.dump(out, open(f'/workspace/agatha/runs/frederic_zorokens/p4_probe_{VOL}.json', 'w'), indent=1)
print(f"WROTE p4_probe_{VOL}.json")
