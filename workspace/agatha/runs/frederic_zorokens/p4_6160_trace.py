#!/usr/bin/env python3
"""Trace St-Jacobus (6160) p91 Zorrokens entries with year-block awareness.
6160 index is columnar too (surname column / name column / year column).
Read the page, list every Zorrok* line with surrounding context + any years.
"""
import os, re, json
VOL=6160
idx=json.load(open(f"/workspace/agatha/cache/volumes/{VOL}/index.json"))
YEAR=re.compile(r'\b(1[5-7]\d{2})\b')
src=open("/workspace/agatha/fuzzy_zorrokens.py").read().replace("if __name__=='__main__':\n    main()","")
ns={}; exec(compile(src,'fd','exec'),ns)
surname_score=ns['surname_score']
rows=[]
for pg in range(88,93):
    f=f"/workspace/agatha/cache/volumes/{VOL}/pages/{pg:03d}.ocr.txt"
    if not os.path.exists(f): continue
    lines=open(f,errors='ignore').read().split('\n')
    for i,l in enumerate(lines):
        toks=re.findall(r"[A-Za-z][A-Za-z'\-\.]{2,}",l)
        for ti,t in enumerate(toks):
            sc=surname_score(t)
            if not sc or sc[0]>1: continue
            d,kind,ref=sc
            # year = nearest year within +/-12 lines
            yrs=[]
            for j in range(max(0,i-12),min(len(lines),i+13)):
                m=YEAR.search(lines[j])
                if m: yrs.append(int(m.group(1)))
            yrs=sorted(set(yrs))
            child=' '.join(toks[ti+1:ti+3])
            ctx=' '.join(x.strip() for x in lines[max(0,i-2):i+3] if x.strip())
            rows.append(dict(page=pg,tok=t,d=d,child=child,yrs=yrs,ctx=ctx[:140]))
print("=== 6160 (St-Jacobus) Zorrok*/Zorok* d0-d1 in pp 88-92 ===")
for r in rows:
    print(f"  p{r['page']} {r['tok']}(d{r['d']}) child='{r['child']}' nearby_yrs={r['yrs']}")
    print(f"        {r['ctx']}")
