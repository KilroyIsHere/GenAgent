#!/usr/bin/env python3
"""Post-sweep verification pass (no-miss certifier) — FILESYSTEM-BASED.

Authoritative no-miss check for the Phase-5 sweep. Independent of the sweep's
own done flags: it verifies the ACTUAL cache files (every page has a jpg >10KB
AND a non-empty .ocr.txt), retries any holes (3 attempts each via
full_sweep.dl/ocr), and flags persistent failures to sweep_failures.json with
IIIF URL + image + ocr path + 'needs' (vision band crops / human read).
Flagged pages are SURFACED (never silently skipped) — the run completes with
them in the report as DOUBTFUL / needs-review.

Because it works off the filesystem (not the results JSON), it recovers ANY
crash state: if the sweep died at vol 10/13, the audit finds vols 11-13 have
no files, downloads+OCRs them itself, and certifies. That is the real
self-heal — the sweep's resumability is the belt, the audit is the suspenders.

Two phases (long-lived background process, gateway-parented):
  Phase 1: verify the 13 index volumes (waits for the sweep process to be
           gone). Writes lookup/audit13_done = count of unresolved (0 = clean).
  Phase 2: verify the San Felipe 6355 slice (waits for the sanfelipe flag).
           Writes lookup/audit_done = total unresolved (13 vols + 6355).

  Legacy (St Joris 6290-6293, spread-based naming): ON-DEMAND ONLY —
  `python3 sweep_audit.py --legacy`. NOT run on every future run.

Idempotent/resumable. Log: logs/sweep_audit.log.
"""
import os, json, time, subprocess
import full_sweep  # VOLS + dl/ocr (module-level, no side effects)

AUDIT13 = '/workspace/agatha/lookup/audit13_done'
AUDIT = '/workspace/agatha/lookup/audit_done'
FAILURES = '/workspace/agatha/lookup/sweep_failures.json'
SF_FLAG = '/workspace/agatha/lookup/sanfelipe_done'
SF_RES = '/workspace/agatha/lookup/sanfelipe_results.json'
LOG = '/workspace/agatha/logs/sweep_audit.log'

def log(msg):
    with open(LOG, 'a') as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    print(msg, flush=True)

def alive(pat):
    r = subprocess.run(['pgrep', '-f', pat], capture_output=True, text=True)
    return bool(r.stdout.strip())

def check_volume(vid, parish, pages, dl, ocr, idx):
    """Verify each page has jpg + non-empty ocr; retry holes; return unresolved."""
    unresolved = []
    for p in pages:
        jpg = f'{full_sweep.VOL_DIR}/{vid}/pages/{p:03d}.jpg'
        ocr_f = f'{full_sweep.VOL_DIR}/{vid}/pages/{p:03d}.ocr.txt'
        if (os.path.exists(jpg) and os.path.getsize(jpg) > 10000
                and os.path.exists(ocr_f) and os.path.getsize(ocr_f) > 0):
            continue
        r_dl = dl(p) if vid == '6355' else dl(vid, p)
        r_ocr = ((ocr(p) if vid == '6355' else ocr(vid, p))
                 if r_dl in ('ok', 'cache') else 'NODL')
        ocr_ok = os.path.exists(ocr_f) and os.path.getsize(ocr_f) > 0
        if ocr_ok:
            log(f'  RECOVERED {vid} p{p} (dl={r_dl})')
        else:
            unresolved.append({
                'volume': vid, 'parish': parish, 'page': p,
                'iiif_url': idx[p-1]['full_res_url'],
                'image': f'cache/volumes/{vid}/pages/{p:03d}.jpg',
                'ocr_file': f'cache/volumes/{vid}/pages/{p:03d}.ocr.txt',
                'dl': r_dl, 'ocr': r_ocr,
                'needs': 'vision wide-band crops (aux model) or human read; flag DOUBTFUL',
            })
            log(f'  UNRESOLVED {vid} p{p}: dl={r_dl} ocr={r_ocr}')
    return unresolved

# --- Legacy (St Joris) volumes: spread-based naming -------------------------
# OLD runs used NNN_L.jpg/NNN_R.jpg (full-res SPREAD halves, each ~2 scan pages)
# + plain NNN.jpg (full-res single-leaf). New volumes use per-page NNN.jpg +
# NNN.ocr.txt. A naive per-page audit (expecting NNN.jpg + NNN.ocr.txt)
# false-alarms hundreds of "holes" on legacy volumes — ALWAYS check both
# conventions (real incident 2026-09-16: 6290/6291/6292/6293 initially reported
# as full of holes; actual coverage was 219/220/230/140 leaves complete).
LEGACY = [
    # (vid, parish, title, leaves_total, scope_max_leaf)
    ('6290', 'St Joris', '6290', 219, 219),
    ('6291', 'St Joris', '6291', 220, 220),
    ('6292', 'St Joris', '6292', 230, 230),
    ('6293', 'St Joris', '6293 (1742-1752 window)', 284, 140),
]
AUDIT_LEGACY = '/workspace/agatha/lookup/audit_legacy_done'
MARKERS = ('[AUDIT ', 'AUDIT-VERIFIED', 'VISION-VERIFIED', 'vision-verified')

