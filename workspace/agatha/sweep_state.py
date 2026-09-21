#!/usr/bin/env python3
"""Monitor-gated, self-healing state for the Phase-5 ZORROK* sweep + 6355 slice.

Emits ONE deterministic line (no timestamps) so the cron monitor only wakes the
agent when a state FLIPS. Gate values are coarse enums (not counters) so the
line stays STABLE during normal progress (a volume finishing does NOT change the
line — the agent reads results.json directly when it wakes for a real event).

  sweep:     running | dead | done
  sanfelipe: running | down   | done

Desired transitions (and what the agent should do — see the cron prompt):
  sweep running->dead : relaunch full_sweep.py (resumable)
  sweep running->done : report sweep complete
  sanfelipe running->done : report 6355 slice complete
  sanfelipe running->down : relaunch sanfelipe_6355.py (safe: it self-waits for the sweep)
"""
import json, os, glob, subprocess

RESULTS = '/workspace/agatha/lookup/full_sweep_results.json'
SF_FLAG = '/workspace/agatha/lookup/sanfelipe_done'
SF_PAGES = 206
TOTAL = 13

def _alive(pattern):
    try:
        r = subprocess.run(['pgrep', '-f', pattern], capture_output=True, text=True, timeout=10)
        pids = [p for p in r.stdout.split() if p.strip()]
        return len(pids) > 0
    except Exception:
        return False

def sweep_gate():
    done = 0
    try:
        d = json.load(open(RESULTS))
        done = sum(1 for r in d.get('completed', {}).values() if r.get('done'))
    except Exception:
        done = 0
    if done >= TOTAL:
        return 'done'
    if _alive('full_sweep.py'):
        return 'running'
    return 'dead'

def sanfelipe_gate():
    if os.path.exists(SF_FLAG):
        return 'done'
    try:
        n = len(glob.glob('/workspace/agatha/cache/volumes/6355/pages/*.ocr.txt'))
        if n >= SF_PAGES:
            return 'done'
    except Exception:
        pass
    if _alive('sanfelipe_6355.py'):
        return 'running'
    return 'down'

if __name__ == '__main__':
    print(f'sweep={sweep_gate()} sanfelipe={sanfelipe_gate()}')
