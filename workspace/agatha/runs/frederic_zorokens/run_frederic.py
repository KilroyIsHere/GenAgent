#!/usr/bin/env python3
"""SINGLE end-to-end orchestrator for the Frederic Zorokens search:
   DOWNLOAD (1685-1712 window) -> OCR (per-leaf, 10-way Kraken small) -> SCAN
(fuzzy). One watched process so the cron watcher has a single
alive/dead/done gate to self-heal. Fully resumable + cache-first: re-runs
skip already-downloaded pages and already-OCR'd leaves.

  NEW BAND (1667-1685) — extension after the 1685-1712 band completed:
    6244: pages 1-186  (1671-1685, whole volume in window)
    6243: pages 1-184  (1660-1671; 1667-1712 window needs the 1667-1671 tail,
                        whole-volume scan for safety at the boundary)
  The 1685-1712 band (6245 1-233, 6246 1-100) is DONE and reported in STATUS.md;
  its state is preserved in ocr_progress_1685.json / frederic_scan_1685.json.
  A fresh ocr_progress.json is used for this band so the completion gate and
  the watcher's monitor read only the new band.

Progress -> ocr_progress.json (the watcher's source of truth).
"""
import os, sys, re, json, time, subprocess, glob, concurrent.futures as cf
sys.path.insert(0, '/workspace/agatha')
import agatha_cache as ac

RUN = '/workspace/agatha/runs/frederic_zorokens'
PROG = f'{RUN}/ocr_progress.json'
URL = 'http://host.docker.internal:8008/ocr-path'
PIL_PY = '/workspace/agatha/.venv_pil/bin/python'
SPLIT = '/workspace/agatha/split_leaves.py'
WINS = {'6244': (1, 186), '6243': (1, 184)}
# Structure is now detected PER-PAGE by scan_frederic.py (filia/filius vs
# infans marker counting), which handles a mid-volume cleric change. 6243/6244
# are St Andries baptism registers of the same era as 6245 (child-after-Infans)
# or 6246 (child-first-filius); per-page detection makes the slot parser
# reliable for both. Mark all reliable (the per-page detector is authoritative).
SLOT_RELIABLE = {'6244': True, '6243': True}
DATE_RANGES = {'6244': '1671-1685', '6243': '1660-1671 (1667-1671 in window)'}
# Human-readable meaning per volume (parish + register type + coverage).
# The user reviews STATUS.md and needs each volume's number to carry what it is.
VOL_DESC = {
    '6244': 'St-Andries baptism register (1671–1685)',
    '6243': 'St-Andries baptism register (1660–1671; 1667–1671 in window)',
    '6245': 'St-Andries baptism register (1685–1706)',
    '6246': 'St-Andries baptism register (1706–1727; 1706–~1715 scanned)',
    '6222': 'St-Andries baptism INDEX (1628–1671; 1667–1671 sliver in window)',
    '6223': 'St-Andries baptism INDEX (1671–1727)',
}
import status
status.init()
t0 = time.time()

