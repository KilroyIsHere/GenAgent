#!/usr/bin/env python3
"""PHASE 5 orchestrator — multi-parish REGISTER sweep (Antwerp, 1667-1712).

Trigger: the Phase 4 multi-parish INDEX sweep returned 0 CONFIRMED / 0
DOUBTFUL (all 28 indexes). Per the plan + the STATUS.md conclusion, the
remaining avenue is a DIRECT REGISTER sweep (not index-first): apply the
validated two-pass fuzzy matcher to the baptism REGISTER text (child + father
on the same entry) across every in-window (1667-1712) digitized register
volume, same city (Antwerp), same window, same matcher.

Standing rules (user):
  * Structure is NEVER assumed (not even from same-parish siblings); assessed
    per-volume and per-page from each volume's own OCR. The register matcher
    (scan_frederic.py) does per-page structure detection itself (child-after
    Infans vs child-first filia/filia), so a 0-hit on an unassessed page is not
    a reliable no-hit.
  * No-miss: OCR the whole in-window slice per volume; a clean header is a
    floor, not a boundary; if a boundary OCRs garbled, extend. If a STRONG
    (in-window) hit falls at/outside a banded edge, fall back to whole volume.
  * DOUBTFUL beats Excluded: crop-verify every fuzzy STRONG before reporting.
  * Per-volume START + FINISH (full per-row detail) written to STATUS.md.

Per volume (chronological register):
  P0 discover: coarse grid (stride 4) download+OCR -> read per-page year tokens
     to bracket the in-window page range (registers are chronological).
  P1 band: OCR the in-window page slice (band = [p_lo, p_hi] +/- buffer;
     whole volume if the span is within the window or years can't be read).
  P2 scan: run the validated two-pass register matcher (scan_frederic.scan_one
     slot-aware + line_pass structure-agnostic safety net) over band+grid
     leaves. STRONG = father-zone Zorok* + child-zone Frederic* (in-window).
     GAP = a line-pass hit the slot parser missed (garbled Infans marker).
  P3 no-miss: if an in-window STRONG fell outside the band, re-OCR whole vol.

Resumable (cache-first: skips cached pages + OCR'd leaves). Single Kraken
batch at a time (ooms >3 jobs). PID-file liveness (immune to argv self-match).
State: p5_state.json (deterministic monitor input).
"""
import os, re, sys, time, json, glob, subprocess

AG = '/workspace/agatha'
RUN = f'{AG}/runs/frederic_zorokens'
PAGE_DIR = f'{AG}/cache/volumes'
OCR_BATCH = f'{AG}/ocr_batch.sh'
STATE = f'{RUN}/p5_state.json'
HITS = f'{RUN}/p5_hits.json'
sys.path.insert(0, AG)
sys.path.insert(0, RUN)
import agatha_cache as ac
import scan_frederic as sf   # the validated two-pass register matcher

WINDOW = (1667, 1712)
STRIDE = 4          # discovery grid stride (read year tokens per page)
BAND_BUF = 6        # buffer pages either side of the estimated in-window band
MAX_PAGE = 460      # sanity cap (all NEW register vols <= 413 pp)

