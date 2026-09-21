#!/usr/bin/env python3
"""Fuzzy re-scan of the 'Birth of Johannes Petri Zorrokens' already-OCR'd corpus.

Re-runs the SAME corpus + window (1715-1741) as the previous fixed-pattern
sweep (full_sweep.py: 13 baptism index vols + San Felipe 6355 + St Joris
legacy 6290-6293 + St Joris indexes 6260/6262/6265/6266), but replaces the
`zor`-anchored regex with a Levenshtein fuzzy matcher so mangled cursive
surnames (Zoorekens, Zorockens, Zorickens, van Zorokens, ...) are caught.
No new OCR, no downloads -- pure re-scan of existing .ocr.txt files.
"""
import json, os, re, glob, sys

VOL_DIR = "/workspace/agatha/cache/volumes"
OUT_JSON = "/workspace/agatha/lookup/fuzzy_zorrokens_results.json"

# Corpus: exact same volumes as the previous search (13 index vols + 6355 + legacy St Joris)
CORPUS = {
 '6379':  ('Christel. Gereform. Kerk', 'bapt index',        '1701-1780'),
 '6141':  ('OLV-Noord',                'bapt index',        '1715-1746'),
 '6088':  ('OLV-Zuid',                 'bapt index',        '1700-1731'),
 '6119':  ('OLV-Zuid',                 'bapt index',        '1731-1745'),
 '6223':  ('St-Andries',               'bapt index',        '1671-1727'),
 '6224':  ('St-Andries',               'bapt index',        '1727-1778'),
 '6160':  ('St-Jacobus',               'bapt index',        '1660-1729'),
 '6161':  ('St-Jacobus',               'bapt index',        '1730-1796'),
 '454853':('St-Laurentius',            'bapt index',        '1705-1721'),
 '6327':  ('St-Laurentius',            'bapt index',        '1722-1763'),
 '6189':  ('St-Walburga',              'bapt index',        '1713-1739'),
 '6209':  ('St-Walburga',              'bapt index',        '1739-1755'),
 '6300':  ('St-Willibrordus',          'bapt index',        '1613-1796'),
 '6355':  ('San Felipe del Castilla',  'bapt REGISTER',     '1700-1795'),
 '6290':  ('Sint-Joris',               'bapt REGISTER',     '1712-1720'),
 '6291':  ('Sint-Joris',               'bapt REGISTER',     '1720-1728'),
 '6292':  ('Sint-Joris',               'bapt REGISTER',     '1729-1742'),
 '6293':  ('Sint-Joris',               'bapt REGISTER',     '1742-1752'),
 '6260':  ('Sint-Joris',               'bapt INDEX',        '1742-...'),
 '6262':  ('Sint-Joris',               'bapt INDEX',        '1742-...'),
 '6265':  ('Sint-Joris',               'bapt INDEX',        '1701-1725'),
 '6266':  ('Sint-Joris',               'bapt INDEX',        '1726-1750'),
}

# Fuzzy targets (lowercase). Whole-token Levenshtein vs the full names,
# plus a distinctive-stem "contains" pass so 'van Zorokens'/'vzorokens'/
# 'Zoorekens' still fire WITHOUT the d=2 flood (theodorus/doncker/etc).
FULL  = ("zorokens", "zorrokens")
STEMS = ("zorok", "zorrok")        # distinctive 5-letter stems only
FULL_TH = 3      # max Levenshtein vs a full name
STEM_TH = 1      # max Levenshtein vs a distinctive stem (for contains pass)

# Target-child first-name cues (to rank STRONG candidates)
CHILD_RE = re.compile(
    r'\b(joannes|johannes|johanis|joes|joeus|joan|joan(n?is)?)\b.*?\b(petri|petrus|peter|petr)\b'
    r'|\b(petri|petrus|peter)\b.*?\b(joannes|johannes|johanis|joes|joeus)\b', re.I)
YEAR_RE  = re.compile(r'\b1[67][0-9][0-9]\b')

def lev(a, b):
    a=a.lower(); b=b.lower()
    if a==b: return 0
    la,lb=len(a),len(b)
    if la<1 or lb<1: return max(la,lb)
    prev=list(range(lb+1))
    for i in range(1,la+1):
        cur=[i]+[0]*lb
        for j in range(1,lb+1):
            cost=0 if a[i-1]==b[j-1] else 1
            cur[j]=min(prev[j]+1, cur[j-1]+1, prev[j-1]+cost)
        prev=cur
    return prev[lb]

def clean(tok):
    t=re.sub(r'[^a-zA-Z]', '', tok).lower()
    # strip a leading particle that scribes often keep attached
    for pre in ('vd','van','de','den'):
        if t.startswith(pre) and len(t)>len(pre)+3:
            t=t[len(pre):]
    return t

