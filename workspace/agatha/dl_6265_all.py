#!/usr/bin/env python3
"""Batch-download missing 6265 canvases (index 1701-1725)."""
import os, sys, time
sys.path.insert(0, '/workspace/agatha')
import agatha_cache as ac

VOL = '6265'
cookie = ac.cmd_ensure()
idx = ac.load_index(VOL)
meta = ac.load_meta(VOL)
referer = meta.get('volume_url', 'https://agatha.arch.be/')
base = os.path.join(ac.vol_dir(VOL), 'pages')
os.makedirs(base, exist_ok=True)
todo = []
for i, entry in enumerate(idx, start=1):
    dst = f"{base}/{i:03d}.jpg"
    if os.path.exists(dst) and os.path.getsize(dst) > 10_000:
        continue
    todo.append((i, entry['full_res_url']))
print(f"cached={len(idx)-len(todo)} to_download={len(todo)}", flush=True)
fails = []
for i, url in todo:
    dst = f"{base}/{i:03d}.jpg"
    tmp = dst + '.part'
    try:
        ac.curl(url, tmp, referer, cookie)
        os.rename(tmp, dst)
        if i % 20 == 0:
            print(f"  {i}/{idx and len(idx)} downloaded ({os.path.getsize(dst)}b)", flush=True)
    except SystemExit as e:
        # cookie may have gone stale mid-batch: re-login once and retry the rest
        if i not in [f[0] for f in fails]:
            print(f"  FAIL at page {i}: {e}", flush=True)
        fails.append((i, str(e)))
        # try to refresh session once
        if len(fails) == 1:
            try:
                cookie = ac.do_login()
                print("  re-logged in, continuing", flush=True)
            except Exception as e2:
                print(f"  re-login failed: {e2}", flush=True)
print(f"DONE fails={[f[0] for f in fails]}", flush=True)
