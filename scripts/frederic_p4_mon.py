#!/usr/bin/env python3
"""Deterministic Phase-4 monitor gate. Emits ONE stable line (no timestamps):
  p4=<running|dead|done> vols=<done/total> hits=<n> strong=<n>
Wakes the watcher only on a FLIP. done = orchestrator finished all volumes.
Liveness = PID-file + /proc/<pid>/cmdline check (immune to pgrep -f self-match
where the caller argv contains the pattern string)."""
import os, json, subprocess
RUN = '/workspace/agatha/runs/frederic_zorokens'
STATE = f'{RUN}/p4_state.json'
PIDFILE = f'{RUN}/p4_run.pid'
TOTAL = 20

def _alive_via_pidfile():
    try:
        pid = int(open(PIDFILE).read().strip())
    except Exception:
        return False
    try:
        with open(f'/proc/{pid}/cmdline','rb') as f:
            cmd = f.read().decode('utf-8','ignore').replace('\x00',' ')
    except Exception:
        return False  # /proc gone => process dead
    return 'p4_run.py' in cmd

def alive():
    # PID-file first (authoritative); pgrep fallback (no PIDFILE yet on first start).
    if os.path.exists(PIDFILE):
        return _alive_via_pidfile()
    try:
        r = subprocess.run(['pgrep','-f','p4_run.py'],capture_output=True,text=True)
        return bool(r.stdout.strip())
    except Exception:
        return False

try:
    s = json.load(open(STATE))
except Exception:
    s = {}
done = s.get('done')
vols_done = sum(1 for v in s.get('vols',{}).values() if v.get('complete'))
hits = sum(v.get('n_hits',0) for v in s.get('vols',{}).values())
strong = sum(v.get('n_strong',0) for v in s.get('vols',{}).values())
if done:
    phase = 'done'
elif alive():
    phase = 'running'
else:
    phase = 'dead'
print(f'p4={phase} vols={vols_done}/{TOTAL} hits={hits} strong={strong}')