def legacy_check(vid, parish, scope_max_leaf):
    """Verify legacy-spread coverage: every in-scope leaf NNN has _L/_R jpgs
    (>10KB) + non-empty _L/_R.ocr.txt. Leaves > scope_max_leaf are OUT OF the
    research window — not holes. Returns unresolved list (empty = clean)."""
    pages_dir = f'{full_sweep.VOL_DIR}/{vid}/pages'
    if not os.path.isdir(pages_dir):
        return [{'volume': vid, 'parish': parish, 'page': None,
                 'issue': 'pages dir missing entirely', 'needs': 're-init + re-sweep'}]
    ocr_names = set(n[:-len('.ocr.txt')] for n in os.listdir(pages_dir)
                    if n.endswith('.ocr.txt'))
    unresolved = []
    for n in range(1, scope_max_leaf + 1):
        for side in ('L', 'R'):
            key = f'{n:03d}_{side}'
            jpg = f'{pages_dir}/{key}.jpg'
            ocr_f = f'{pages_dir}/{key}.ocr.txt'
            if (os.path.exists(jpg) and os.path.getsize(jpg) > 10000
                    and os.path.exists(ocr_f) and os.path.getsize(ocr_f) > 0):
                # (vision-verified blank markers count as non-empty OCR results)
                continue
            unresolved.append({
                'volume': vid, 'parish': parish, 'leaf': n, 'side': side,
                'convention': 'legacy-spread',
                'image': f'cache/volumes/{vid}/pages/{key}.jpg',
                'ocr_file': f'cache/volumes/{vid}/pages/{key}.ocr.txt',
                'iiif_url': '(see St Joris index 6260/6262; leaf NNN = 2 scan pages)',
                'issue': 'missing jpg and/or ocr file',
                'needs': 're-download via agatha_cache / re-OCR; flag DOUBTFUL if unreadable',
            })
            log(f'  LEGACY UNRESOLVED {vid} {key}: missing jpg/ocr')
    return unresolved

def phase_legacy():
    """Audit the legacy St Joris volumes (already closed — verify only, no
    re-download/re-OCR here; holes, if any, are handled by the St Joris
    dl/ocr range scripts). Idempotent; runs before waiting on the sweep."""
    log('Auditing legacy St Joris volumes (dual-convention check).')
    failures = []
    for vid, parish, title, leaves_total, scope_max in LEGACY:
        unres = legacy_check(vid, parish, scope_max)
        failures.extend(unres)
        log(f'legacy audit {vid} ({title}, {scope_max}/{leaves_total} in scope): '
            f'{len(unres)} unresolved')
    json.dump(failures, open('/workspace/agatha/lookup/legacy_failures.json',
                             'w'), indent=1)
    with open(AUDIT_LEGACY, 'w') as f:
        f.write(str(len(failures)))
    log(f'Legacy audit complete: {len(failures)} unresolved (0 = clean) -> audit_legacy_done')
    return failures

def phase1():
    while alive('full_sweep.py'):
        log('Sweep still running. Sleeping 120s...')
        time.sleep(120)
    log('Sweep process gone. Auditing 13 index volumes (filesystem).')
    failures = []
    for vid, parish, title, drange, npages in full_sweep.VOLS:
        idx = json.load(open(f'{full_sweep.VOL_DIR}/{vid}/index.json'))
        unres = check_volume(vid, parish, list(range(1, npages + 1)),
                             full_sweep.dl, full_sweep.ocr, idx)
        failures.extend(unres)
        log(f'audit {vid}: {len(unres)} unresolved')
    json.dump(failures, open(FAILURES, 'w'), indent=1)
    with open(AUDIT13, 'w') as f:
        f.write(str(len(failures)))
    log(f'Phase 1 complete: {len(failures)} unresolved (0 = clean) -> audit13_done')
    return failures

def phase2(failures):
    while not os.path.exists(SF_FLAG):
        if alive('sanfelipe_6355.py'):
            log('San Felipe slice running. Sleeping 120s...')
        else:
            log('San Felipe not running, no flag yet (watcher relaunches). Sleeping 120s...')
        time.sleep(120)
    log('San Felipe flag set. Auditing 6355 slice.')
    import sanfelipe_6355 as sf
    try:
        sr = json.load(open(SF_RES))
        pages = list(range(sr['slice_pages'][0], sr['slice_pages'][1] + 1))
    except Exception:
        pages = list(range(1, sf.N_PAGES + 1))
        log('No slice_pages in results; auditing full 6355 (206p).')
    idx = json.load(open(f'{sf.VOL_DIR}/index.json'))
    unres = check_volume('6355', 'San Felipe del Castilla', pages, sf.dl, sf.ocr, idx)
    failures = [f for f in failures if f.get('volume') != '6355'] + unres
    json.dump(failures, open(FAILURES, 'w'), indent=1)
    with open(AUDIT, 'w') as f:
        f.write(str(len(failures)))
    log(f'Phase 2 complete: {len(failures)} total unresolved (0 = clean) -> audit_done')

def main(legacy=False):
    # LEGACY CHECK IS ON-DEMAND ONLY (user decision 2026-09-16): St Joris
    # 6290-6293 are CLOSED — re-checking them on every future run is noise.
    # Run with `python3 sweep_audit.py --legacy` when a legacy audit is
    # explicitly requested. Not part of the default run.
    if legacy:
        phase_legacy()
    f1 = phase1()
    phase2(f1)

if __name__ == '__main__':
    main(legacy='--legacy' in __import__('sys').argv)
