import json, glob, os
base = '/workspace/agatha/runs/frederic_zorokens'
s = json.load(open(base + '/p5_state.json'))
vols = s['vols']
print('ts:', s['ts'], '| phase:', s['phase'], '| done:', s['done'])
print('vols in state:', len(vols))
order = [v for v in vols] if isinstance(vols, list) else list(vols.keys())
# figure out per-volume status
for v in order:
    d = vols[v] if isinstance(vols, dict) else None
    if isinstance(d, dict):
        print(v, d.get('status'), d.get('hits_count', ''), d.get('page', ''), d.get('total_pages', ''))
    else:
        print(v, d)
