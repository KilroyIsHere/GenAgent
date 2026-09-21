#!/usr/bin/env python3
"""Deterministic Phase-5 monitor gate. Emits ONE stable line (no timestamps):
  p5=<running|dead|done> vols=<done/39> strong=<n> near=<n> gap=<n>
Wakes the watcher only on a FLIP. done = orchestrator finished all 39 volumes.
Liveness = PID-file + /proc/<pid>/cmdline check (immune to pgrep -f self-match
where the caller argv contains the pattern string)."""
import os, json, subprocess
RUN = '/workspace/agatha/runs/frederic_zorokens'
STATE = f'{RUN}/p5_state.json'
PIDFILE = f'{RUN}/p5_run.pid'
TOTAL = 39

def _alive_via_pidfile():
    try:
        pid = int(open(PIDFILE).read().strip())
    except Exception:
        return False
    try:
        with open(f'/proc/{pid}/cmdline','rb') as f:
            cmd = f.read().decode('utf-8','ignore').replace('\x00',' ')
    except Exception:
        return False
    return 'p5_run.py' in cmd

def alive():
    # PID-file-only liveness. The orchestrator writes its pidfile at startup
    # and removes it on exit, so a missing pidfile genuinely means dead.
    # (Deliberately NO pgrep -f fallback: it self-matches any caller whose argv
    # contains the literal string 'p5_run.py', producing false 'running'.)
    if not os.path.exists(PIDFILE):
        return False
    return _alive_via_pidfile()

try:
    s = json.load(open(STATE))
except Exception:
    s = {}
done = s.get('done')
vols_done = sum(1 for v in s.get('vols',{}).values() if v.get('complete'))
strong = sum(v.get('n_strong',0) for v in s.get('vols',{}).values())
near = sum(v.get('n_near',0) for v in s.get('vols',{}).values())
gap = sum(v.get('n_gap',0) for v in s.get('vols',{}).values())
if done:
    phase = 'done'
elif alive():
    phase = 'running'
else:
    phase = 'dead'
print(f'p5={phase} vols={vols_done}/{TOTAL} strong={strong} near={near} gap={gap}')
