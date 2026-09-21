#!/usr/bin/env python3
"""Phase 5 — San Felipe (parish 16) 6355 baptism REGISTER slice.

6355 is a chronological register 1700-1795 (206 pages), NOT an alphabetical
index — the only available covering source for San Felipe. Strategy:
  1. WAIT for the 13-volume full sweep to finish (Kraken OOMs >3 parallel jobs;
     do not run concurrent batches).
  2. Map year->page with spread anchors (chronological registers are monotonic),
     pin the 1715-1741 page range, add +/-5 margin. If the anchors are
     ambiguous (non-monotonic), fall back to OCR-ing the FULL 206 pages.
  3. Download + OCR the slice (10-way parallel Kraken small), scan for Zorrok*
     variants + 1715-1741 dates, save all hits with context + IIIF URL.
  4. Set the done flag so the cron monitor flips sanfelipe=done.

Resumable. Log: logs/sanfelipe_6355.log. Results: lookup/sanfelipe_results.json.
"""
import os, re, json, time, subprocess, concurrent.futures as cf

VOL = '6355'
VOL_DIR = f'/workspace/agatha/cache/volumes/{VOL}'
COOKIE = open('/workspace/agatha/cache/session_cookie.txt').read().strip()
REF = 'https://agatha.arch.be/'
URL = 'http://host.docker.internal:8008/ocr-path'
RESULTS = '/workspace/agatha/lookup/sanfelipe_results.json'
FLAG = '/workspace/agatha/lookup/sanfelipe_done'
LOG = '/workspace/agatha/logs/sanfelipe_6355.log'
N_PAGES = 206
YEAR_LO, YEAR_HI = 1715, 1741

VAR = re.compile(r'\bdo[rz][rre]*[a-z]{0,8}\b', re.I)
YEAR_RE = re.compile(r'\b1[67][0-9][0-9]\b')
IDX = json.load(open(f'{VOL_DIR}/index.json'))

def log(msg):
    with open(LOG, 'a') as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    print(msg, flush=True)

def dl(p):
    dst = f'{VOL_DIR}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return 'cache'
    last = 'ERR'
    for attempt in range(3):
        r = subprocess.run(
            ['curl','-sS','-f','-o',dst+'.part','-H',f'Referer: {REF}',
             '-H',f'Cookie: {COOKIE}','-w','%{http_code}', IDX[p-1]['full_res_url']],
            capture_output=True, text=True)
        if (r.returncode == 0 and r.stdout.strip() == '200'
                and os.path.exists(dst+'.part') and os.path.getsize(dst+'.part') > 10000):
            os.rename(dst+'.part', dst)
            return 'ok'
        last = f'ERR {r.stdout} {r.stderr[:60]}'
        time.sleep(3*(attempt+1))
    return last

def ocr(p):
    img = f'{VOL_DIR}/pages/{p:03d}.jpg'
    out = f'{VOL_DIR}/pages/{p:03d}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return 'cache'
    if not (os.path.exists(img) and os.path.getsize(img) > 10000):
        return 'NODL'
    last = 'EMPTY'
    for attempt in range(3):
        r = subprocess.run(
            ['curl','-sS','-X','POST',URL,'-H','Content-Type: application/json',
             '-d',json.dumps({'path':img,'model':'small.safetensors'}),'-o',out],
            capture_output=True, text=True, timeout=300)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return 'ok'
        if os.path.exists(out):
            os.remove(out)  # 0-byte file would be mistaken for 'cache' on retry
        last = f'EMPTY {r.stderr[:80]}'
        time.sleep(3*(attempt+1))
    return last

def ocr_range(pages):
    ok = fail = 0
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(ocr, p): p for p in pages}
        for fut in cf.as_completed(futs):
            r = fut.result()
            if r in ('ok','cache'): ok += 1
            else:
                fail += 1; log(f"  OCR FAIL p{futs[fut]}: {r}")
    return ok, fail

def page_years(p):
    f = f'{VOL_DIR}/pages/{p:03d}.ocr.txt'
    if not os.path.exists(f): return []
    return [int(y) for y in YEAR_RE.findall(open(f, errors='ignore').read())]

