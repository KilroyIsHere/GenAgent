#!/usr/bin/env python3
"""Phase 5 step 1 — init all 33 NEW register volumes (manifest -> index.json + meta.json).
Cache-first: skip volumes already initialized (index.json present + non-empty).
Purpose: get REAL page counts for an honest OCR/disk estimate before the sweep."""
import sys, json, time, os, re
sys.path.insert(0, '/workspace/agatha')
import importlib.util
import agatha_cache as ac
spec = importlib.util.spec_from_file_location('e', '/workspace/agatha/enum_antwerp_baptism.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

# (vol, parish, span) — 33 NEW register volumes in the 1667-1712 window.
# The 6 cached in-window register vols (6355/6243/6244/6245/6246/6290) are
# already OCR'd + swept -> zero-OCR re-scan only, NOT init'd here.
VOLS = [
    ('6367', 'Christ. Gereform. (11)', '1660-1667'),
    ('6372', 'Christ. Gereform. (11)', '1660-1787'),
    ('6150', 'OLV-Noord (14)',          '1663-1687'),
    ('6149', 'OLV-Noord (14)',          '1682-1682'),
    ('6151', 'OLV-Noord (14)',          '1688-1705'),
    ('6152', 'OLV-Noord (14)',          '1705-1725'),
    ('6110', 'OLV-Zuid (15)',           '1658-1670'),
    ('6113', 'OLV-Zuid (15)',           '1670-1687'),
    ('6116', 'OLV-Zuid (15)',           '1688-1700'),
    ('6117', 'OLV-Zuid (15)',           '1701-1717'),
    ('6354', 'San Felipe (16)',         '1658-1700'),
    ('6169', 'St-Jacobus (19)',         '1665-1672'),
    ('6170', 'St-Jacobus (19)',         '1672-1685'),
    ('6171', 'St-Jacobus (19)',         '1685-1693'),
    ('6172', 'St-Jacobus (19)',         '1693-1703'),
    ('6173', 'St-Jacobus (19)',         '1704-1722'),
    ('6283', 'St-Joris (20)',           '1664-1673'),
    ('6284', 'St-Joris (20)',           '1674-1683'),
    ('6282', 'St-Joris (20)',           '1680-1680'),
    ('6286', 'St-Joris (20)',           '1683-1689'),
    ('6287', 'St-Joris (20)',           '1690-1700'),
    ('6288', 'St-Joris (20)',           '1700-1705'),
    ('6289', 'St-Joris (20)',           '1705-1712'),
    ('6321', 'St-Laurentius (21)',      '1659-1676'),
    ('6323', 'St-Laurentius (21)',      '1667-1687'),
    ('6325', 'St-Laurentius (21)',      '1688-1721'),
    ('6203', 'St-Walburga (24)',        '1665-1677'),
    ('6204', 'St-Walburga (24)',        '1678-1696'),
    ('6205', 'St-Walburga (24)',        '1696-1700'),
    ('6206', 'St-Walburga (24)',        '1701-1712'),
    ('6304', 'St-Willibrordus (25)',    '1654-1698'),
    ('6303', 'St-Willibrordus (25)',    '1687-1687'),
    ('6305', 'St-Willibrordus (25)',    '1698-1778'),
]

out = {}
for bp, par, dr in VOLS:
    idxp = f'/workspace/agatha/cache/volumes/{bp}/index.json'
    if os.path.exists(idxp) and os.path.getsize(idxp) > 100:
        n = len(json.load(open(idxp)))
        out[bp] = {'par': par, 'dr': dr, 'ok': True, 'n_pages': n, 'manifest': 'already-init'}
        print(f"{bp}: already initialized ({n} pp) — skip", flush=True)
        continue
    url = f"https://agatha.arch.be/en/search/genealogie/{bp}"
    try:
        html = m.fetch(url, 'https://agatha.arch.be/', ac.get_cookie())
    except Exception as e:
        out[bp] = {'par': par, 'dr': dr, 'ok': False, 'note': f'fetch err: {e}'}
        print(f"{bp}: FETCH ERR {e}", flush=True); continue
    mans = sorted(set(re.findall(r'/data/json/[^<>\s"\']+\.json', html)))
    if not mans:
        out[bp] = {'par': par, 'dr': dr, 'ok': False, 'note': 'no manifest in page'}
        print(f"{bp}: NO MANIFEST", flush=True); continue
    man_url = 'https://agatha.arch.be' + mans[0]
    try:
        ac.cmd_init(bp, man_url, ac.get_cookie(), f"bapt REGISTER {par} {dr}", dr, bp)
        out[bp] = {'par': par, 'dr': dr, 'ok': True,
                   'n_pages': len(json.load(open(idxp))), 'manifest': man_url}
    except Exception as e:
        out[bp] = {'par': par, 'dr': dr, 'ok': False, 'note': f'init err: {e}'}
        print(f"{bp}: INIT ERR {e}", flush=True)
    time.sleep(0.3)

json.dump(out, open('/workspace/agatha/runs/frederic_zorokens/p5_new_register_manifests.json', 'w'), indent=1)
ok = sum(1 for v in out.values() if v.get('ok'))
tot = sum(v.get('n_pages', 0) for v in out.values() if v.get('ok'))
print(f"\nDONE: {ok}/{len(VOLS)} initialized, {tot} total pages", flush=True)
