#!/usr/bin/env python3
"""Monitor-gated, self-healing state for the Phase-5 ZORROK* sweep + 6355 slice
+ audit certifier.

Emits THREE deterministic lines (no counters/timestamps) so the cron monitor
only wakes the agent on a real FLIP:

  sweep=<running|dead|done> sanfelipe=<running|down|done>
  audit13=<pending|clean|failures>
  legacy=<pending|clean|failures>

Semantics:
  sweep=done        -> all 13 index volumes processed (audit still certifies).
  audit13=clean     -> audit verified EVERY page of the 13 vols has a jpg +
                       non-empty OCR (0 unresolved) = no-miss certified. This
                       is the real completion signal for the index work.
  audit13=failures  -> pages persistently unreadable after 3 retries; they are
                       flagged (never skipped) in lookup/sweep_failures.json
                       with IIIF URL + image + ocr path; report them DOUBTFUL.
  dead / down       -> relaunch the resumable script (audit also recovers holes).

The 6355 slice is gated on the AUDIT certifying the 13 vols (audit13_done
EXISTS), so sanfelipe only starts after the index pages are actually read —
Kraken OOM discipline.
"""
import json, os, glob, subprocess

RESULTS = '/workspace/agatha/lookup/full_sweep_results.json'
SF_FLAG = '/workspace/agatha/lookup/sanfelipe_done'
AUDIT13 = '/workspace/agatha/lookup/audit13_done'
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

def audit13_gate():
    try:
        s = open(AUDIT13).read().strip()
        return 'clean' if s == '0' else 'failures'
    except Exception:
        return 'pending'

def legacy_gate():
    """Legacy St Joris volumes (6290-6293): ON-DEMAND ONLY (user decision
    2026-09-16 — St Joris is closed, don't re-check every run). Emitted
    ONLY when its flag file exists (i.e. `sweep_audit.py --legacy` was run
    on demand); otherwise the line is omitted so the monitor stays 2-line
    and stable."""
    flag = '/workspace/agatha/lookup/audit_legacy_done'
    if not os.path.exists(flag):
        return None
    try:
        s = open(flag).read().strip()
        return 'clean' if s == '0' else 'failures'
    except Exception:
        return 'failures'

if __name__ == '__main__':
    print(f'sweep={sweep_gate()} sanfelipe={sanfelipe_gate()}')
    print(f'audit13={audit13_gate()}')
    lg = legacy_gate()
    if lg is not None:
        print(f'legacy={lg}')
