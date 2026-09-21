#!/usr/bin/env python3
"""15-min heartbeat for the Frederic Zorokens run.

Counts ON-DISK OCR files (live progress, not the orchestrator's progress flag,
which can lag), uses the same content-aware completion gate as the monitor
(scan file + leaf coverage >= 98%; a blank title page is tolerated). Prints a
compact status line to stdout (delivered verbatim by the no_agent cron). Prints
NOTHING when the run is done (empty stdout -> nothing delivered), so it
auto-stops. No timestamps that churn.
"""
import json, os, glob, subprocess

RUN = '/workspace/agatha/runs/frederic_zorokens'
VOL_DIR = '/workspace/agatha/cache/volumes'
PROG = f'{RUN}/ocr_progress.json'
SCAN = f'{RUN}/frederic_scan.json'
WINS = {'6244': (1, 186), '6243': (1, 184)}   # NEW BAND 1667-1685
TOTAL_PAGES = sum(hi - lo + 1 for lo, hi in WINS.values())   # 370
COVERAGE = 0.98

def alive(pat):
    try:
        r = subprocess.run(['pgrep', '-f', pat], capture_output=True, text=True, timeout=10)
        return any(p.strip() for p in r.stdout.split())
    except Exception:
        return False

def on_disk(vol):
    return len(glob.glob(f'{VOL_DIR}/{vol}/pages/*.ocr.txt'))

def coverage_ok():
    return all(on_disk(v) >= COVERAGE * (hi - lo + 1) * 2 for v, (lo, hi) in WINS.items())

# Completion gate (same as monitor): scan file present + coverage met.
if os.path.exists(SCAN) and coverage_ok():
    raise SystemExit(0)   # nothing to post -> auto-stop

# Progress from disk (live), per volume.
lines = []
ocr_fail = 0
for vol, (lo, hi) in WINS.items():
    n = hi - lo + 1
    leaves = on_disk(vol)
    total = n * 2
    if leaves >= COVERAGE * total:
        lines.append(f"{vol}: OCR {leaves}/{total} (done)")
    elif leaves > 0:
        lines.append(f"{vol}: OCR {leaves}/{total}")
    else:
        lines.append(f"{vol}: DL")
    # OCR fail count from progress (best-effort)
    try:
        ocr_fail += json.load(open(f'{PROG}')).get('vols', {}).get(vol, {}).get('ocr_fail', 0)
    except Exception:
        pass

elapsed = 0
try:
    elapsed = json.load(open(PROG)).get('elapsed_s', 0)
except Exception:
    pass

# ETA from leaves done.
leaves_done = sum(on_disk(v) for v in WINS)
leaves_total = TOTAL_PAGES * 2
eta = ''
if 0 < leaves_done < leaves_total and elapsed > 0:
    rate = elapsed / leaves_done
    rem = leaves_total - leaves_done
    eta = f" ETA ~{int(rem * rate / 60)} min left (OCR)"

alive_flag = 'alive' if alive('run_frederic.py') else 'NOT RUNNING (watcher will relaunch)'
print(f"Frederic Zorokens: {alive_flag}. " + " | ".join(lines) +
      f" | elapsed {int(elapsed/60)}m | ocr_fails {ocr_fail}" + eta)
