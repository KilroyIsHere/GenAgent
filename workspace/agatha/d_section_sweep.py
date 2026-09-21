#!/usr/bin/env python3
"""Phase 5 D-section sweep, v2 (corrected for single A→Z structure).
For each of 13 distinct physical scans:
  Phase A: dense probe every ~4% of pages, detect dominant letter per page.
  Phase B: bracket the D-range from the probe letters; expand ±3 pages buffer.
  Phase C: OCR all pages in the expanded D-range (10-way parallel Kraken small).
  Phase D: scan OCR for Zorrok* variants + dates; record context + year.
  Phase E: save to /workspace/agatha/lookup/d_section_results.json.

Structure (confirmed 2026-09-16, vol 6141 p2-24):
  - Single A→Z run by father's surname per volume (not year-banded).
  - Each page covers one or two letters; dates scatter across the full volume range.
  - The D-section is a contiguous page range of ~5-10 pages.
  - Page-letter detection: dominant letter of first-column tokens (surname column),
    using a curated FIRST-NAMES exclusion set + date/month filter.
"""
import sys, os, re, json, subprocess, concurrent.futures as cf, time
from collections import Counter

VOL_DIR = '/workspace/agatha/cache/volumes'
COOKIE = open('/workspace/agatha/cache/session_cookie.txt').read().strip()
REF = 'https://agatha.arch.be/'
URL = 'http://host.docker.internal:8008/ocr-path'
RESULTS = '/workspace/agatha/lookup/d_section_results.json'

# 13 distinct physical scans (18 bookpart IDs deduped by IIIF SFX)
VOLS = [
    ('6379',  'OLV-Zuid',        'OLV Zuid bapt index',    '1701-1780', 90),
    ('6141',  'OLV-Noord',       'OLV Noord bapt index',   '1715-1746', 204),
    ('6088',  'OLV-Noord-2',     'OLV Noord-2 bapt index', '1700-1731', 230),
    ('6119',  'OLV-Zuid-2',      'OLV Zuid-2 bapt index',  '1731-1745', 241),
    ('6223',  'St-Andries',      'Andries bapt index 1',   '1671-1727', 194),
    ('6224',  'St-Andries',      'Andries bapt index 2',   '1727-1778', 142),
    ('6160',  'St-Jacobus',      'Jacobus bapt index 1',   '1660-1729', 345),
    ('6161',  'St-Jacobus',      'Jacobus bapt index 2',   '1730-1796', 226),
    ('454853','St-Laurentius',   'Laurentius bapt index 1','1705-1721', 175),
    ('6327',  'St-Laurentius-2', 'Laurentius bapt index 2','1722-1763', 204),
    ('6189',  'St-Walburga',     'Walburga bapt index 1',  '1713-1739', 221),
    ('6209',  'St-Walburga',     'Walburga bapt index 2',  '1739-1755', 283),
    ('6300',  'St-Willibrordus', 'Willibrordus bapt index','1613-1796', 214),
]

# First names + month names + header words to exclude from surname detection
FIRST = set([
    'Maria','Iabella','Anna','Janna','Joannes','soannes','Jacobul','JacoVIul',
    'Iacobul','Catharina','Elisabeth','Gerardul','Petrul','Petrus','Lucia',
    'Philippul','Clara','Joannel','Joanna','Constantia','Habella','Barbara',
    'Susanna','Melchior','Carolus','Rumoldul','Anua','Helena','Cornelia',
    'Thomal','Gulielmill','Henricus','Paulul','David','Philippl','Sufanna',
    'Adrianul','Ignatiul','Corneliul','Ludovicul','Gaspar','Arnoldus','Josephul',
    'Nicolaus','Andreas','Antonius','Emmanuël','Emmanuel','Dominicul','Bavo',
    'Balthazar','Albertus','Johannes','Guilielmus','Willem','Pieter','Joseph',
    'Sebastianus','Stephanus','Vincentius','Theresia','Carolina','Margareta',
    'Isabella','Elisobetha','Cathavina','JaAnna','Sofia','Bavo','Iacoba','Iacobs',
    'Johanna','Iacobus','Iacob','Iacoba','Iacoba','Iacoba','Iacoba','Iacoba',
])
MONTH_RE = re.compile(
    r'(Januarij|Ianuari|Februari|Martii|Aprilis|Maii|Junii|Julii|Augusti|Septembril|Octobris|Novembris|Decembr)', re.I)