# In-window register volumes (parish, span label, in-window year slice).
# 33 NEW (init'd, 0 pages cached) + 6 cached in-window (zero-OCR re-scan).
# The 8 excluded parishes with no digitized in-window source are NOT here
# (recorded as Excluded in STATUS.md, not "not found").
VOLS = [
    # ---- Christ. Gereform. (11) ----
    ('6367', 'Christ. Gereform. (11)', '1660-1667', 1667, 1667),
    ('6372', 'Christ. Gereform. (11)', '1660-1787', 1667, 1712),
    # ---- OLV-Noord (14) ----
    ('6150', 'OLV-Noord (14)',         '1663-1687', 1667, 1687),
    ('6149', 'OLV-Noord (14)',         '1682-1682', 1682, 1682),
    ('6151', 'OLV-Noord (14)',         '1688-1705', 1688, 1705),
    ('6152', 'OLV-Noord (14)',         '1705-1725', 1705, 1712),
    # ---- OLV-Zuid (15) ----
    ('6110', 'OLV-Zuid (15)',          '1658-1670', 1667, 1670),
    ('6113', 'OLV-Zuid (15)',          '1670-1687', 1670, 1687),
    ('6116', 'OLV-Zuid (15)',          '1688-1700', 1688, 1700),
    ('6117', 'OLV-Zuid (15)',          '1701-1717', 1701, 1712),
    # ---- San Felipe (16) ----
    ('6354', 'San Felipe (16)',        '1658-1700', 1667, 1700),
    ('6355', 'San Felipe (16)',        '1700-1795', 1700, 1712),   # cached
    # ---- St-Jacobus (19) ----
    ('6169', 'St-Jacobus (19)',        '1665-1672', 1667, 1712),
    ('6170', 'St-Jacobus (19)',        '1672-1685', 1672, 1685),
    ('6171', 'St-Jacobus (19)',        '1685-1693', 1685, 1693),
    ('6172', 'St-Jacobus (19)',        '1693-1703', 1693, 1703),
    ('6173', 'St-Jacobus (19)',        '1704-1722', 1704, 1712),
    # ---- St-Joris (20) ----
    ('6283', 'St-Joris (20)',          '1664-1673', 1667, 1712),
    ('6284', 'St-Joris (20)',          '1674-1683', 1674, 1683),
    ('6282', 'St-Joris (20)',          '1680-1680', 1680, 1680),
    ('6286', 'St-Joris (20)',          '1683-1689', 1683, 1689),
    ('6287', 'St-Joris (20)',          '1690-1700', 1690, 1700),
    ('6288', 'St-Joris (20)',          '1700-1705', 1700, 1705),
    ('6289', 'St-Joris (20)',          '1705-1712', 1705, 1712),
    ('6290', 'St-Joris (20)',          '1712-1720', 1712, 1712),   # cached
    # ---- St-Laurentius (21) ----
    ('6321', 'St-Laurentius (21)',     '1659-1676', 1667, 1712),
    ('6323', 'St-Laurentius (21)',     '1667-1687', 1667, 1687),
    ('6325', 'St-Laurentius (21)',     '1688-1721', 1688, 1712),
    # ---- St-Walburga (24) ----
    ('6203', 'St-Walburga (24)',       '1665-1677', 1667, 1712),
    ('6204', 'St-Walburga (24)',       '1678-1696', 1678, 1696),
    ('6205', 'St-Walburga (24)',       '1696-1700', 1696, 1700),
    ('6206', 'St-Walburga (24)',       '1701-1712', 1701, 1712),
    # ---- St-Willibrordus (25) ----
    ('6304', 'St-Willibrordus (25)',   '1654-1698', 1667, 1698),
    ('6303', 'St-Willibrordus (25)',   '1687-1687', 1687, 1687),
    ('6305', 'St-Willibrordus (25)',   '1698-1778', 1698, 1712),
    # ---- St-Andries (17) — ANCHOR parish, cached (zero-OCR re-scan; Phase 2/3
    #      already reported NOT FOUND, re-scanned here so the multi-parish
    #      register sweep is complete and the matcher result reproduces) ----
    ('6243', 'St-Andries (17)',        '1660-1671', 1667, 1671),
    ('6244', 'St-Andries (17)',        '1671-1685', 1671, 1685),
    ('6245', 'St-Andries (17)',        '1685-1706', 1685, 1706),
    ('6246', 'St-Andries (17)',        '1706-1727', 1706, 1712),
]
N_VOLS = len(VOLS)
CACHED = {'6355', '6290', '6243', '6244', '6245', '6246'}  # zero-OCR re-scan

YEAR_RE = sf.YEAR_RE

# ---- download (cache-first, 3-retry, ensure-on-first-fail) ----
def download_page(vol, p):
    dst = f'{PAGE_DIR}/{vol}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return True
    for attempt in range(3):
        try:
            ac.cmd_get(vol, p)
            if os.path.exists(dst) and os.path.getsize(dst) > 10000:
                return True
        except SystemExit:
            if attempt == 0:
                try: ac.cmd_ensure()
                except SystemExit: return False
        except Exception:
            return False
        if os.path.exists(dst + '.part'):
            try: os.unlink(dst + '.part')
            except Exception: pass
        time.sleep(0.4)
    return False

