#!/usr/bin/env python3
"""15-min heartbeat for the Frederic Zorokens run. Prints a compact status
line to stdout (delivered verbatim by the no_agent cron). Prints NOTHING when
the run is done (empty stdout -> nothing delivered), so it auto-stops.

Status: phase + per-volume download/OCR progress + elapsed + rough ETA +
failure count. No timestamps in a way that churns (ETA + counters are the
signal).
"""
import json, os, glob, subprocess, time

RUN = '/workspace/agatha/runs/frederic_zorokens'
PROG = f'{RUN}/ocr_progress.json'
WINS = {'6244': (1, 186), '6243': (1, 184)}  # NEW BAND 1667-1685
TOTAL_PAGES = sum(hi - lo + 1 for lo, hi in WINS.values())  # 370

def alive(pat):
    try:
        r = subprocess.run(['pgrep', '-f', pat], capture_output=True, text=True, timeout=10)
        return any(p.strip() for p in r.stdout.split())
    except Exception:
        return False

d = {}
try:
    d = json.load(open(PROG))
except Exception:
    pass

done = bool(d.get('done'))
if done:
    # nothing to post -> auto-stop heartbeat
    raise SystemExit(0)

vols = d.get('vols', {})
lines = []
dl_total = ocr_total = dl_fail = ocr_fail = 0
for vol, (lo, hi) in WINS.items():
    n = hi - lo + 1
    v = vols.get(vol, {})
    dld = v.get('dl_done', 0)
    ok = v.get('ocr_done', 0)
    ocr_complete = v.get('ocr_complete', False)
    if ocr_complete:
        lines.append(f"{vol}: DONE ({n}p)")
    elif ok > 0:
        lines.append(f"{vol}: OCR {ok}/{n*2} leaves")
    else:
        lines.append(f"{vol}: DL {dld}/{n}")
    dl_total += dld
    ocr_total += ok
    dl_fail += v.get('dl_fail', 0)
    ocr_fail += v.get('ocr_fail', 0)

elapsed = d.get('elapsed_s', 0)
# ETA: OCR is the long pole (~666 leaves). If any OCR started, estimate from it.
eta = ''
ocr_started = any(vols.get(v, {}).get('ocr_done', 0) > 0 or vols.get(v, {}).get('ocr_complete') for v in WINS)
if ocr_started and elapsed > 0:
    # leaves done so far
    leaves_done = sum(vols.get(v, {}).get('ocr_done', 0) for v in WINS)
    leaves_total = TOTAL_PAGES * 2
    if leaves_done > 0:
        rate = elapsed / leaves_done  # s per leaf
        rem = leaves_total - leaves_done
        eta = f" ETA ~{int(rem*rate/60)} min left (OCR)"
alive_flag = 'alive' if alive('run_frederic.py') else 'NOT RUNNING (watcher will relaunch)'
fails = dl_fail + ocr_fail
print(f"Frederic Zorokens search: {alive_flag}. " +
      " | ".join(lines) +
      f" | elapsed {int(elapsed/60)}m | fails {fails}" + eta)
