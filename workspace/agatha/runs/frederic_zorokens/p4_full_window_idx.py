#!/usr/bin/env python3
"""Phase 4 — ZERO-OCR fuzzy matcher over ALL cached index vols, FULL 1667-1712 window.
Index layout: surname token + first-name tokens on the same/next lines (alphabetical).
Surname scored vs Zorokens/Zorrokens via validated fuzzy matcher (edit<=3).
Report every d0-d2 hit with first-name, year (nearest within +/-8 lines), page, leaf, IIIF.
"""
import os, re, json, glob
src = open("/workspace/agatha/fuzzy_zorrokens.py").read().replace("if __name__=='__main__':\n    main()", "")
ns = {}; exec(compile(src, 'fd', 'exec'), ns)
surname_score = ns['surname_score']
LO, HI = 1667, 1712
YEAR_RE = re.compile(r'\b(1[67][0-9][0-9])\b')
FRED_RE = re.compile(r'^(frederic|frideric|frider|frieric|frier|federic|frederik|fridericus|fredericus|fresder|frederick|phreder|fridericx|fieder|fiedric|fiedericus|fredricus|fidericus)', re.I)
CORPUS = {
    '6223': ('St-Andries', 'bapt index', '1671-1727'),
    '6160': ('St-Jacobus', 'bapt index', '1660-1729'),
    '6300': ('St-Willibrordus', 'bapt index', '1613-1796'),
    '6379': ('Christ.Gereform', 'bapt index', '1701-1780'),
    '6089': ('OLV-Zuid', 'bapt index', '1700-1717'),
    '454853': ('St-Laurentius', 'bapt index', '1705-1721'),
    '6260': ('St-Joris', 'bapt index', '1700-...'),
    '6262': ('St-Joris', 'bapt index', '1700-...'),
    '6265': ('St-Joris', 'bapt index', '1701-1725'),
}
out = {}
for vol, (parish, title, drange) in CORPUS.items():
    idxp = f"/workspace/agatha/cache/volumes/{vol}/index.json"
    idx = json.load(open(idxp)) if os.path.exists(idxp) else []
    rows = []
    for ocr in sorted(glob.glob(f"/workspace/agatha/cache/volumes/{vol}/pages/*.ocr.txt")):
        if os.path.getsize(ocr) <= 0: continue
        txt = open(ocr, errors='ignore').read()
        base = os.path.basename(ocr)[:-len('.ocr.txt')]
        page = int(re.sub(r'[^0-9]', '', base)) or 0
        lines = txt.split('\n')
        for ln, line in enumerate(lines):
            toks = re.findall(r"[A-Za-z][A-Za-z'’\-\.]{2,}", line)
            for ti, t in enumerate(toks):
                sc = surname_score(t)
                if not sc or sc[0] > 2: continue
                d, kind, ref = sc
                # nearest year within +/-8 lines
                yrs = []
                for j in range(max(0, ln-8), min(len(lines), ln+9)):
                    for m in YEAR_RE.findall(lines[j]):
                        yrs.append(int(m))
                yrs = sorted(set(yrs))
                inwin = any(LO <= y <= HI for y in yrs)
                # first-name tokens: next 1-3 tokens on same or next line
                following = toks[ti+1:ti+4]
                if not following and ln+1 < len(lines):
                    following = re.findall(r"[A-Za-z][A-Za-z'’\-\.]{2,}", lines[ln+1])[:3]
                first = ' '.join(following)
                fred = any(FRED_RE.match(f) for f in following) or any(FRED_RE.match(f) for f in (lines[ln+1].split() if ln+1 < len(lines) else []))
                iiif = idx[page-1].get('full_res_url', '') if 0 < page <= len(idx) else ''
                rows.append(dict(page=page, leaf=base, tok=t, d=d, kind=kind, first=first,
                                 fred=fred, years=yrs, in_window=inwin,
                                 line=line.strip()[:90], next=(lines[ln+1].strip()[:90] if ln+1 < len(lines) else ''), iiif=iiif))
    out[vol] = dict(parish=parish, title=title, drange=drange, rows=rows)
    rows = out[vol]['rows']
    print(f"=== {parish} ({vol}) {drange} d0-d2: {len(rows)} ===")
    for r in sorted(rows, key=lambda r: r['page']):
        tag = "INWIN" if r['in_window'] else "out"
        ftag = "FRED*" if r['fred'] else ""
        print(f"  p{r['page']}/{r['leaf']} {r['tok']}(d{r['d']},{r['kind']}) first='{r['first']}' {ftag} yrs={r['years']} [{tag}] :: {r['line']}")
json.dump(out, open('/workspace/agatha/runs/frederic_zorokens/_p4_full_window_idx.json', 'w'), indent=1, ensure_ascii=False)
print("\nWROTE _p4_full_window_idx.json")
