#!/usr/bin/env python3
"""Sanity: does each cached index contain ANY d0 (exact Zorokens/Zorrokens) entries at all?
Confirms the matcher is actually reading the index D-sections, not silently failing.
"""
import os, json, re, glob
src = open("/workspace/agatha/fuzzy_zorrokens.py").read().replace("if __name__=='__main__':\n    main()", "")
ns = {}; exec(compile(src, 'fd', 'exec'), ns)
surname_score = ns['surname_score']
CORPUS = {'6223':('St-Andries','1671-1727'), '6160':('St-Jacobus','1660-1729'), '6300':('St-Willibrordus','1613-1796')}
YEAR_RE = re.compile(r'\b1[67][0-9][0-9]\b')
for vol,(parish,drange) in CORPUS.items():
    d0=[]; d1=[]; d2=[]
    for ocr in sorted(glob.glob(f"/workspace/agatha/cache/volumes/{vol}/pages/*.ocr.txt")):
        if os.path.getsize(ocr)<=0: continue
        txt=open(ocr,errors='ignore').read()
        base=os.path.basename(ocr)[:-len('.ocr.txt')]
        page=int(re.sub(r'[^0-9]','',base)) or 0
        lines=txt.split('\n')
        for ln,line in enumerate(lines):
            toks=re.findall(r"[A-Za-z][A-Za-z'\-\.]{2,}",line)
            for ti,t in enumerate(toks):
                sc=surname_score(t)
                if not sc: continue
                d,kind,ref=sc
                win=' '.join(lines[ln:ln+2])
                yrs=[int(y) for y in YEAR_RE.findall(win)]
                rec=(page,t,kind,' '.join(toks[ti+1:ti+3]),yrs)
                if d==0: d0.append(rec)
                elif d==1: d1.append(rec)
                elif d==2: d2.append(rec)
    print(f"=== {parish} ({vol}) {drange} ===  d0={len(d0)} d1={len(d1)} d2={len(d2)}")
    for r in d0[:25]:
        print(f"  D0 p{r[0]} {r[1]} child='{r[3]}' yrs={r[4]}")
