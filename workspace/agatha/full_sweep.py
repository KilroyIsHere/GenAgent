#!/usr/bin/env python3
"""Phase 5 FULL-VOLUME ZORROK* SWEEP (robust, structure-agnostic).
For each of 13 distinct physical scans, download + OCR ALL pages (10-way
parallel Kraken small), scan for Zorrok* variants + 1715-1741 dates, and
save all hits with full context + IIIF URL.

No structure assumption: the variant scan finds Zorrok* hits wherever they
are in the volume, regardless of the index's internal layout (single A→Z
run, year-banded cycles, or anything else).

Resumable: skips pages already OCR'd. Saves after each volume.

Usage: full_sweep.py [vol1 vol2 ...]   (default: all 13)
"""
import sys, os, re, json, subprocess, concurrent.futures as cf, time
from collections import Counter

VOL_DIR = '/workspace/agatha/cache/volumes'
COOKIE = open('/workspace/agatha/cache/session_cookie.txt').read().strip()
REF = 'https://agatha.arch.be/'
URL = 'http://host.docker.internal:8008/ocr-path'
RESULTS = '/workspace/agatha/lookup/full_sweep_results.json'

# NOTE: 6141/6142/6143 (OLV-Noord), 6088/6089 (OLV-Zuid), 6327/6328
# (St-Laurentius), 6189/6190 (St-Walburga) are each ONE physical scan listed
# under multiple year-range labels — swept once (deduped here).
VOLS = [
    ('6379',  'Christel. Gereform. Kerk', 'bapt index',        '1701-1780', 90),
    ('6141',  'OLV-Noord',                'bapt index (1 scan=6141/42/43)', '1715-1746', 204),
    ('6088',  'OLV-Zuid',                 'bapt index (1 scan=6088/89)',   '1700-1731', 230),
    ('6119',  'OLV-Zuid',                 'bapt index',        '1731-1745', 241),
    ('6223',  'St-Andries',               'bapt index',        '1671-1727', 194),
    ('6224',  'St-Andries',               'bapt index',        '1727-1778', 142),
    ('6160',  'St-Jacobus',               'bapt index',        '1660-1729', 345),
    ('6161',  'St-Jacobus',               'bapt index',        '1730-1796', 226),
    ('454853','St-Laurentius',            'bapt index',        '1705-1721', 175),
    ('6327',  'St-Laurentius',            'bapt index (1 scan=6327/28)',    '1722-1763', 204),
    ('6189',  'St-Walburga',              'bapt index (1 scan=6189/90)',    '1713-1739', 221),
    ('6209',  'St-Walburga',              'bapt index',        '1739-1755', 283),
    ('6300',  'St-Willibrordus',          'bapt index',        '1613-1796', 214),
]

# Zorrok* variant pattern — generous, case-insensitive
VAR = re.compile(r'\bdo[rz][rre]*[a-z]{0,8}\b', re.I)
# Near-miss (ZOR, ZORS, ZOROTHEA) — review candidates
NEAR = re.compile(r'\bdo[rz][a-z]{0,12}\b', re.I)
YEAR_RE = re.compile(r'\b1[67][0-9][0-9]\b')

def dl(v, p):
    idx = json.load(open(f'{VOL_DIR}/{v}/index.json'))
    dst = f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return 'cache'
    last = 'ERR'
    for attempt in range(3):
        r = subprocess.run(
            ['curl','-sS','-f','-o',dst+'.part',
             '-H',f'Referer: {REF}','-H',f'Cookie: {COOKIE}','-w','%{http_code}',
             idx[p-1]['full_res_url']],
            capture_output=True, text=True)
        if (r.returncode == 0 and r.stdout.strip() == '200'
                and os.path.exists(dst+'.part') and os.path.getsize(dst+'.part') > 10000):
            os.rename(dst+'.part', dst)
            return 'ok'
        last = f'ERR {r.stdout} {r.stderr[:60]}'
        time.sleep(3*(attempt+1))
    return last

def ocr(v, p):
    img = f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    out = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return 'cache'
    if not (os.path.exists(img) and os.path.getsize(img) > 10000):
        return 'NODL'
    last = 'EMPTY'
    for attempt in range(3):
        r = subprocess.run(
            ['curl','-sS','-X','POST',URL,
             '-H','Content-Type: application/json',
             '-d',json.dumps({'path':img,'model':'small.safetensors'}),
             '-o',out],
            capture_output=True, text=True, timeout=300)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return 'ok'
        if os.path.exists(out):
            os.remove(out)  # 0-byte file would be mistaken for 'cache' on retry
        last = f'EMPTY {r.stderr[:80]}'
        time.sleep(3*(attempt+1))
    return last