def save(s):
    s['elapsed_s'] = round(time.time() - t0, 1)
    s['ts'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    json.dump(s, open(PROG, 'w'), indent=1)

state = {'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
         'vols': {}, 'scan_done': False, 'done': False}
if os.path.exists(PROG):
    try:
        prev = json.load(open(PROG))
        if prev.get('done'):
            print('ALREADY DONE — nothing to do', flush=True)
            sys.exit(0)
        state['vols'] = prev.get('vols', {})
        state['scan_done'] = prev.get('scan_done', False)
    except Exception:
        pass

# ---------------- PHASE A: DOWNLOAD ----------------
def dl_one(vol, p):
    dst = f'/workspace/agatha/cache/volumes/{vol}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return 'cache'
    for a in range(3):
        try:
            ac.cmd_get(vol, p)
            if os.path.exists(dst) and os.path.getsize(dst) > 10000:
                return 'ok'
        except SystemExit:
            if a == 0:
                try:
                    ac.cmd_ensure()
                except SystemExit:
                    pass
        except Exception:
            pass
        if os.path.exists(dst + '.part'):
            try: os.unlink(dst + '.part')
            except OSError: pass
        time.sleep(2 * (a + 1))
    return 'FAIL'

print('=== PHASE A: download ===', flush=True)
for vol, (lo, hi) in WINS.items():
    vw = state['vols'].setdefault(vol, {'dl_done': 0, 'dl_fail': 0, 'dl_fails': []})
    print(f'-- {vol} window {lo}-{hi}', flush=True)
    for p in range(lo, hi + 1):
        r = dl_one(vol, p)
        if r in ('ok', 'cache'):
            vw['dl_done'] += 1
        else:
            vw['dl_fail'] += 1
            vw['dl_fails'].append(f'p{p}')
            print(f'  DL FAIL {vol} p{p}', flush=True)
        if vw['dl_done'] % 25 == 0:
            save(state)
            print(f'  {vol} dl {vw["dl_done"]}/{hi - lo + 1} ({time.time()-t0:.0f}s)', flush=True)
    save(state)
    print(f'-- {vol} download: {vw["dl_done"]}/{hi - lo + 1} ok, {vw["dl_fail"]} fail', flush=True)

# ---------------- PHASE B: OCR per-leaf ----------------
def ocr_leaf(vol, leaf):
    img = f'/workspace/agatha/cache/volumes/{vol}/pages/{leaf}.jpg'
    out = f'/workspace/agatha/cache/volumes/{vol}/pages/{leaf}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return 'cache'
    if not (os.path.exists(img) and os.path.getsize(img) > 10000):
        return 'NODL'
    last = 'EMPTY'
    for a in range(3):
        r = subprocess.run(
            ['curl', '-sS', '-X', 'POST', URL,
             '-H', 'Content-Type: application/json',
             '-d', json.dumps({'path': img, 'model': 'small.safetensors'}),
             '-o', out],
            capture_output=True, text=True, timeout=300)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return 'ok'
        if os.path.exists(out):
            os.remove(out)
        last = f'EMPTY {r.stderr[:60]}'
        time.sleep(3 * (a + 1))
    return last

print('=== PHASE B: OCR per-leaf ===', flush=True)
# Load scan_frederic.py in-process so we can run a per-volume scan immediately
# after each volume's OCR completes (pushes results to STATUS before the next
# volume starts — the user reviews STATUS.md, not the transcript).
import importlib.util
_spec = importlib.util.spec_from_file_location('scanmod', f'{RUN}/scan_frederic.py')
scanmod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scanmod)

def finish_vol(vol, ocr_done, ocr_total, skip=False):
    """Run a per-volume scan (only this volume's OCR'd files) and write its
    STATUS FINISH block with every candidate detailed. Marked UNSURE if the
    slot parser is not reliable for this volume's structure."""
    sub = f'{RUN}/scan_{vol}.json'
    try:
        scanmod.main(only_vol=vol, out_path=sub)
        scan = json.load(open(sub))
    except Exception as e:
        print(f'  STATUS: per-volume scan {vol} FAILED ({e})', flush=True)
        scan = {'hits': [], 'gaps': [], 'n_ocr_files_scanned': 0, 'n_entries': 0}
    date_range = DATE_RANGES.get(vol, '')
    unreliable = (not SLOT_RELIABLE.get(vol, True))
    note = ''
    if unreliable:
        note = (f'slot parser NOT reliable for {vol} (different register structure — '
                f'child-first "filius" layout). 0-hit is NOT a reliable no-hit until '
                f're-scanned with the child-first/line filter. PASS 2 line-net result is '
                f'the safety net here.')
    status.finish(vol, date_range, date_range, scan, ocr_done, ocr_total,
                  unsure=unreliable, note=note, desc=VOL_DESC.get(vol, ''))
    print(f'  STATUS: {vol} FINISH block written to STATUS.md', flush=True)

