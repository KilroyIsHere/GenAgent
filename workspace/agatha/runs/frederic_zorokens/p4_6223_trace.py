#!/usr/bin/env python3
"""6223 (St-Andries baptism index) D-section, year-BLOCK-aware trace of every
Zorrok*/Zorok* entry. Index is columnar: a year appears once per block header
(e.g. 'Damiens. Hubertus 1671. Januari'); name lines inherit the block's year.
We read pp 40-50 (the D-section), track the most-recent year seen, and report
each Zorrok* entry with its block year + page + IIIF + raw line context.
"""
import os, re, json, glob
VOL=6223; LO,HI=1685,1712
idx=json.load(open(f"/workspace/agatha/cache/volumes/{VOL}/index.json"))
YEAR=re.compile(r'\b(1[5-7]\d{2})\b')
# fuzzy surname via the validated matcher
src=open("/workspace/agatha/fuzzy_zorrokens.py").read().replace("if __name__=='__main__':\n    main()","")
ns={}; exec(compile(src,'fd','exec'),ns)
surname_score=ns['surname_score']
def clean(t): return re.sub(r'[^a-z]','',t.lower())
rows=[]
for pg in range(40,51):
    for suf in [f"{pg:03d}",f"{pg:03d}_L",f"{pg:03d}_R"]:
        f=f"/workspace/agatha/cache/volumes/{VOL}/pages/{suf}.ocr.txt"
        if not os.path.exists(f): continue
        lines=open(f,errors='ignore').read().split('\n')
        cur_year=None
        for i,l in enumerate(lines):
            m=YEAR.search(l)
            if m: cur_year=int(m.group(1))
            toks=re.findall(r"[A-Za-z][A-Za-z'\-\.]{2,}",l)
            for ti,t in enumerate(toks):
                sc=surname_score(t)
                if not sc or sc[0]>1: continue   # d0-d1 (real/possible)
                d,kind,ref=sc
                child=' '.join(toks[ti+1:ti+3])
                inwin=cur_year is not None and LO<=cur_year<=HI
                iiif=idx[pg-1].get('full_res_url','') if 0<pg<=len(idx) else ''
                ctx=' '.join(x.strip() for x in lines[max(0,i-1):i+2] if x.strip())
                rows.append(dict(page=pg,leaf=suf,year=cur_year,tok=t,d=d,child=child,
                                  in_window=inwin,ctx=ctx[:120],iiif=iiif))
        break
rows.sort(key=lambda r:(r['page'],))
print(f"=== 6223 D-section Zorrok*/Zorok* d0-d1 entries (year-block aware) ===")
for r in rows:
    flag="IN-WINDOW" if r['in_window'] else ("pre-window" if (r['year'] or 9999)<LO else "post-window")
    print(f"  p{r['page']}/{r['leaf']} [{r['year']}] {r['tok']}(d{r['d']}) child='{r['child']}'  {flag}")
    print(f"        ctx: {r['ctx']}")
json.dump(rows,open('/workspace/agatha/runs/frederic_zorokens/_6223_dsection.json','w'),indent=1,ensure_ascii=False)
print(f"\nWROTE _6223_dsection.json  ({len(rows)} entries)")