def surname_score(tok):
    """Return (dist, kind, ref) for best fuzzy surname match, else None."""
    t = clean(tok)
    if len(t) < 5: return None
    best=None
    for ref in FULL:
        d=lev(t, ref)
        if d <= FULL_TH and (best is None or d < best[0]):
            best=(d,'full',ref)
    # contains pass ONLY for distinctive stems (d<=1) -> avoids the flood
    if best is None or best[0] > 1:
        for s in STEMS:
            for i in range(0, max(1,len(t)-len(s)+1)):
                w=t[i:i+len(s)]
                d=lev(w, s)
                if d <= STEM_TH and (best is None or d<best[0]):
                    best=(d,'stem-contains',s)
    return best

def main():
    hits=[]
    seen=set()
    nfiles=0
    for vol,(parish,title,drange) in CORPUS.items():
        idxp=f"{VOL_DIR}/{vol}/index.json"
        try: idx=json.load(open(idxp))
        except Exception: idx=[]
        ocrs=sorted(glob.glob(f"{VOL_DIR}/{vol}/pages/*.ocr.txt"))
        for ocr in ocrs:
            if os.path.getsize(ocr)<=0: continue
            nfiles+=1
            txt=open(ocr, errors='ignore').read()
            # derive page for IIIF: filename like 048.ocr.txt or 018_L.ocr.txt
            base=os.path.basename(ocr)[:-len('.ocr.txt')]
            page=int(re.sub(r'[^0-9]','',base)) or 0
            iiif=''
            if idx and 0<page<=len(idx):
                iiif=idx[page-1].get('full_res_url','')
            lines=txt.split('\n')
            for ln,line in enumerate(lines):
                # tokenize the line
                toks=re.findall(r"[A-Za-z][A-Za-z'\-\.]{2,}", line)
                matched=[]
                for tok in toks:
                    sc=surname_score(tok)
                    if sc: matched.append((sc,tok))
                if not matched: continue
                ctx=' || '.join(l for l in lines[max(0,ln-4):ln+5] if l.strip())
                win=txt[max(0,txt.find(line)-150):txt.find(line)+len(line)+150]
                years=[int(y) for y in YEAR_RE.findall(win)]
                in_range=any(1715<=y<=1741 for y in years)
                child=bool(CHILD_RE.search(ctx))
                # strongest
                best=min(matched, key=lambda m:m[0][0])
                sc,mtok=best
                d,kind,ref=sc
                key=(vol,page,mtok.lower())
                if key in seen: continue
                seen.add(key)
                strong = child and (in_range or not years)
                hits.append({
                    'volume':vol,'parish':parish,'title':title,'date_range':drange,
                    'page':page,'leaf':base,'matched':mtok,'edit':d,'kind':kind,'ref':ref,
                    'years_near':years,'in_range_1715_1741':in_range,'child_joannes_petri':child,
                    'strong':strong,
                    'context':ctx[:600],
                    'iiif_url':iiif,
                    'ocr_file':f'cache/volumes/{vol}/pages/{base}.ocr.txt',
                    'image':f'cache/volumes/{vol}/pages/{base}.jpg',
                })
    # sort: strong first, then edit asc, then in-range
    hits.sort(key=lambda h:(not h['strong'], h['edit'], not h['in_range_1715_1741'], h['volume'], h['page']))
    out={'target':'Joannes ± Petri/Petrus ZORROKENS (fuzzy re-scan)',
         'window':'1715-1741','method':'Levenshtein fuzzy (full<=3, stem-contains<=2)',
         'corpus':{v:list(p) for v,p in CORPUS.items()},
         'n_ocr_files_scanned':nfiles,'n_hits':len(hits),
         'n_strong':sum(1 for h in hits if h['strong']),
         'hits':hits}
    json.dump(out, open(OUT_JSON,'w'), indent=1, ensure_ascii=False)
    print(f"scanned {nfiles} OCR files across {len(CORPUS)} volumes")
    print(f"total fuzzy surname hits: {len(hits)}  | strong (Joannes+Petri near): {out['n_strong']}")
    print("\n=== STRONG candidates ===")
    for h in hits:
        if not h['strong']: continue
        print(f"[{h['volume']} p{h['page']}/{h['leaf']}] {h['parish']} :: matched={h['matched']} (d={h['edit']},{h['kind']},~{h['ref']}) yrs={h['years_near']}")
        print(f"    ctx: {h['context'][:300]}")
    print("\n=== in-range (1715-1741) non-strong (top 40 by edit) ===")
    ir=[h for h in hits if not h['strong'] and h['in_range_1715_1741']]
    for h in ir[:40]:
        print(f"[{h['volume']} p{h['page']}] {h['parish']} :: {h['matched']} (d={h['edit']},{h['kind']}) yrs={h['years_near']}")

if __name__=='__main__':
    main()