YEAR_RE = re.compile(r'\b1[67][0-9][0-9]\b')
# Zorrok* variant pattern (generous)
VAR = re.compile(r'\bdo[rz][rre]*[a-z]{0,8}\b', re.I)
# Near-miss review: ZOR, ZORS, ZORN, ZOROTHEA, ZORNIQ (flagged, not confirmed)
NEAR = re.compile(r'\bdo[rz][a-z]{0,10}\b', re.I)

def dl(v, p):
    idx = json.load(open(f'{VOL_DIR}/{v}/index.json'))
    dst = f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return 'cache'
    r = subprocess.run(
        ['curl','-sS','-f','-o',dst+'.part',
         '-H',f'Referer: {REF}','-H',f'Cookie: {COOKIE}','-w','%{http_code}',
         idx[p-1]['full_res_url']],
        capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != '200':
        return f'ERR {r.stdout} {r.stderr[:60]}'
    os.rename(dst+'.part', dst)
    return 'ok'

def ocr(v, p):
    img = f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    out = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return 'cache'
    r = subprocess.run(
        ['curl','-sS','-X','POST',URL,
         '-H','Content-Type: application/json',
         '-d',json.dumps({'path':img,'model':'small.safetensors'}),
         '-o',out],
        capture_output=True, text=True, timeout=300)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return 'ok'
    return f'EMPTY {r.stderr[:80]}'

def page_dominant_letter(v, p):
    """Return the most-frequent surname initial on page p (excluding first names, dates, months)."""
    f = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if not os.path.exists(f):
        return None
    txt = open(f, errors='ignore').read()
    initials = []
    for line in txt.split('\n'):
        s = line.strip()
        if not s or re.match(r'^\d', s):
            continue
        core = s.rstrip('.')
        if MONTH_RE.search(core) or YEAR_RE.match(core):
            continue
        if not re.match(r'^[A-Z][a-z]{2,}', core):
            continue
        if core in FIRST:
            continue
        # Skip prefix particles (van/de/den/du) — take the main word initial
        m = re.match(r'^(?:van |vanden |van den |de |den |du )?([A-Za-z])', core)
        if m:
            initials.append(m.group(1).upper())
    if not initials:
        return None
    return Counter(initials).most_common(1)[0][0]

def find_d_range(v, n):
    """Dense probe: every ~4% of pages (skip p1 title), detect dominant letter,
    bracket the D-range, expand ±3 pages buffer."""
    probe_pages = set()
    for frac in [0.04,0.08,0.12,0.16,0.20,0.24,0.28,0.32,0.36,0.40]:
        p = max(2, min(n-1, int(n * frac)))
        probe_pages.add(p)
    probe_pages.add(2)
    probe_pages.add(3)

    for p in sorted(probe_pages):
        dl(v, p)
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for p, r in ex.map(lambda p: (p, ocr(v, p)), sorted(probe_pages)):
            if r not in ('ok','cache'):
                print(f'    probe OCR {p}: {r}', flush=True)

    letters = {}
    for p in sorted(probe_pages):
        letters[p] = page_dominant_letter(v, p)
        print(f'    p{p}: letter={letters[p]}', flush=True)

    d_pages = [p for p, l in letters.items() if l == 'D']
    if d_pages:
        d_start = min(d_pages) - 3
        d_end = max(d_pages) + 3
    else:
        # No D probes — estimate from letter progression (D ≈ 15-25% of pages)
        # Find the page where letter is C and the page where letter is E, bracket between.
        c_pages = [p for p, l in letters.items() if l == 'C']
        e_pages = [p for p, l in letters.items() if l == 'E']
        if c_pages and e_pages:
            d_start = min(c_pages) + 1
            d_end = max(e_pages) - 1
        elif c_pages:
            d_start = min(c_pages) + 1
            d_end = d_start + max(5, int(n * 0.08))
        elif e_pages:
            d_end = max(e_pages) - 1
            d_start = max(2, d_end - max(5, int(n * 0.08)))
        else:
            # Fallback: assume D ≈ 15-25% of volume
            d_start = max(2, int(n * 0.13))
            d_end = min(n-1, int(n * 0.28))
        print(f'    No D probe; bracketing D as p{d_start}-{d_end}', flush=True)

    d_start = max(2, d_start)
    d_end = min(n-1, d_end)
    return d_start, d_end

def scan_page(v, p, parish, title, drange):
    """Scan one page's OCR for Zorrok* variants; return hit dicts (or empty list)."""
    f = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if not os.path.exists(f):
        return []
    txt = open(f, errors='ignore').read()
    hits = []
    for m in VAR.finditer(txt):
        word = m.group(0)
        # Get context: ±3 lines
        lines = txt.split('\n')
        line_no = txt[:m.start()].count('\n')
        ctx = ' || '.join(l for l in lines[max(0,line_no-3):line_no+4] if l.strip())
        # Find nearby year (within 100 chars of the match)
        win = txt[max(0,m.start()-100):m.end()+100]
        years = [int(y) for y in YEAR_RE.findall(win)]
        in_range = any(1715 <= y <= 1741 for y in years)
        idx_json = json.load(open(f'{VOL_DIR}/{v}/index.json'))
        iiif = idx_json[p-1]['full_res_url'] if p-1 < len(idx_json) else '?'
        hits.append({
            'volume': v, 'parish': parish, 'title': title, 'date_range': drange,
            'page': p, 'variant': word, 'years_near': years,
            'in_range_1715_1741': in_range,
            'context': ctx[:500],
            'iiif_url': iiif,
            'ocr_file': f'cache/volumes/{v}/pages/{p:03d}.ocr.txt',
            'image': f'cache/volumes/{v}/pages/{p:03d}.jpg',
        })
    return hits

def main():
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    state = {}
    if os.path.exists(RESULTS):
        try:
            state = json.load(open(RESULTS))
        except:
            state = {}
    results = state.get('completed', {})
    all_hits = state.get('all_hits', [])

    for vid, parish, title, drange, npages in VOLS:
        if only and vid not in only:
            continue
        if vid in results and results[vid].get('done'):
            print(f'== {vid} already done (n_d_pages={results[vid]["n_d_pages"]}, hits={results[vid]["n_hits"]}) — skip', flush=True)
            continue
        print(f'\n===== {vid} ({parish} {title} {drange}, {npages}p) =====', flush=True)
        t0 = time.time()
        d_start, d_end = find_d_range(vid, npages)
        print(f'  D-section bracket: p{d_start}-p{d_end} ({d_end-d_start+1} pages)', flush=True)
        pages = list(range(d_start, d_end+1))
        for p in pages:
            r = dl(vid, p)
            if r not in ('ok','cache'):
                print(f'    DL {p}: {r}', flush=True)
        with cf.ThreadPoolExecutor(max_workers=10) as ex:
            for p, r in ex.map(lambda p: (p, ocr(vid, p)), pages):
                if r not in ('ok','cache'):
                    print(f'    OCR {p}: {r}', flush=True)
        hits = []
        for p in pages:
            hits.extend(scan_page(vid, p, parish, title, drange))
        in_range = [h for h in hits if h['in_range_1715_1741']]
        elapsed = time.time() - t0
        results[vid] = {
            'parish': parish, 'title': title, 'date_range': drange,
            'n_pages': npages, 'd_start': d_start, 'd_end': d_end,
            'n_d_pages': d_end - d_start + 1,
            'n_hits': len(hits), 'n_in_range': len(in_range),
            'elapsed_s': round(elapsed, 1), 'done': True,
        }
        all_hits = [h for h in all_hits if h.get('volume') != vid] + hits
        print(f'  Variant hits: {len(hits)} | in-range (1715-1741): {len(in_range)}', flush=True)
        for h in in_range:
            print(f'    IN-RANGE p{h["page"]}: {h["variant"]} years={h["years_near"]} :: {h["context"][:200]}', flush=True)
        for h in [x for x in hits if not x['in_range_1715_1741']]:
            print(f'    out-of-range p{h["page"]}: {h["variant"]} years={h["years_near"]}', flush=True)
        # Save after each volume (resilience)
        json.dump({'completed': results, 'all_hits': all_hits}, open(RESULTS, 'w'), indent=1)

    print(f'\n===== SUMMARY ({time.strftime("%H:%M:%S")}) =====')
    print(f'Volumes done: {sum(1 for r in results.values() if r.get("done"))}/{len(VOLS)}')
    print(f'Total variant hits: {len(all_hits)}')
    print(f'In-range (1715-1741) hits: {len([h for h in all_hits if h["in_range_1715_1741"]])}')
    json.dump({'completed': results, 'all_hits': all_hits}, open(RESULTS, 'w'), indent=1)
    print('SAVED', RESULTS)

if __name__ == '__main__':
    main()