def scan_page(v, p, parish, title, drange):
    f = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if not os.path.exists(f):
        return []
    txt = open(f, errors='ignore').read()
    idx_json = json.load(open(f'{VOL_DIR}/{v}/index.json'))
    iiif = idx_json[p-1]['full_res_url'] if p-1 < len(idx_json) else '?'
    hits = []
    for m in VAR.finditer(txt):
        word = m.group(0)
        # Only keep hits where the variant looks like a surname (not "do rre")
        # Filter out pure month/word matches
        if word.lower() in ('dobbelaer','dorp','zoro'): continue
        lines = txt.split('\n')
        line_no = txt[:m.start()].count('\n')
        ctx = ' || '.join(l for l in lines[max(0,line_no-4):line_no+5] if l.strip())
        win = txt[max(0,m.start()-150):m.end()+150]
        years = [int(y) for y in YEAR_RE.findall(win)]
        in_range = any(1715 <= y <= 1741 for y in years)
        hits.append({
            'volume': v, 'parish': parish, 'title': title, 'date_range': drange,
            'page': p, 'variant': word, 'years_near': years,
            'in_range_1715_1741': in_range,
            'context': ctx[:600],
            'iiif_url': iiif,
            'ocr_file': f'cache/volumes/{v}/pages/{p:03d}.ocr.txt',
            'image': f'cache/volumes/{v}/pages/{p:03d}.jpg',
        })
    return hits

def main():
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    state = {}
    if os.path.exists(RESULTS):
        try: state = json.load(open(RESULTS))
        except: state = {}
    results = state.get('completed', {})
    all_hits = state.get('all_hits', [])

    for vid, parish, title, drange, npages in VOLS:
        if only and vid not in only:
            continue
        if vid in results and results[vid].get('done'):
            print(f'== {vid} already done (hits={results[vid]["n_hits"]}) — skip', flush=True)
            continue
        print(f'\n===== {vid} ({parish} {title} {drange}, {npages}p) =====', flush=True)
        t0 = time.time()
        pages = list(range(1, npages+1))
        # Download all pages
        dl_done = dl_fail = 0
        for i, p in enumerate(pages):
            r = dl(vid, p)
            if r in ('ok', 'cache'): dl_done += 1
            else:
                dl_fail += 1
                print(f'    DL FAIL p{p}: {r}', flush=True)
        print(f'  Downloaded {dl_done}/{len(pages)} ({dl_fail} failed)', flush=True)
        # OCR all pages (10-way parallel)
        ocr_ok = ocr_fail = 0
        with cf.ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(ocr, vid, p): p for p in pages}
            for fut in cf.as_completed(futs):
                r = fut.result()
                if r in ('ok','cache'): ocr_ok += 1
                else:
                    ocr_fail += 1
                    print(f'    OCR FAIL p{futs[fut]}: {r}', flush=True)
        print(f'  OCR: {ocr_ok} ok, {ocr_fail} fail', flush=True)
        # Scan for variants
        hits = []
        for p in pages:
            hits.extend(scan_page(vid, p, parish, title, drange))
        in_range = [h for h in hits if h['in_range_1715_1741']]
        elapsed = time.time() - t0
        complete = (dl_fail == 0 and ocr_fail == 0)
        results[vid] = {
            'parish': parish, 'title': title, 'date_range': drange,
            'n_pages': npages, 'n_hits': len(hits), 'n_in_range': len(in_range),
            'dl_fail': dl_fail, 'ocr_fail': ocr_fail,
            'elapsed_s': round(elapsed, 1), 'done': complete,
        }
        if not complete:
            print(f'  !! {vid} NOT marked done: {dl_fail} dl + {ocr_fail} ocr '
                  f'failures (audit will retry; do NOT treat as searched)', flush=True)
        all_hits = [h for h in all_hits if h.get('volume') != vid] + hits
        print(f'  Variant hits: {len(hits)} | in-range (1715-1741): {len(in_range)}', flush=True)
        for h in in_range:
            print(f'    IN-RANGE p{h["page"]}: {h["variant"]} years={h["years_near"]} :: {h["context"][:180]}', flush=True)
        json.dump({'completed': results, 'all_hits': all_hits}, open(RESULTS, 'w'), indent=1)
        print(f'  [saved] elapsed {elapsed:.0f}s', flush=True)

    print(f'\n===== SUMMARY ({time.strftime("%H:%M:%S")}) =====')
    done = sum(1 for r in results.values() if r.get('done'))
    print(f'Volumes done: {done}/{len(VOLS)}')
    print(f'Total variant hits: {len(all_hits)}')
    print(f'In-range (1715-1741) hits: {len([h for h in all_hits if h["in_range_1715_1741"]])}')
    json.dump({'completed': results, 'all_hits': all_hits}, open(RESULTS, 'w'), indent=1)
    print('SAVED', RESULTS)

if __name__ == '__main__':
    main()
