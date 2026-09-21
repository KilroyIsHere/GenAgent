#!/usr/bin/env python3
"""Download 6262 canvases 90-120 (1726-1731 gap)."""
import os, sys
sys.path.insert(0, '/workspace/agatha')
import agatha_cache as ac

VOL = '6262'
cookie = ac.cmd_ensure()
idx = ac.load_index(VOL)
meta = ac.load_meta(VOL)
referer = meta.get('volume_url', 'https://agatha.arch.be/')
base = os.path.join(ac.vol_dir(VOL), 'pages')
os.makedirs(base, exist_ok=True)
fails = []
for i in range(90, 121):
    dst = f"{base}/{i:03d}.jpg"
    if os.path.exists(dst) and os.path.getsize(dst) > 10_000:
        continue
    url = idx[i-1]['full_res_url']
    tmp = dst + '.part'
    try:
        ac.curl(url, tmp, referer, cookie)
        os.rename(tmp, dst)
        print(f"  {i} ok ({os.path.getsize(dst)}b)", flush=True)
    except SystemExit as e:
        fails.append(i)
        print(f"  {i} FAIL {e}", flush=True)
        if len(fails) == 1:
            try:
                cookie = ac.do_login()
                print("  re-logged in", flush=True)
            except Exception as e2:
                print(f"  relogin fail {e2}", flush=True)
print(f"DONE fails={fails}", flush=True)
