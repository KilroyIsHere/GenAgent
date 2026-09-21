#!/usr/bin/env python3
"""Phase 4 step 1 — init all 20 NEW index volumes (manifest -> index.json + meta.json).
Cache-first: skip volumes already initialized (index.json present + non-empty)."""
import sys, json, time
sys.path.insert(0, '/workspace/agatha')
import agatha_cache as ac

MAN = json.load(open('/workspace/agatha/runs/frederic_zorokens/p4_new_index_manifests.json'))
PID = {'6222':17,'6364':11,'6365':11,'6084':15,'6091':15,'6090':15,
       '6138':14,'6137':14,'6145':14,'6144':14,'6320':21,'6322':21,'6324':21,
       '6186':24,'6187':24,'6188':24,'6263':20,'6257':20,'6259':20,'6264':20}
import os
for bp, info in MAN.items():
    idxp = f'/workspace/agatha/cache/volumes/{bp}/index.json'
    if os.path.exists(idxp) and os.path.getsize(idxp) > 100:
        print(f"{bp}: already initialized — skip")
        continue
    if not info.get('ok'):
        print(f"{bp}: NO MANIFEST ({info.get('note')}) — skip")
        continue
    ac.cmd_init(bp, info['manifest'], ac.get_cookie(),
                f"bapt INDEX {info['par']} {info['dr']}", info['dr'], str(PID[bp]))
    time.sleep(0.3)
print("DONE init pass")
