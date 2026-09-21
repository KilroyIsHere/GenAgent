#!/usr/bin/env python3
"""Monitor-gated, self-healing state for the Frederic Zorokens search run.

Content-aware completion (does NOT trust run_frederic.py's own ocr_complete,
which is `fail==0` and is permanently False because 001_L is a blank title
page that Kraken returns EMPTY for -> os.remove -> no .ocr.txt -> counted a
"fail" -> ocr_complete stuck False -> the old gate would read `dead` and the
watcher would relaunch into an infinite loop).

Instead, completion = COUNT ACTUAL .ocr.txt FILES ON DISK (independent of the
process's self-report):
  A corpus volume is OCR-complete when its leaf coverage (ocr.txt files /
  expected leaves) >= 99%. A handful of legitimately-blank pages are terminal,
  not failures. The whole run is DONE when every corpus volume is complete AND
  the scan file (frederic_scan.json) exists.

Emits ONE deterministic line (NO timestamps) so the cron monitor wakes the
agent only on a state FLIP:
  phase: running | done | dead
    running = run_frederic.py alive
    done    = scan file exists AND every volume's on-disk OCR coverage >= 99%
    dead    = not done and not alive -> agent relaunches (resumable; on a
              relaunch the existing .ocr.txt files are skipped so coverage only
              goes up, so the gate is monotonic and cannot loop)

Self-heal (watcher prompt):
  running->dead : relaunch  python3 runs/frederic_zorokens/run_frederic.py
  running->done : Phase 3 (crop-verify STRONG/NEAR/GAP -> write report);
                  if zero STRONG -> Phase 4 multi-parish fallback (Antwerp,
                  index-first, city-scoped).
"""
import json, os, re, subprocess

RUN = '/workspace/agatha/runs/frederic_zorokens'
VOL_DIR = '/workspace/agatha/cache/volumes'
SCAN = f'{RUN}/frederic_scan.json'
# corpus: volume -> (lo_page, hi_page). Expected leaves = (hi-lo+1)*2 (L+R).
# NEW BAND (1667-1685): 6244 (1671-1685) + 6243 (1660-1671, 1667-1671 in window).
# The 1685-1712 band (6245/6246) is already certified in its own report; this
# gate fires when THIS band's volumes are OCR'd + scanned. Must match the
# orchestrator's WINS exactly.
CORPUS = {'6244': (1, 186), '6243': (1, 184)}
COVER = 0.99  # >= 99% on-disk OCR coverage counts as complete

def alive(pat):
    try:
        r = subprocess.run(['pgrep', '-f', pat], capture_output=True,
                           text=True, timeout=10)
        return any(p.strip() for p in r.stdout.split())
    except Exception:
        return False

def vol_complete(vol):
    lo, hi = CORPUS[vol]
    expected = (hi - lo + 1) * 2
    have = 0
    pd = f'{VOL_DIR}/{vol}/pages'
    if os.path.isdir(pd):
        for f in os.listdir(pd):
            if f.endswith('.ocr.txt'):
                have += 1
    # only count leaves in-window (all corpus leaves are in-window by design)
    return have >= expected * COVER, have, expected

def gate():
    scan_done = os.path.exists(SCAN)
    all_cov = all(vol_complete(v)[0] for v in CORPUS)
    if scan_done and all_cov:
        return 'done'
    if alive('run_frederic.py'):
        return 'running'
    return 'dead'

if __name__ == '__main__':
    # one deterministic line; coverage detail only on the done/edge states
    cov = {v: f'{vol_complete(v)[1]}/{vol_complete(v)[2]}' for v in CORPUS}
    print(f'phase={gate()} scan={os.path.exists(SCAN)} cov_6244={cov["6244"]} cov_6243={cov["6243"]}')
