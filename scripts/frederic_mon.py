#!/usr/bin/env python3
"""Monitor-gated, self-healing state for the Frederic Zorokens search run.

ONE watched process (run_frederic.py) does download -> OCR -> scan (token-stream
slot-aware) -> writes runs/frederic_zorokens/frederic_scan.json. Emits ONE
deterministic line (NO timestamps) so the cron monitor wakes the agent only on
a state FLIP:

  phase:   running | done | dead
    running = run_frederic.py alive (download/OCR/scan in progress)
    done    = process exited AND scan file exists AND per-volume leaf coverage
              >= 98% (content-aware; a blank title page -> EMPTY OCR is tolerated,
              so a single blank page no longer blocks completion)
    dead    = not running, not done -> agent relaunches (resumable)

Self-heal (handled by the agent when phase=dead):
  relaunch  cd /workspace/agatha && python3 runs/frederic_zorokens/run_frederic.py
  (cache-first, skips already-downloaded pages and already-OCR'd leaves)
When phase=done the agent runs Phase 3 (crop-verify STRONG/NEAR candidates +
write report); if zero STRONG/NEAR -> Phase 4 multi-parish fallback.

NOTE: the gate does NOT rely on ocr_progress.json's 'done' flag (the
orchestrator sets it from fail==0, which a blank page breaks). It computes
completion directly from the scan file + on-disk leaf coverage.
"""
import json, os, glob, subprocess

RUN = '/workspace/agatha/runs/frederic_zorokens'
VOL_DIR = '/workspace/agatha/cache/volumes'
SCAN = f'{RUN}/frederic_scan.json'
# Same corpus/windows as scan_frederic.py + run_frederic.py (NEW BAND 1667-1685)
CORPUS = [('6244', 1, 186), ('6243', 1, 184)]
COVERAGE = 0.98

def alive(pat):
    try:
        r = subprocess.run(['pgrep', '-f', pat], capture_output=True, text=True, timeout=10)
        return any(p.strip() for p in r.stdout.split())
    except Exception:
        return False

def coverage_ok():
    for vol, lo, hi in CORPUS:
        total = (hi - lo + 1) * 2
        have = len(glob.glob(f'{VOL_DIR}/{vol}/pages/*.ocr.txt'))
        if have < COVERAGE * total:
            return False
    return True

def gate():
    if alive('run_frederic.py'):
        return 'running'
    if os.path.exists(SCAN) and coverage_ok():
        return 'done'
    return 'dead'

if __name__ == '__main__':
    print(f'phase={gate()}')
