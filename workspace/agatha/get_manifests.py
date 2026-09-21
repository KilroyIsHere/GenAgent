#!/usr/bin/env python3
"""For bookpart IDs given on argv: fetch volume page -> extract manifest_path ->
register in cache via cmd_init. Title/range/parish come from
/workspace/agatha/lookup/antwerp_baptism_enum.json (vols list has id+desc+start+end)."""
import sys, re, os, json, subprocess, agatha_cache as ac

enum = json.load(open('/workspace/agatha/lookup/antwerp_baptism_enum.json'))
# map bookpart id -> (parish_id, title, range)
volinfo = {}
for pid, p in enum.items():
    for v in p['vols']:
        volinfo[v['id']] = (pid, f"{p['name']} — {v['desc']}", f"{v['start']}-{v['end']}", v['index'])

IDS = sys.argv[1:]
cookie = ac.cmd_ensure()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
tmp = '/tmp/volpage.html'

def get_manifest_path(bid):
    url = f'https://agatha.arch.be/en/search/genealogie/{bid}'
    tmp = '/tmp/volpage.html'
    r = subprocess.run(
        ["curl","-sSL","-f","-o",tmp,
         "-H",f"Referer: https://agatha.arch.be/en/search/genealogie/",
         "-H",f"Cookie: {cookie}","-w","%{http_code}",url],
        capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip()!='200':
        raise SystemExit(f"HTTP {r.stdout.strip()} for {url} ({r.stderr.strip()})")
    html = open(tmp, errors='ignore').read()
    m = re.search(r'manifest_path\s*=\s*["\']([^"\']+)["\']', html)
    return m.group(1) if m else None

out = {}
for bid in IDS:
    pid, title, rng, isidx = volinfo.get(bid, ('?','?','?',None))
    try:
        mp = get_manifest_path(bid)
        if not mp:
            out[bid] = 'NO MANIFEST PATH'; print(bid, 'NO MANIFEST PATH'); continue
        ac.cmd_init(bid, mp, cookie, title, rng, str(pid))
        out[bid] = mp
        print(bid, 'OK', title, rng)
    except SystemExit as e:
        out[bid] = f'ERR {e}'; print(bid, 'ERR', e)
    except Exception as e:
        out[bid] = f'ERR {e}'; print(bid, 'ERR', e)
open('/workspace/agatha/lookup/manifest_paths.json','w').write(json.dumps(out, indent=1))
print('SAVED', len(out))