for vol, (lo, hi) in WINS.items():
    vw = state['vols'].setdefault(vol, {})
    if vw.get('ocr_complete'):
        print(f'== {vol} OCR already complete — skip', flush=True)
        ocr_total = sum(1 for s in ('L','R') for p in range(lo, hi+1)
                        if os.path.exists(f'/workspace/agatha/cache/volumes/{vol}/pages/{p:03d}_{s}.ocr.txt'))
        finish_vol(vol, ocr_total, ocr_total, skip=True)
        continue
    leaves = []
    for p in range(lo, hi + 1):
        need = []
        for s in ('L', 'R'):
            img = f'/workspace/agatha/cache/volumes/{vol}/pages/{p:03d}_{s}.jpg'
            if not (os.path.exists(img) and os.path.getsize(img) > 10000):
                need.append(p)
        if need:
            subprocess.run([PIL_PY, SPLIT, vol, str(p)], capture_output=True, text=True)
        for s in ('L', 'R'):
            leaves.append(f'{p:03d}_{s}')
    print(f'== {vol} OCR {len(leaves)} leaves ==', flush=True)
    # --- STATUS: START marker for this volume (before OCR) ---
    date_range = DATE_RANGES.get(vol, '')
    status.start(vol, f'{lo}-{hi}', date_range, len(leaves), desc=VOL_DESC.get(vol, ''))
    ok = fail = 0
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(ocr_leaf, vol, l): l for l in leaves}
        for fut in cf.as_completed(futs):
            r = fut.result()
            if r in ('ok', 'cache'):
                ok += 1
            else:
                fail += 1
                vw.setdefault('ocr_fails', []).append(f'{futs[fut]}:{r}')
                print(f'  OCR FAIL {futs[fut]}: {r}', flush=True)
            if (ok + fail) % 50 == 0:
                save(state)
                print(f'  {vol} ocr {ok + fail}/{len(leaves)} ({time.time()-t0:.0f}s)', flush=True)
    vw['ocr_done'] = ok
    vw['ocr_fail'] = fail
    # Content-aware completion gate: a legitimately-blank page (Kraken EMPTY ->
    # no .ocr.txt) is terminal, not a failure. Treat OCR as complete when
    # >=98% of leaves have a .ocr.txt file (never trust fail==0).
    ocr_files = sum(1 for l in leaves
                    if os.path.exists(f'/workspace/agatha/cache/volumes/{vol}/pages/{l}.ocr.txt')
                    and os.path.getsize(f'/workspace/agatha/cache/volumes/{vol}/pages/{l}.ocr.txt') > 0)
    coverage = ocr_files / len(leaves) if leaves else 0.0
    vw['ocr_complete'] = coverage >= 0.98
    vw['ocr_coverage'] = round(coverage, 4)
    save(state)
    print(f'== {vol} OCR: {ok}/{len(leaves)} ok, {fail} fail, coverage={coverage:.3f} '
          f'(complete={vw["ocr_complete"]}) ==', flush=True)
    # --- STATUS: FINISH + full per-volume results (immediately after OCR,
    #     BEFORE the next volume begins) ---
    finish_vol(vol, ok, len(leaves))

# ---------------- PHASE C: SCAN ----------------
print('=== PHASE C: fuzzy scan ===', flush=True)
r = subprocess.run([sys.executable, f'{RUN}/scan_frederic.py'],
                   capture_output=True, text=True, timeout=600)
print(r.stdout[-4000:], flush=True)
if r.returncode != 0:
    print('SCAN ERR:', r.stderr[-1200:], flush=True)
state['scan_done'] = os.path.exists(f'{RUN}/frederic_scan.json')
all_complete = all(v.get('ocr_complete') for v in state['vols'].values())
state['done'] = state['scan_done'] and all_complete
save(state)
print(f'\nDONE. scan_done={state["scan_done"]} ocr_all_complete={all_complete} '
      f'ocr_fails={sum(v.get("ocr_fail", 0) for v in state["vols"].values())} '
      f'dl_fails={sum(v.get("dl_fail", 0) for v in state["vols"].values())} '
      f'elapsed={state["elapsed_s"]}s', flush=True)
