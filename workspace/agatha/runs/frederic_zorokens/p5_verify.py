#!/usr/bin/env python3
"""PHASE 5 PRE-LAUNCH VERIFICATION — no downloads, no OCR, no state writes.
Checks:
  1. import chain (p5_run + scan_frederic symbols actually used)
  2. VOLS list internal consistency (count, unique ids, cached vs new)
  3. every NEW vol has a real index.json with a page list
  4. every CACHED vol has pages in cache (zero-OCR re-scan ready)
  5. init-manifest vol set == VOLS new set (nothing orphaned / dropped)
  6. estimate_band self-test (chronological + whole-window + no-year cases)
  7. scan_frederic exposes YEAR_RE, scan_one, line_pass, tokenize_leaf, detect_structure
Prints PASS/FAIL per check and a final summary.
"""
import os, sys, json, importlib
sys.path.insert(0, '/workspace/agatha')
sys.path.insert(0, '/workspace/agatha/runs/frederic_zorokens')

FAIL = []
def chk(name, ok, detail=''):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ''))
    if not ok: FAIL.append(name)

# ---- 1. import chain ----
import p5_run as p5
import scan_frederic as sf
print("import p5_run + scan_frederic OK")

# ---- 7. matcher symbols ----
need = ['YEAR_RE', 'scan_one', 'line_pass', 'tokenize_leaf', 'detect_structure']
miss = [s for s in need if not hasattr(sf, s)]
chk("scan_frederic exposes used symbols", not miss, "missing=%s" % miss if miss else "all present")

# ---- 2. VOLS internal consistency ----
ids = [v[0] for v in p5.VOLS]
chk("VOLS count == N_VOLS", p5.N_VOLS == len(p5.VOLS), f"len={len(p5.VOLS)}")
chk("VOLS ids unique", len(set(ids)) == len(ids), f"{len(ids)} entries")
chk("CACHED subset of VOLS", set(p5.CACHED) <= set(ids), f"CACHED={sorted(p5.CACHED)}")
new = [i for i in ids if i not in p5.CACHED]
chk("CACHED count == 6", len(p5.CACHED) == 6, f"{len(p5.CACHED)}")
chk("NEW count == 33", len(new) == 33, f"{len(new)}")
# every vol has a window tuple
badwin = [v for v in p5.VOLS if not (1 <= v[3] <= 3200 and v[3] <= v[4])]
chk("every VOLS row has sane window", not badwin, f"bad={badwin}" if badwin else f"39 rows OK")

# ---- 5. init-manifest set == VOLS new set ----
mf_path = '/workspace/agatha/runs/frederic_zorokens/p5_new_register_manifests.json'
mf = set()
if os.path.exists(mf_path):
    raw = json.load(open(mf_path))
    if isinstance(raw, dict):
        mf = set(raw.keys())
    elif isinstance(raw, list):
        mf = set(str(x) for x in raw)
chk("init-manifest exists", os.path.exists(mf_path))
chk("init-manifest set == NEW set", mf == set(new),
    "extra=%s missing=%s" % (sorted(mf - set(new))[:5], sorted(set(new) - mf)[:5]) if mf != set(new) else "33/33 match")

# ---- 3. NEW vols have real index.json ----
bad_idx = []
for v in new:
    ip = f'/workspace/agatha/cache/volumes/{v}/index.json'
    if not os.path.exists(ip):
        bad_idx.append((v, 'no index.json')); continue
    try:
        ix = json.load(open(ip))
        n = len(ix) if isinstance(ix, list) else len(ix.get('pages', []))
        if n <= 0:
            bad_idx.append((v, 'empty index'))
    except Exception as e:
        bad_idx.append((v, f'parse {e}'))
chk("all NEW vols have non-empty index.json", not bad_idx,
    f"bad={bad_idx[:8]}" if bad_idx else f"{len(new)}/33 OK")

# ---- 4. CACHED vols have pages in cache ----
bad_cache = []
for v in p5.CACHED:
    pd = f'/workspace/agatha/cache/volumes/{v}/pages'
    njpg = len([f for f in os.listdir(pd) if f.endswith('.jpg')]) if os.path.isdir(pd) else -1
    if njpg <= 0:
        bad_cache.append((v, njpg))
chk("all CACHED vols have pages (zero-OCR re-scan ready)", not bad_cache,
    f"missing={bad_cache}" if bad_cache else "6/6 have pages")

# ---- 6. estimate_band self-test ----
import tempfile
cases = []
# (desc, n, grid_year_map {page->year}, win_lo, win_hi, expect_fallback)
def mktmp(files):
    d = tempfile.mkdtemp()
    for rel, yr in files.items():
        full = os.path.join(d, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(f"Doe {yr} Jan {yr} " + ("FREDERIC " if yr in (1690,1691) else "") + "x\n")
    return d
# we test estimate_band by monkey-patching PAGE_DIR to a temp tree
real_page_dir = p5.PAGE_DIR
p5.PAGE_DIR = mktmp({'6100/pages/001_L.ocr.txt': 1650, '6100/pages/005_L.ocr.txt': 1660,
                     '6100/pages/009_L.ocr.txt': 1670, '6100/pages/013_L.ocr.txt': 1680,
                     '6100/pages/017_L.ocr.txt': 1690, '6100/pages/021_L.ocr.txt': 1700,
                     '6100/pages/025_L.ocr.txt': 1710, '6100/pages/029_L.ocr.txt': 1720})
# vol 6100, n=30, grid stride 4 -> pages 1,5,9,13,17,21,25,29
grid = list(range(1, 31, 4))
band, fb = p5.estimate_band('6100', grid, 30, 1667, 1712)
# years 1650..1720 straddle 1667-1712; in-window pages 9..25 -> band ~[3..31] clamped, no fallback
p5.PAGE_DIR = real_page_dir
chk("estimate_band: straddling chronological -> banded, no fallback",
    (band[0] >= 1 and band[1] <= 30) and not fb and band[1] > band[0],
    f"band={band} fb={fb}")

# whole-volume-in-window case: years all 1680-1710
p5.PAGE_DIR = mktmp({'6101/pages/001_L.ocr.txt': 1680, '6101/pages/005_L.ocr.txt': 1690,
                     '6101/pages/009_L.ocr.txt': 1700, '6101/pages/013_L.ocr.txt': 1710})
band, fb = p5.estimate_band('6101', list(range(1, 14, 4)), 13, 1667, 1712)
p5.PAGE_DIR = real_page_dir
chk("estimate_band: whole vol in-window -> [1,n] no fallback",
    band == [1, 13] and not fb, f"band={band} fb={fb}")

# no-year case -> whole volume, fallback
p5.PAGE_DIR = mktmp({'6102/pages/001_L.ocr.txt': 0, '6102/pages/005_L.ocr.txt': 0})
band, fb = p5.estimate_band('6102', list(range(1, 6, 4)), 5, 1667, 1712)
p5.PAGE_DIR = real_page_dir
chk("estimate_band: no year tokens -> [1,n] fallback (no-miss)",
    band == [1, 5] and fb, f"band={band} fb={fb}")

print()
print("=== SUMMARY: %s ===" % ("ALL PASS" if not FAIL else f"FAILURES: {FAIL}"))
sys.exit(1 if FAIL else 0)