def ocr_vol(vol, pages):
    """Run ocr_batch.sh for the pages that still need OCR (cache-first)."""
    todo = []
    for p in pages:
        for s in ('L', 'R'):
            o = f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt'
            if not (os.path.exists(o) and os.path.getsize(o) > 0):
                todo.append(p); break
    if not todo:
        return True
    # chunk long lists so one crash doesn't lose the whole volume (resumable)
    CH = 60
    for i in range(0, len(sorted(set(todo))), CH):
        chunk = sorted(set(todo))[i:i+CH]
        r = subprocess.run(['bash', OCR_BATCH, vol] + [str(p) for p in chunk],
                           capture_output=True, text=True, timeout=7200)
        # a leaf is DONE when its .ocr.txt EXISTS (any size). 0-byte = Kraken
        # read nothing (dark/blank scan, terminal). MISSING = real failure.
        incomplete = [p for p in chunk for s in ('L', 'R')
                      if os.path.exists(f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.jpg')
                      and not os.path.exists(f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt')]
        if incomplete:
            return False
    return True

def vol_n_pages(vol):
    p = f'{PAGE_DIR}/{vol}/index.json'
    if not os.path.exists(p): return MAX_PAGE
    try:
        ix = json.load(open(p))
        return len(ix) if isinstance(ix, list) else len(ix.get('pages', []))
    except Exception:
        return MAX_PAGE

def load_idx(vol):
    p = f'{PAGE_DIR}/{vol}/index.json'
    if not os.path.exists(p): return []
    try: return json.load(open(p))
    except Exception: return []

# =================== state + monitor ===================
def save_state(state):
    state['ts'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    json.dump(state, open(STATE, 'w'), indent=1)

def load_state():
    if os.path.exists(STATE):
        try: return json.load(open(STATE))
        except Exception: pass
    return {'vols': {}, 'phase': 'running', 'done': False}

def ocr_count(vol):
    return len(glob.glob(f'{PAGE_DIR}/{vol}/pages/*.ocr.txt'))

# =================== year-band discovery ===================
def leaf_years(ocr_path):
    if not os.path.exists(ocr_path) or os.path.getsize(ocr_path) <= 0:
        return []
    txt = open(ocr_path, errors='ignore').read()
    return [int(y) for y in YEAR_RE.findall(txt)]

def estimate_band(vol, grid, n, win_lo, win_hi):
    """Bracket the in-window page range from the grid's per-page year tokens.
    Returns (band, fallback). Register is chronological -> in-window pages are
    contiguous. If years can't be read or the window spans the whole volume,
    fallback to the whole volume (no-miss)."""
    # collect (page, year) samples
    samp = []
    for p in grid:
        for s in ('L', 'R'):
            ys = leaf_years(f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt')
            for y in ys:
                samp.append((p, y))
    if not samp:
        return [1, n], True   # no year tokens anywhere -> whole volume (no-miss)
    # earliest page whose years reach win_lo, latest page whose years reach win_hi
    in_win = [p for p, y in samp if win_lo <= y <= win_hi]
    below = [p for p, y in samp if y < win_lo]
    above = [p for p, y in samp if y > win_hi]
    lo_y = min(y for _, y in samp); hi_y = max(y for _, y in samp)
    # UNCERTAINTY -> whole volume (no-miss default). The band is only trusted
    # when the grid's year-samples actually CONFIRM an in-window page AND the
    # samples span the window (a page before 1667 and a page after 1712).
    if not in_win:
        return [1, n], True        # no grid page in-window -> can't bracket safely
    if lo_y >= win_lo and hi_y <= win_hi:
        return [1, n], False       # whole volume is in-window (nothing to band)
    if not (below and above):
        return [1, n], True        # samples don't straddle the window -> don't trust
    p_lo = min(in_win); p_hi = max(in_win)
    band = [max(1, p_lo - BAND_BUF), min(n, p_hi + BAND_BUF)]
    # thin bracket (<3 in-window grid samples) -> widen to whole volume (no-miss)
    if len(set(in_win)) < 3:
        return [1, n], True
    return band, False

# =================== STATUS.md (per-volume START/FINISH, standing rule) ===================
STATUS = ('/vault/genealogy/AI Searches/'
          'Birth of Frederic Zorokens (father of Johannes Petri 1722)/STATUS.md')
LINK = '../../../../workspace/agatha/'

def _ts():
    return time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())

def _append(s):
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    with open(STATUS, 'a') as f:
        f.write(s)

def _rel(p):
    if p.startswith('/workspace/agatha/'):
        return p.split('/workspace/agatha/', 1)[1]
    return p

def status_start(vol, parish, span, win, n):
    _append(f"\n---\n\n## {vol} — {parish} baptism REGISTER ({span}, in-window {win[0]}–{win[1]}) — START — {_ts()}\n\n")
    _append(f"- pages: {n} total; in-window slice {win[0]}–{win[1]} (year-band discovery, whole slice = no-miss)\n")
    _append("- structure: **assessed per-page from this volume's own OCR (child-after Infans vs child-first filia/filia) — never assumed**; layout can change mid-volume\n")
    _append(f"- status: in progress…\n\n")

def _ev(h):
    img = _rel(h.get('image', '') if h.get('image','').startswith('/') else f'/workspace/agatha/{h.get("image","")}');
    ocr = _rel(h.get('ocr_file', '') if h.get('ocr_file','').startswith('/') else f'/workspace/agatha/{h.get("ocr_file","")}')
    s = f"[image]({LINK}{img}) · [OCR]({LINK}{ocr})"
    if h.get('iiif_url'):
        s += f" · [full-res]({h['iiif_url']})"
    return s

def status_finish(vol, parish, span, win, vp, all_hits, gaps, ocr_done, ocr_total, band):
    strong = [h for h in all_hits if h['verdict'] == 'STRONG' and h.get('in_window_1667_1712')]
    near   = [h for h in all_hits if h['verdict'] == 'NEAR'   and h.get('in_window_1667_1712')]
    father = [h for h in all_hits if h['verdict'] == 'FATHER' and h.get('in_window_1667_1712')]
    oow    = [h for h in all_hits if h['verdict'] == 'STRONG' and not h.get('in_window_1667_1712')]
    excl   = [h for h in all_hits if h.get('excluded_lineage')]
    binit  = [h for h in all_hits if h.get('b_initial') and not h.get('excluded_lineage')]
    band_s = f"{band[0]}–{band[1]}" if band else '?'
    fb = ' · **whole-volume (no-miss)**' if vp.get('fallback') else ''
    kind = vp.get('structure_kind', '?')
    _append(f"\n---\n\n## {vol} — {parish} baptism REGISTER ({span}, in-window {win[0]}–{win[1]}) — FINISH — {_ts()}\n\n")
    _append(f"- pages OCR'd: {band_s} of {vp.get('n_pages','?')} · **structure per-page={kind}{fb}**\n")
    _append(f"- OCR: {ocr_done}/{ocr_total} leaves in slice\n")
    _append(f"- in-window (1667–1712): **{len(strong)} STRONG (father Zorok* + child Frederic, crop-verify)** · "
            f"{len(near)} NEAR (Frederic in godparent zone) · {len(father)} FATHER-only (corroboration) · "
            f"{len(binit)} B-initial (Borrokens* — DOUBTFUL crop-verify) · {len(excl)} excluded-lineage · "
            f"{len(oow)} STRONG out-of-window\n")
    # STRONG rows
    if strong:
        _append(f"\n#### {vol} — STRONG (crop-verify, DOUBTFUL until crop agrees)\n\n")
        _append("| # | Page | Leaf | Zorok* (edit) | Frederic child (edit) | Father zone | Child zone | Yr | Evidence |\n")
        _append("|---|------|------|---------------|------------------------|-------------|------------|----|----------|\n")
        for i, h in enumerate(strong, 1):
            _append(f"| {i} | {h['page']} | {h['leaf']} | `{h['father_zorok_tok']}` (d{h['father_zorok_edit']}, binit={h['b_initial']}) "
                    f"| `{h['fred_child_tok']}` (d{h['fred_child_edit']}) | {','.join(h['father_tokens'][:5])} "
                    f"| {','.join(h['child_zone_tokens'][:4])} | {'/'.join(str(y) for y in h['years_near']) or '—'} | {_ev(h)} |\n")
    # NEAR rows
    if near:
        _append(f"\n#### {vol} — NEAR (Frederic in godparent zone — crop-verify)\n\n")
        _append("| # | Page | Leaf | Zorok* (edit) | Frederic godp (edit) | Child zone | Yr | Evidence |\n")
        _append("|---|------|------|---------------|----------------------|------------|----|----------|\n")
        for i, h in enumerate(near, 1):
            _append(f"| {i} | {h['page']} | {h['leaf']} | `{h['father_zorok_tok']}` (d{h['father_zorok_edit']}) "
                    f"| `{h['fred_godp_tok']}` (d{h['fred_godp_edit']}) | {','.join(h['child_zone_tokens'][:4])} "
                    f"| {'/'.join(str(y) for y in h['years_near']) or '—'} | {_ev(h)} |\n")
    # FATHER-only (corroboration) — compact
    if father:
        _append(f"\n#### {vol} — FATHER-only (Zorok* father, child ≠ Frederic — family present, corroboration)\n\n")
        for h in father[:40]:
            _append(f"- p{h['page']}/{h['leaf']}: `{h['father_zorok_tok']}` (d{h['father_zorok_edit']}) "
                    f"child={','.join(h['child_zone_tokens'][:3])} yr={h['years_near']} · {_ev(h)}\n")
    # GAP (slot-parser-missed) — crop-verify
    if gaps:
        _append(f"\n#### {vol} — GAP (line co-occurrence the slot parser missed — crop-verify)\n\n")
        _append("| # | Page | Leaf | Zorok* (edit) | Frederic* (edit) | Yr | Evidence |\n")
        _append("|---|------|------|---------------|-------------------|----|----------|\n")
        for i, h in enumerate(gaps, 1):
            _append(f"| {i} | {h['page']} | {h['leaf']} | `{h['line_zorok_tok']}` (d{h['line_zorok_edit']}) "
                    f"| `{h['line_fred_tok']}` (d{h['line_fred_edit']}) | {'/'.join(str(y) for y in h['years_near']) or '—'} | {_ev(h)} |\n")
    if not (strong or near or father or gaps or excl or oow):
        _append(f"\n**0 candidate entries** in the in-window slice — no Zorok* father-block entry and no "
                f"line co-occurrence. Structure assessed per-page from this volume's own OCR; slice "
                f"{band_s} covers {win[0]}–{win[1]}.{'' if not vp.get('fallback') else ' (whole-volume = no-miss)'}\n")
    _append(f"\n_Tier meaning (register, two-pass validated matcher): **STRONG** = father-zone Zorok* AND "
            f"child-zone Frederic* (Levenshtein<=3), in 1667–1712 → crop-verify (DOUBTFUL until crop agrees). "
            f"**NEAR** = Zorok* father + Frederic in godparent zone. **FATHER** = Zorok* father, child ≠ "
            f"Frederic (sibling/corroboration). **GAP** = a Zorok*+Frederic* line co-occurrence the "
            f"slot-aware parser missed (garbled Infans marker) → crop-verify. **B-initial** = Borrokens* "
            f"(D→B misread plausible) → DOUBTFUL. **excluded-lineage** = Zoron/Zooren (distinct family). "
            f"Structure detected per-page (child-after Infans vs child-first filia/filia); never assumed._\n\n")

PIDFILE = f'{RUN}/p5_run.pid'
def write_pid():
    try: open(PIDFILE, 'w').write(str(os.getpid()))
    except Exception: pass
def clear_pid():
    try: os.unlink(PIDFILE)
    except Exception: pass

# ---- P2 scan: run the validated two-pass matcher over the OCR'd leaves ----
def scan_volume(vol, parish, span, win, idx, pages_covered):
    """Call sf.scan_one (slot-aware) + sf.line_pass (safety net) per leaf in
    pages_covered. Pass lo=1, hi=MAX (wide) — in-window is decided by the
    matcher's own year-anchoring. Returns (all_hits, gaps)."""
    lo, hi = 1, MAX_PAGE
    idx_list = idx if isinstance(idx, list) else []
    all_hits, line_hits = [], []
    seen = set()
    for p in sorted(set(pages_covered)):
        for s in ('L', 'R'):
            ocr = f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt'
            if not (os.path.exists(ocr) and os.path.getsize(ocr) > 0):
                continue
            for h in sf.scan_one(ocr, vol, parish, 'bapt REGISTER', f'{win[0]}-{win[1]}', lo, hi, idx_list):
                key = (vol, h['page'], h['infans_line'], h['leaf'])
                if key not in seen:
                    seen.add(key); all_hits.append(h)
            line_hits.extend(sf.line_pass(ocr, vol, parish, 'bapt REGISTER', f'{win[0]}-{win[1]}', lo, hi, idx_list))
    # GAP = line_pass hit on a (vol,page) the slot parser found NO Zorok* entry on
    slot_covered = set(h['page'] for h in all_hits)
    gaps, gseen = [], set()
    for g in line_hits:
        if g['page'] in slot_covered:
            continue
        k = (g['page'], g['leaf'], g['line'])
        if k not in gseen:
            gseen.add(k); gaps.append(g)
    gaps.sort(key=lambda g: (g['line_zorok_edit'], g['line_fred_edit'], g['page']))
    return all_hits, gaps

def _main_inner(t0):
    state = load_state()
    if state.get('done'):
        print('PHASE 5 ALREADY DONE — nothing to do', flush=True)
        return
    idx_cache = {}
    for vol, parish, span, win_lo, win_hi in VOLS:
        vp = state['vols'].setdefault(vol, {'parish': parish, 'span': span,
                                            'win': [win_lo, win_hi], 'phase': 'pending',
                                            'band': None, 'n_hits': 0, 'n_strong': 0,
                                            'n_near': 0, 'n_gap': 0, 'fallback': False,
                                            'started': False, 'complete': False})
        if vp.get('complete'):
            continue
        n = min(vol_n_pages(vol), MAX_PAGE)
        vp['n_pages'] = n
        idx = idx_cache.get(vol)
        if idx is None:
            idx = load_idx(vol); idx_cache[vol] = idx

        # ---- P0 discovery (coarse grid to bracket in-window pages) ----
        if vp['phase'] in ('pending', 'discover', 'discover-failed'):
            grid = list(range(1, n + 1, STRIDE))
            if not vp.get('started'):
                status_start(vol, parish, span, (win_lo, win_hi), n)
                vp['started'] = True
            vp['phase'] = 'discover'
            save_state(state)
            for p in grid:
                if not download_page(vol, p):
                    vp['phase'] = 'discover-failed'; save_state(state); break
            if vp['phase'] == 'discover-failed':
                print(f'  {vol}: download fail on grid — leaving for retry', flush=True); continue
            if not ocr_vol(vol, grid):
                vp['phase'] = 'discover-failed'; save_state(state)
                print(f'  {vol}: discovery OCR incomplete — will resume', flush=True); continue
            band, fallback = estimate_band(vol, grid, n, win_lo, win_hi)
            vp['band'] = band; vp['fallback'] = fallback
            # per-page structure sample (record a few for the FINISH note)
            struct_kinds = []
            for p in grid[:12]:
                for s in ('L', 'R'):
                    op = f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt'
                    if os.path.exists(op) and os.path.getsize(op) > 0:
                        stream, _ = sf.tokenize_leaf(op)
                        struct_kinds.append(sf.detect_structure(stream))
            from collections import Counter
            vp['structure_kind'] = Counter(struct_kinds).most_common(1)[0][0] if struct_kinds else 'unknown'
            vp['phase'] = 'band'
            save_state(state)
            print(f'  {vol} [{parish}] {span}: structure={vp["structure_kind"]} band={band} fallback={fallback}', flush=True)

        # ---- P1 band OCR (whole in-window slice; re-enters on band-failed) ----
        if vp['phase'] in ('band', 'band-failed'):
            if vp['phase'] == 'band-failed':
                vp['phase'] = 'band'; save_state(state)
            lo, hi = vp['band']
            band_pages = list(range(lo, hi + 1))
            for p in band_pages:
                if not download_page(vol, p):
                    vp['phase'] = 'band-failed'; save_state(state); break
            if vp['phase'] == 'band-failed':
                print(f'  {vol}: band download fail — resume', flush=True); continue
            if not ocr_vol(vol, band_pages):
                vp['phase'] = 'band-failed'; save_state(state)
                print(f'  {vol}: band OCR incomplete — resume', flush=True); continue
            vp['phase'] = 'scan'
            save_state(state)

        # ---- P2 scan (band + discovery grid = no-miss over all OCR'd pages) ----
        if vp['phase'] == 'scan':
            lo, hi = vp['band']
            grid_pages = set(range(1, n + 1, STRIDE))
            ocr_pages = set(range(lo, hi + 1)) | grid_pages
            all_hits, gaps = scan_volume(vol, parish, span, (win_lo, win_hi), idx, ocr_pages)
            strong = [h for h in all_hits if h['verdict'] == 'STRONG' and h.get('in_window_1667_1712')]
            # ---- P3 no-miss: in-window STRONG outside the band -> whole-volume re-OCR ----
            if not vp['fallback']:
                out = any(h['page'] < lo or h['page'] > hi for h in strong)
                if out:
                    vp['band'] = [1, n]; vp['fallback'] = True
                    vp['phase'] = 'band'
                    save_state(state)
                    print(f'  {vol}: out-of-band in-window STRONG -> whole-volume fallback', flush=True)
                    continue
            vp['phase'] = 'done'; vp['complete'] = True
            vp['n_hits'] = len(all_hits); vp['n_strong'] = len(strong)
            vp['n_near'] = len([h for h in all_hits if h['verdict'] == 'NEAR' and h.get('in_window_1667_1712')])
            vp['n_gap'] = len(gaps)
            # persist hits
            allh = json.load(open(HITS)) if os.path.exists(HITS) else []
            allh.extend(all_hits)
            for g in gaps:
                g['volume'] = vol; g['parish'] = parish
                allh.append(g)
            json.dump(allh, open(HITS, 'w'), indent=1, ensure_ascii=False)
            ocr_done = ocr_count(vol)
            ocr_total = len(ocr_pages) * 2
            status_finish(vol, parish, span, (win_lo, win_hi), vp, all_hits, gaps, ocr_done, ocr_total, vp['band'])
            save_state(state)
            print(f'  {vol} [{parish}]: DONE hits={len(all_hits)} strong_inwin={len(strong)} '
                  f'near={vp["n_near"]} gaps={len(gaps)} ocr={ocr_done}/{ocr_total}', flush=True)

    n_complete = sum(1 for v in state['vols'].values() if v.get('complete'))
    all_complete = (n_complete == N_VOLS) and all('complete' in state['vols'].get(v, {}) for v, *_ in VOLS)
    state['phase'] = 'done' if all_complete else 'incomplete'
    state['done'] = all_complete
    state['elapsed_s'] = round(time.time() - t0, 1)
    save_state(state)
    if all_complete:
        print(f'PHASE 5 ALL {N_VOLS} VOLUMES DONE', flush=True)
    else:
        print(f'PHASE 5 INCOMPLETE: {n_complete}/{N_VOLS} complete — NOT marking done (resumable)', flush=True)

def main():
    t0 = time.time()
    write_pid()
    try:
        _main_inner(t0)
    finally:
        clear_pid()

if __name__ == '__main__':
    main()
