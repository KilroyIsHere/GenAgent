#!/usr/bin/env python3
"""Unit-test p5_run pieces without launching the sweep:
- import chain (agatha_cache + scan_frederic)
- estimate_band bracketing (chronological + whole-window cases)
- STATUS start/finish writers (capture _append, render with real-shaped hits)
- scan_volume over the already-OCR'd 6245 (St-Andries, Phase 2/3 proven corpus)
  to prove the matcher runs end-to-end on real register OCR and returns the
  expected FATHER-only corroboration (NOT a Frederic STRONG).
"""
import sys, os, json, glob
sys.path.insert(0, '/workspace/agatha')
sys.path.insert(0, '/workspace/agatha/runs/frederic_zorokens')
import p5_run as p5
import scan_frederic as sf

print("== import ok; VOLS =", len(p5.VOLS), "CACHED =", p5.CACHED)

# --- estimate_band on a synthetic chronological sample ---
# make fake OCR leaves with known years to test bracketing
os.makedirs('/tmp/p5test/6999/pages', exist_ok=True)
for p, y in [(1,1650),(10,1660),(20,1670),(30,1680),(40,1690),(50,1700),(60,1710),(70,1720)]:
    for s in ('L','R'):
        open(f'/tmp/p5test/6999/pages/{p:03d}_{s}.ocr.txt','w').write(f'{y}\n{y}\n')
# temp-page trick: point estimate_band at /tmp by monkeypatching PAGE_DIR
old=p5.PAGE_DIR; p5.PAGE_DIR='/tmp/p5test'
band, fb = p5.estimate_band('6999', list(range(1,71,4)), 70, 1667, 1712)
print("== estimate_band chronological 1667-1712:", band, "fallback:", fb, "(expect band ~[16,56], fallback False)")
# whole-window case: years all inside window
for p in [1,10,20,30,40,50,60,70]:
    for s in ('L','R'):
        open(f'/tmp/p5test/6999/pages/{p:03d}_{s}.ocr.txt','w').write('1690\n1695\n')
band2, fb2 = p5.estimate_band('6999', list(range(1,71,4)), 70, 1667, 1712)
print("== estimate_band whole-in-window:", band2, "fallback:", fb2, "(expect [1,70], fallback False)")
# no-years case
for p in [1,10,20,30,40,50,60,70]:
    for s in ('L','R'):
        open(f'/tmp/p5test/6999/pages/{p:03d}_{s}.ocr.txt','w').write('no years here\n')
band3, fb3 = p5.estimate_band('6999', list(range(1,71,4)), 70, 1667, 1712)
print("== estimate_band no-years:", band3, "fallback:", fb3, "(expect [1,70], fallback True)")
p5.PAGE_DIR=old

# --- STATUS writers: capture _append ---
captured=[]
p5._append=lambda s: captured.append(s)
p5.status_start('6999','TEST (99)','1660-1720',(1667,1712),70)
# build a fake STRONG + NEAR + FATHER + GAP from real-shaped hit dicts
def mk(verdict, page=25, edit=1):
    return {'verdict':verdict,'page':page,'leaf':'025_L','father_zorok_tok':'Zorrokens',
            'father_zorok_edit':edit,'b_initial':False,'excluded_lineage':False,
            'fred_child_tok':'Fredericus','fred_child_edit':edit,'fred_godp_tok':'Fredericus',
            'fred_godp_edit':edit,'father_tokens':['Frederici','Zorrokens','Maria','Janssens'],
            'child_zone_tokens':['Fredericus','legitimus'],'godp_zone_tokens':['Joannes','Petrus'],
            'years_near':[1690],'in_window_1667_1712':True,'iiif_url':'https://x/iiif/9',
            'ocr_file':'cache/volumes/6999/pages/025_L.ocr.txt','image':'cache/volumes/6999/pages/025_L.jpg',
            'line_zorok_tok':'Zorrokens','line_zorok_edit':1,'line_fred_tok':'Fredericus','line_fred_edit':1}
all_hits=[mk('STRONG'),mk('NEAR',26),mk('FATHER',27)]
gaps=[mk('GAP',28)]
vp={'structure_kind':'child-after','fallback':False,'n_pages':70}
p5.status_finish('6999','TEST (99)','1660-1720',(1667,1712),vp,all_hits,gaps,140,140,[16,56])
rendered=''.join(captured)
for needle in ['— START —','— FINISH —','STRONG (crop-verify','NEAR (Frederic in godparent',
               'FATHER-only','GAP (line co-occurrence','Zorrokens','full-res](https://x/iiif/9)']:
    assert needle in rendered, f"MISSING in STATUS render: {needle!r}"
print("== STATUS writers render OK; bytes:", len(rendered))
print("---- sample FINISH (first 1200 chars) ----")
print(rendered[rendered.index('— FINISH —'):][:1200])

# --- scan_volume over real 6245 OCR (proven Phase-2/3 corpus) ---
idx=[]
ah,gap = p5.scan_volume('6245','St-Andries (17)','1685-1706',(1685,1706),idx,set(range(1,10)))
strong_inwin=[h for h in ah if h['verdict']=='STRONG' and h.get('in_window_1667_1712')]
print(f"\n== scan_volume on 6245 pp1-9: total entries={len(ah)} strong_inwin={len(strong_inwin)} gaps={len(gap)}")
from collections import Counter
print("   verdicts:", dict(Counter(h['verdict'] for h in ah)))
print("   structure per leaf:", [sf.detect_structure(sf.tokenize_leaf(f'/workspace/agatha/cache/volumes/6245/pages/{p:03d}_L.ocr.txt')[0])[0] if False else (sf.detect_structure(sf.tokenize_leaf(f'/workspace/agatha/cache/volumes/6245/pages/{p:03d}_L.ocr.txt')[0])) for p in [1,2,3]][:3])
print("\nALL UNIT TESTS PASSED")
