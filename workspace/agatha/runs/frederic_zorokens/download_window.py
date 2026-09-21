#!/usr/bin/env python3
"""Download the 1685-1712 window for the Frederic Zorokens search.
Volumes: 6245 (1-233, whole volume) + 6246 (1-100). Cache-first, resumable.
Logs per-page progress to progress.json for the watcher.
"""
import os, sys, time, json
sys.path.insert(0, '/workspace/agatha')
import agatha_cache as ac

RUN = '/workspace/agatha/runs/frederic_zorokens'
PROG = f'{RUN}/progress.json'
WINS = {
    '6245': (1, 233),   # 1685-1706, whole volume in window
    '6246': (1, 100),   # 1706-~1714 (covers 1706-1712 w/ margin); 165-181 cached already
}
t0 = time.time()

def save(state):
    state['elapsed_s'] = round(time.time() - t0, 1)
    state['ts'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    json.dump(state, open(PROG, 'w'), indent=1)

state = {'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
         'vols': {}, 'done': False}
if os.path.exists(PROG):
    try:
        prev = json.load(open(PROG))
        if prev.get('done'):
            print('PREVIOUS RUN ALREADY DONE — nothing to do', flush=True)
            sys.exit(0)
        state['vols'] = prev.get('vols', {})
    except Exception:
        pass

for vol, (lo, hi) in WINS.items():
    vw = state['vols'].setdefault(vol, {'lo': lo, 'hi': hi, 'done': 0, 'fail': 0, 'fails': []})
    if vw.get('complete'):
        print(f'== {vol} already complete — skip', flush=True)
        continue
    n = hi - lo + 1
    vw['n'] = n
    print(f'== {vol} window {lo}-{hi} ({n} pages) ==', flush=True)
    for p in range(lo, hi + 1):
        dst = f'/workspace/agatha/cache/volumes/{vol}/pages/{p:03d}.jpg'
        if os.path.exists(dst) and os.path.getsize(dst) > 10000:
            vw['done'] += 1
            continue
        ok = False
        for attempt in range(3):
            try:
                ac.cmd_get(vol, p)
                if os.path.exists(dst) and os.path.getsize(dst) > 10000:
                    ok = True
                    break
            except SystemExit:
                # cookie may be stale mid-batch
                if attempt == 0:
                    try:
                        ac.cmd_ensure()
                        print(f'  {vol} p{p}: re-logged in, retrying', flush=True)
                    except SystemExit as e:
                        vw['fails'].append(f'p{p}:relogin:{str(e)[:40]}')
                        vw['fail'] += 1
                        break
            except Exception as e:
                vw['fails'].append(f'p{p}:{str(e)[:40]}')
                vw['fail'] += 1
                break
            if os.path.exists(dst + '.part'):
                try: os.unlink(dst + '.part')
                except OSError: pass
        if ok:
            vw['done'] += 1
        if vw['done'] % 20 == 0:
            save(state)
            print(f'  {vol} {vw["done"]}/{n} (elapsed {time.time()-t0:.0f}s)', flush=True)
    vw['complete'] = (vw['fail'] == 0)
    save(state)
    print(f'== {vol} done: {vw["done"]}/{n}, {vw["fail"]} fail ==', flush=True)

state['done'] = True
save(state)
print(f'\nDONE 6245+6246 window download. fails={sum(v["fail"] for v in state["vols"].values())} elapsed={state["elapsed_s"]}s', flush=True)
