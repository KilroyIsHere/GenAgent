#!/usr/bin/env python3
"""Phase 4 — per-page in-window Zorok* rows for the 3 cached index vols (1685-1712).
Index layout: 'Surname. Firstname' (child's name). Surname slot = matched token;
child name = following tokens on the line. Real/possible tier = d0-d2.
"""
import os, json, re, glob
src = open("/workspace/agatha/fuzzy_zorrokens.py").read().replace("if __name__=='__main__':\n    main()", "")
ns = {}
exec(compile(src, 'fd', 'exec'), ns)
surname_score = ns['surname_score']
LO, HI = 1685, 1712
CORPUS = {
    '6223': ('St-Andries', 'bapt index', '1671-1727'),
    '6160': ('St-Jacobus', 'bapt index', '1660-1729'),
    '6300': ('St-Willibrordus', 'bapt index', '1613-1796'),
}
YEAR_RE = re.compile(r'\b1[67][0-9][0-9]\b')
out = {}
for vol, (parish, title, drange) in CORPUS.items():
    idxp = f"/workspace/agatha/cache/volumes/{vol}/index.json"
    idx = json.load(open(idxp)) if os.path.exists(idxp) else []
    rows = []
    for ocr in sorted(glob.glob(f"/workspace/agatha/cache/volumes/{vol}/pages/*.ocr.txt")):
        if os.path.getsize(ocr) <= 0:
            continue
        txt = open(ocr, errors='ignore').read()
        base = os.path.basename(ocr)[:-len('.ocr.txt')]
        page = int(re.sub(r'[^0-9]', '', base)) or 0
        lines = txt.split('\n')
        for ln, line in enumerate(lines):
            toks = re.findall(r"[A-Za-z][A-Za-z'\-\.]{2,}", line)
            for ti, t in enumerate(toks):
                sc = surname_score(t)
                if not sc or sc[0] > 2:
                    continue
                d, kind, ref = sc
                childtoks = toks[ti+1:ti+3]
                win = ' '.join(lines[ln:ln+2])
                yrs = [int(y) for y in YEAR_RE.findall(win)]
                if not any(LO <= y <= HI for y in yrs):
                    continue
                iiif = idx[page-1].get('full_res_url', '') if 0 < page <= len(idx) else ''
                rows.append(dict(page=page, leaf=base, tok=t, d=d, kind=kind,
                                 child=' '.join(childtoks), line=line.strip()[:90],
                                 years=yrs, iiif=iiif))
    out[vol] = dict(parish=parish, title=title, drange=drange, rows=rows)
    rows = out[vol]['rows']
    print(f"=== {parish} ({vol}) {drange} in-window d0-d2: {len(rows)} ===")
    for r in sorted(rows, key=lambda r: r['page'])[:40]:
        print(f"  p{r['page']}/{r['leaf']} {r['tok']}(d{r['d']}) child='{r['child']}' yrs={r['years']} :: {r['line']}")
json.dump(out, open('/workspace/agatha/runs/frederic_zorokens/_p4_cached_idx_perpage.json', 'w'), indent=1, ensure_ascii=False)
print("\nWROTE _p4_cached_idx_perpage.json")
