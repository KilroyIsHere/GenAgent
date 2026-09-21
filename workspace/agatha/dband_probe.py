#!/usr/bin/env python3
"""Phase 5 D-band probe: for each volume, download+OCR 5 probe pages
(near-start, 25%, 50%, 75%, near-end), detect dominant surname initial +
presence of variant tokens, and emit per-volume D-band candidate range.
Single-landscape index pages are OCR'd whole (no split_leaves)."""
import sys, os, re, json, subprocess, concurrent.futures as cf, math

VOL_DIR = '/workspace/agatha/cache/volumes'
COOKIE = open('/workspace/agatha/cache/session_cookie.txt').read().strip()
REF = 'https://agatha.arch.be/'
URL = 'http://host.docker.internal:8008/ocr-path'
OUT = '/workspace/agatha/lookup/probe_results.json'

VOLS = [v.strip() for v in sys.argv[1:] if v.strip()]

# Variant pattern for ZORROK* (case-insensitive) — generous
VAR = re.compile(r'\bdo[rz][rre]*[a-z]{0,7}\b', re.I)
# Also near-miss family: ZORRO*, ZORKE*, ZORROGEN, etc — VAR covers the first.
# Token pattern for surname detection: word starting with uppercase (Latin).
TOK = re.compile(r'\b[A-Z][a-z]{3,14}\b')

def vol_pages(v):
    idx = json.load(open(f'{VOL_DIR}/{v}/index.json'))
    return len(idx)

def dl(v, p):
    idx = json.load(open(f'{VOL_DIR}/{v}/index.json'))
    dst = f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return 'cache'
    url = idx[p-1]['full_res_url']
    r = subprocess.run(['curl','-sS','-f','-o',dst+'.part','-H',f'Referer: {REF}','-H',f'Cookie: {COOKIE}','-w','%{http_code}',url],
                       capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != '200':
        return f'ERR {r.stdout.strip()} {r.stderr.strip()[:60]}'
    os.rename(dst+'.part', dst)
    return 'ok'

def ocr(v, p):
    img = f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    out = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return 'cache'
    r = subprocess.run(['curl','-sS','-X','POST',URL,'-H','Content-Type: application/json',
                        '-d',json.dumps({'path':img,'model':'small.safetensors'}),'-o',out],
                       capture_output=True, text=True, timeout=300)
    return 'ok' if os.path.exists(out) and os.path.getsize(out) > 0 else 'EMPTY'

def analyze(v, p):
    """Read OCR text, detect dominant surname initial + variant presence."""
    f = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if not os.path.exists(f):
        return {'page':p, 'status':'no-ocr'}
    txt = open(f, errors='ignore').read()
    toks = TOK.findall(txt)
    # Filter out obvious non-surname tokens (months, years, common Latin words)
    EXCL = re.compile(r'^(Januari|Februari|Mart|April|Mai|Junij|Julij|Augu|Septem|Octo|Novem|Decem|'
                      r'Anno|Mens|Die|Nomina|Joannes|Joanna|Maria|Petrus|Jacobus|Antonius|Nicolaus|'
                      r'Franciscus|Barbara|Catharina|Elisabeth|Anna|Susanna|Gertrudis|Cornelius|'
                      r'Hendricus|Henricus|Guilielmus|Johannes|Joes|Joés|Joseph|Josepha|Theresia|'
                      r'Carolina|Margareta|Margarita|Isabella|Cathar|Maria|Theres|Carla|Helena|'
                      r'Barth|Bernard|Albert|Bartel|Bastiaen|Bastiaens|Bertels|Blaes|Brecht|'
                      r'Prosecutio|Verso|Recto|Folium|Folio|Tabella|Inci|Incipium|Bapt|Bapto|'
                      r'[0-9]+|1[67][0-9][0-9])', re.I)
    surnames = [t for t in toks if not EXCL.match(t)]
    if not surnames:
        # fallback: use ALL toks
        surnames = toks
    from collections import Counter
    initials = [s[0].upper() for s in surnames]
    if initials:
        c = Counter(initials)
        top = c.most_common(3)
        # dominant = most common; but if page spans a transition, we want min/max of the top-50% tokens
        # Better signal: median initial over sorted tokens
        sorted_i = sorted(initials)
        med = sorted_i[len(sorted_i)//2]
        # range: first and last initial among tokens that are in top-3 most-frequent
        top3 = set([x[0] for x in top[:3]])
        in_top = [x for x in sorted_i if x in top3]
        dom_lo = in_top[0] if in_top else med
        dom_hi = in_top[-1] if in_top else med
    else:
        med = dom_lo = dom_hi = '?'
    # Variants
    var_hits = VAR.findall(txt)
    # Count of D-initial surnames
    dcount = sum(1 for x in initials if x == 'D')
    return {'page':p, 'median_initial':med, 'dom_lo':dom_lo, 'dom_hi':dom_hi,
            'n_tokens':len(surnames), 'd_count':dcount,
            'variant_hits':var_hits[:8], 'n_variants':len(var_hits)}

# Probe pages: pick ~ 5% , 30%, 50%, 70%, 95% of content range (skip p1 title)
def probe_pages(n):
    cands = [max(2, int(n*0.05)), int(n*0.30), int(n*0.50), int(n*0.70), max(3, int(n*0.95))]
    # dedupe, clamp 2..n-1
    seen = set(); out = []
    for c in cands:
        c = min(n-1, max(2, c))
        if c not in seen:
            seen.add(c); out.append(c)
    return out

def main():
    out = {}
    for v in VOLS:
        n = vol_pages(v)
        pp = probe_pages(n)
        print(f'== {v} ({n} pages) probes={pp}', flush=True)
        # download
        for p in pp:
            r = dl(v, p)
            if r not in ('ok','cache'):
                print('  DL', p, r)
        # OCR in parallel
        def do_ocr(p):
            r = ocr(v, p)
            return (p, r)
        with cf.ThreadPoolExecutor(max_workers=min(5, len(pp))) as ex:
            for p, r in ex.map(do_ocr, pp):
                if r != 'ok' and r != 'cache':
                    print('  OCR', p, r)
        # analyze
        res = {}
        for p in pp:
            res[p] = analyze(v, p)
            a = res[p]
            print(f'  p{p}: med={a.get("median_initial")} lo..hi={a.get("dom_lo")}..{a.get("dom_hi")} '
                  f'n={a.get("n_tokens")} D={a.get("d_count")} vars={a.get("n_variants")}', flush=True)
        out[v] = {'n_pages':n, 'probes':pp, 'analysis':res}
        # save after each volume
        open(OUT,'w').write(json.dumps(out, indent=1))
    print('SAVED', OUT)

if __name__ == '__main__':
    main()