def scan(p):
    f = f'{VOL_DIR}/pages/{p:03d}.ocr.txt'
    if not os.path.exists(f): return []
    txt = open(f, errors='ignore').read()
    out = []
    for m in VAR.finditer(txt):
        word = m.group(0)
        if word.lower() in ('dobbelaer','dorp','zoro'): continue
        lines = txt.split('\n')
        ln = txt[:m.start()].count('\n')
        ctx = ' || '.join(l for l in lines[max(0,ln-4):ln+5] if l.strip())
        win = txt[max(0,m.start()-150):m.end()+150]
        years = [int(y) for y in YEAR_RE.findall(win)]
        out.append({'page': p, 'variant': word, 'years_near': years,
                    'in_range': any(YEAR_LO <= y <= YEAR_HI for y in years),
                    'context': ctx[:600], 'iiif_url': IDX[p-1]['full_res_url'],
                    'ocr_file': f'cache/volumes/{VOL}/pages/{p:03d}.ocr.txt',
                    'image': f'cache/volumes/{VOL}/pages/{p:03d}.jpg'})
    return out

def wait_for_sweep():
    # Wait until the audit has certified the 13 index volumes (audit13_done
    # EXISTS). That is the no-miss gate: it is filesystem-verified (every page
    # has a jpg + non-empty OCR), independent of the sweep's own done flags, so
    # the slice starts only after the 13 vols are actually read.
    while True:
        try:
            state = open('/workspace/agatha/lookup/audit13_done').read().strip()
        except Exception:
            state = 'pending'
        if state != 'pending':
            log(f"13 index volumes certified (unresolved={state}). Starting 6355 slice.")
            return
        log("audit13_done not set yet (waiting for 13-vol certification). Sleeping 120s...")
        time.sleep(120)

def main():
    if os.path.exists(FLAG):
        log("Already done, exiting."); return
    wait_for_sweep()
    # --- map anchors: 11 spread pages across 206 ---
    anchors = [1, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200]
    log("Mapping anchors: " + ", ".join(f"p{a}" for a in anchors))
    for a in anchors:
        dl(a)
    ok, fail = ocr_range(anchors)
    log(f"Anchors OCR: {ok} ok, {fail} fail")
    # find first page >= YEAR_LO and last page <= YEAR_HI from anchors
    lo_page = hi_page = None
    for a in anchors:
        ys = page_years(a)
        if lo_page is None and any(y >= YEAR_LO for y in ys):
            lo_page = a
        if any(y <= YEAR_HI for y in ys) and (hi_page is None or a < hi_page):
            hi_page = a
    if lo_page is None:
        lo_page = anchors[0]
    if hi_page is None:
        hi_page = anchors[-1]
    # check monotonicity: a later anchor should not carry an earlier year than an earlier anchor
    mono = True
    prev_max = -1
    for a in anchors:
        ys = [y for y in page_years(a) if 1600 <= y <= 1900]
        if ys:
            m = max(ys)
            if m < prev_max - 20:  # big backwards jump = non-monotonic
                mono = False
            prev_max = max(prev_max, m)
    if mono:
        start = max(1, lo_page - 5)
        end = min(N_PAGES, hi_page + 5)
        log(f"Monotonic. Slice p{start}-p{end} (lo anchor p{lo_page}, hi anchor p{hi_page}).")
    else:
        start, end = 1, N_PAGES
        log("NON-MONOTONIC anchors detected -> falling back to FULL 206-page scan.")
    pages = list(range(start, end + 1))
    log(f"Downloading {len(pages)} pages...")
    dl_ok = 0
    for p in pages:
        if dl(p) == 'ok': dl_ok += 1
    log(f"Downloaded {dl_ok}/{len(pages)} fresh (rest cached). OCR...")
    ok, fail = ocr_range(pages)
    log(f"Slice OCR: {ok} ok, {fail} fail")
    hits = []
    for p in pages:
        hits.extend(scan(p))
    in_range = [h for h in hits if h['in_range']]
    res = {'volume': VOL, 'parish': 'San Felipe del Castilla',
           'type': 'baptism register', 'date_range': '1700-1795',
           'slice_pages': [start, end], 'mono': mono,
           'n_hits': len(hits), 'n_in_range': len(in_range),
           'hits': hits, 'done': True}
    json.dump(res, open(RESULTS, 'w'), indent=1)
    open(FLAG, 'w').write(time.strftime('%Y-%m-%d %H:%M UTC'))
    log(f"DONE. hits={len(hits)} in-range={len(in_range)}")
    for h in in_range:
        log(f"  IN-RANGE p{h['page']}: {h['variant']} years={h['years_near']} :: {h['context'][:180]}")

if __name__ == '__main__':
    main()
