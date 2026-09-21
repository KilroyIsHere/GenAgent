#!/usr/bin/env python3
"""PHASE 4 orchestrator — multi-parish fallback (Antwerp, index-first).

Trigger: St Andries 1667-1712 register sweep returned 0 STRONG / 0 NEAR
(Phase 3 crop-verified). Now sweep the other Antwerp parishes' baptism
INDEXES for a Frederic Zorokens/Zorrokens entry in the 1667-1712 window.

Standing rule (user 2026-09-17): structure is NEVER assumed (not even from
same-parish sibling volumes); it is assessed per-volume from its own OCR and
per-page, because layout can change mid-volume. A 0-hit on an unassessed page
is not a reliable no-hit. => candidate detection here is page-level and
structure-AGNOSTIC: every OCR'd index page is token-scanned for Zorok* /
Frederic* hits. Structure assessment only bounds the OCR band width; if the
band can't be confidently bracketed we fall back to the whole in-window span.

Per volume:
  P0 discover: coarse grid (stride 3) download+OCR -> per-page structure read
     (alphabetical A..Z vs year-block), leading-letter map, any-page hits.
  P1 band: OCR the estimated target band (alphabetical: D..F surname span;
     year-sorted: in-window year span; unknown: whole span), ±5 buffer.
  P2 scan: page-level fuzzy scan (validated matcher, Levenshtein<=3 on
     surname Zorokens/Zorrokens + first name Frederic) over every OCR'd page;
     every hit = candidate -> crop-verify (DOUBTFUL until crop agrees).
  P3 no-miss: if the P0/P1 band edges looked uncertain, or any Frederic*
     token appeared outside the band, extend/whole-volume OCR.

Resumable (cache-first: skips cached pages + OCR'd leaves). Single Kraken
batch at a time (ooms >3 jobs). State: p4_state.json (deterministic monitor
input).
"""
import os, re, sys, time, json, glob, subprocess

AG = '/workspace/agatha'
RUN = f'{AG}/runs/frederic_zorokens'
PAGE_DIR = f'{AG}/cache/volumes'
OCR_BATCH = f'{AG}/ocr_batch.sh'
STATE = f'{RUN}/p4_state.json'
HITS = f'{RUN}/p4_hits.json'
DISC_LOG = f'{RUN}/p4_discovery.log'
PROG = f'{RUN}/p4_progress.json'
sys.path.insert(0, AG)
import agatha_cache as ac

WINDOW = (1667, 1712)
STRIDE = 3          # discovery grid stride
BAND_BUF = 5        # buffer pages either side of estimated band
MAX_PAGE = 260      # sanity cap per volume (all NEW vols <= 251 pp)

# NEW index volumes (parish, span label). 6379/6089/454853/6160/6300/6260/6262/
# 6265 (DONE) are handled by a separate zero-OCR matcher re-run (p4_cached_idx.py).
VOLS = [
    ('6364', 'Christ. Gereform. (11)', '1660-1699'),
    ('6365', 'Christ. Gereform. (11)', '1672-1677'),
    ('6084', 'OLV-Zuid (15)',          '1658-1670'),
    ('6091', 'OLV-Zuid (15)',          '1670-1687'),
    ('6090', 'OLV-Zuid (15)',          '1688-1700'),
    ('6138', 'OLV-Noord (14)',         '1663-1675'),
    ('6137', 'OLV-Noord (14)',         '1676-1687'),
    ('6145', 'OLV-Noord (14)',         '1688-1704'),
    ('6144', 'OLV-Noord (14)',         '1705-1714'),
    ('6320', 'St-Laurentius (21)',     '1659-1667'),
    ('6322', 'St-Laurentius (21)',     '1667-1687'),
    ('6324', 'St-Laurentius (21)',     '1688-1704'),
    ('6186', 'St-Walburga (24)',       '1636-1677'),
    ('6187', 'St-Walburga (24)',       '1678-1696'),
    ('6188', 'St-Walburga (24)',       '1696-1712'),
    ('6263', 'St-Joris (20)',          '1651-1675'),
    ('6257', 'St-Joris (20)',          '1650-1699'),
    ('6259', 'St-Joris (20)',          '1650-1699'),
    ('6264', 'St-Joris (20)',          '1676-1700'),
    ('6222', 'St-Andries (17)',        '1628-1671 (sliver 1667-1671)'),
]

# --- validated fuzzy matcher (verbatim from scan_frederic.py / fuzzy_zorrokens.py) ---
FULL  = ("zorokens", "zorrokens")
STEMS = ("zorok", "zorrok")
FULL_TH = 3; STEM_TH = 1
FRED = ("frederic","friederic","frederix","frideric","phrederic","frederick",
        "frederik","fredericius","fridericus","federic")
FRED_TH = 3
FRED_STEM = ("freder","frider","phreder","feder")
EXCLUDED_LINEAGE = {"zoron","zooren","vandonren","zorone","zorons"}
TOK_RE = re.compile(r"[A-Za-z][A-Za-z'\-\.]{1,}")
YEAR_RE = re.compile(r'\b1[67][0-9][0-9]\b')

def lev(a, b):
    a = a.lower(); b = b.lower()
    if a == b: return 0
    la, lb = len(a), len(b)
    if la < 1 or lb < 1: return max(la, lb)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i-1] == b[j-1] else 1
            cur[j] = min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + cost)
        prev = cur
    return prev[lb]

def clean(tok):
    t = re.sub(r'[^a-zA-Z]', '', tok).lower()
    for pre in ('vd','van','de','den','opden'):
        if t.startswith(pre) and len(t) > len(pre) + 2:
            t = t[len(pre):]
    return t

def surname_score(tok):
    t = clean(tok)
    if len(t) < 5: return None
    best = None
    for ref in FULL:
        d = lev(t, ref)
        if d <= FULL_TH and (best is None or d < best[0]):
            best = (d, 'full', ref)
    if best is None or best[0] > 1:
        for s in STEMS:
            for i in range(0, max(1, len(t) - len(s) + 1)):
                w = t[i:i+len(s)]
                d = lev(w, s)
                if d <= STEM_TH and (best is None or d < best[0]):
                    best = (d, 'stem-contains', s)
    return best

def firstname_score(tok):
    t = clean(tok)
    if len(t) < 5: return None
    best = None
    for ref in FRED:
        d = lev(t, ref)
        if d <= FRED_TH and (best is None or d < best[0]):
            best = (d, 'full', ref)
    if best is None or best[0] > 1:
        for s in FRED_STEM:
            if s in t:
                cand = (1, 'stem-contains', s)
                best = cand if best is None else (best if best[0] < cand[0] else cand)
    return best

# --- per-page structure read (index: alphabetical vs year-block) ---
LETTER_RE = re.compile(r'\b([A-Z])\b')
def page_structure(ocr_path):
    """Read ONE page's structure from its own OCR. Returns
    {letters:[...], years:[...], lead_letter: str|None, kind: 'alpha'|'year'|'unknown'}
    - 'alpha'   : a run of distinct A-Z letters present (surname-column headers)
    - 'year'    : >=2 distinct 16xx/17xx years (year-blocked index)
    - 'unknown' : neither clearly -> caller treats as unassessed (no-miss fallback)
    """
    if not os.path.exists(ocr_path): return None
    txt = open(ocr_path, errors='ignore').read()
    letters = sorted(set(m.group(1) for m in LETTER_RE.finditer(txt)
                         if len(txt[max(0,m.start()-1):m.start()]) == 0 or not txt[m.start()-1].isalpha()))
    # require the letter to stand alone (word boundary) to be a header letter
    letters = sorted(set(re.findall(r'(?<![A-Za-z])([A-Z])(?![a-zA-Z])', txt)))
    years = sorted(set(int(y) for y in YEAR_RE.findall(txt)))
    lead = letters[0] if letters else None
    n_a = len(set(letters) & set('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
    if n_a >= 2 and n_a >= max(2, len(years)):
        kind = 'alpha'
    elif len(years) >= 2 and max(years) - min(years) < 60:
        kind = 'year'
    else:
        kind = 'unknown'
    return {'letters': letters, 'years': years, 'lead_letter': lead, 'kind': kind}

# --- page-level fuzzy scan (structure-agnostic) ---
def scan_page(ocr_path, vol, parish, idx, page):
    """Scan ONE index page for Zorok* / Frederic* tokens. Returns list of
    candidate dicts. EXCLUDED_LINEAGE tokens are recorded but pre-classified
    (distinct family). Structure-agnostic: does NOT rely on the page's layout."""
    if not os.path.exists(ocr_path) or os.path.getsize(ocr_path) <= 0:
        return []
    txt = open(ocr_path, errors='ignore').read()
    toks = TOK_RE.findall(txt)
    cand = []
    fred_toks, zorok_toks, excl_toks = [], [], []
    for t in toks:
        fs = firstname_score(t)
        ss = surname_score(t)
        if fs:
            cand.append({'kind': 'first', 'tok': t, 'score': fs, 'dist': fs[0], 'how': fs[1], 'ref': fs[2]})
            fred_toks.append(t)
        if ss:
            c = clean(t)
            if c in EXCLUDED_LINEAGE:
                excl_toks.append(t); continue
            cand.append({'kind': 'surname', 'tok': t, 'score': ss, 'dist': ss[0], 'how': ss[1], 'ref': ss[2]})
            zorok_toks.append(t)
    # A candidate PAGE = any zorok token, or any fred token (first-name-only
    # is weak; a zorok-surname + fred co-occurring on the page is STRONG-ish).
    strong_page = bool(zorok_toks) and bool(fred_toks)
    if not cand and not excl_toks:
        return []
    iiif = ''
    if idx and 0 < page <= len(idx):
        iiif = idx[page-1].get('full_res_url', '') if isinstance(idx, list) else idx.get(page,{}).get('full_res_url','')
    return [{
        'volume': vol, 'parish': parish, 'page': page,
        'strong_page': strong_page,
        'fred_tokens': fred_toks, 'zorok_tokens': zorok_toks,
        'excluded_tokens': excl_toks,
        'cand': cand, 'iiif': iiif,
        'years': sorted(set(int(y) for y in YEAR_RE.findall(txt))),
        'ocr_file': ocr_path,
        'image': ocr_path.replace('.ocr.txt', '.jpg'),
    }]

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


_PIL_OK = False
try:
    import PIL.Image as _PILImage
    _PIL_OK = True
except Exception:
    _PIL_OK = False
    _PILImage = None

def leaf_has_ink(jpg):
    """True if the leaf jpg carries real ink (i.e. NOT a genuinely-blank page).
    A 0-byte OCR on an ink-bearing leaf is a FAILURE (retry); a 0-byte OCR on a
    genuinely-blank leaf is TERMINAL (Kraken returns empty for blank/title pages).
    Resizes to a thumbnail and counts dark (<140) pixels. Missing/tiny jpg => False."""
    if not _PIL_OK:
        return False
    try:
        im = _PILImage.open(jpg).convert('L')
        if im.size[0] < 40 or im.size[1] < 40:
            return False
        im = im.resize((120, 120))
        px = list(im.getdata())
        dark = sum(1 for v in px if v < 140) / len(px)
        return dark > 0.05
    except Exception:
        return False

def ocr_vol(vol, pages):
    """Run ocr_batch.sh for the pages that still need OCR (cache-first)."""
    todo = []
    for p in pages:
        for s in ('L', 'R'):
            o = f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt'
            if not (os.path.exists(o) and os.path.getsize(o) > 0):
                todo.append(p); break
    # Record terminal 0-byte (dark) leaves across ALL covered pages (not just the
    # fresh `todo`) so the reporting step can vision-verify the in-band ones even
    # on a fully-cached re-entry (where todo is empty and the batch is skipped).
    dark = []
    for p in set(pages):
        for s2 in ('L', 'R'):
            o = f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s2}.ocr.txt'
            if os.path.exists(o) and os.path.getsize(o) == 0:
                dark.append(f'{p:03d}_{s2}')
    if dark:
        try:
            _st = load_state()
            _vp = _st['vols'].setdefault(vol, {})
            _prev = set(_vp.get('dark_leaves', []))
            _vp['dark_leaves'] = sorted(_prev | set(dark))
            save_state(_st)
        except Exception:
            pass
    if not todo:
        return True
    r = subprocess.run(['bash', OCR_BATCH, vol] + [str(p) for p in sorted(set(todo))],
                       capture_output=True, text=True, timeout=3600)
    # A leaf is DONE when its .ocr.txt EXISTS (any size). Empty (0-byte) after a
    # completed batch on a healthy service = Kraken read nothing = a terminal
    # dark/blank scan (NOT a transient failure — verified by retry). A MISSING
    # .ocr.txt = the batch did not get to the leaf (curl/split error/timeout)
    # = a real failure -> batch incomplete -> retry. 0-byte leaves are recorded
    # on the volume state (dark_leaves) by the block above the batch.
    def leaf_done(p, s):
        o = f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt'
        if not os.path.exists(o):
            return False
        if os.path.getsize(o) == 0:
            dark.append(f'{p:03d}_{s}')
        return True
    ok = 'ALL OK' in r.stdout or all(
        leaf_done(p, s)
        for p in todo for s in ('L', 'R') if os.path.exists(f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.jpg'))
    return ok

def vol_n_pages(vol):
    p = f'{PAGE_DIR}/{vol}/index.json'
    if not os.path.exists(p): return MAX_PAGE
    ix = json.load(open(p))
    return len(ix.get('pages', [])) if isinstance(ix, dict) else len(ix)

def load_idx(vol):
    p = f'{PAGE_DIR}/{vol}/index.json'
    if not os.path.exists(p): return []
    return json.load(open(p))

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
    """absolute cache path -> workspace-relative for the LINK base."""
    if p.startswith('/workspace/agatha/'):
        return p.split('/workspace/agatha/', 1)[1]
    return p

def _evidence(h):
    img = _rel(h.get('image', '')); ocr = _rel(h.get('ocr_file', ''))
    s = f"[image]({LINK}{img}) · [OCR]({LINK}{ocr})"
    if h.get('iiif'):
        s += f" · [full-res]({h['iiif']})"
    return s

def status_start(vol, parish, span, grid_leaves):
    _append(f"\n---\n\n## {vol} — {parish} baptism index ({span}) — START — {_ts()}\n\n")
    _append(f"- pages: full volume (in-window slice {span})\n")
    _append(f"- discovery grid queued: {grid_leaves} leaves (stride {STRIDE})\n")
    _append("- structure: **assessed from this volume's own OCR per-page — never assumed** "
            "(can change mid-volume); OCR band chosen from that\n")
    _append("- status: in progress…\n\n")

def _best_zorok(r):
    for c in r.get('cand', []):
        if c.get('kind') == 'surname' and c.get('ref'):
            return c.get('dist'), c.get('ref')
    return None, None

def status_finish(vol, parish, span, vp, hits, ocr_done, ocr_total):
    kind = vp.get('structure_kind', '?')
    band = vp.get('band')
    band_s = f"{band[0]}–{band[1]}" if band else '?'
    fb = ' · **whole-volume fallback (band not confidently bracketed)**' if vp.get('fallback') else ''
    bypage = {}
    for h in hits:
        pg = h.get('page')
        d = bypage.setdefault(pg, {'page': pg, 'leaf': h.get('leaf', '?'),
                                   'strong': False, 'zorok': set(), 'fred': set(),
                                   'excl': set(), 'years': set(), 'cand': [],
                                   'iiif': h.get('iiif', ''), 'image': h.get('image', ''),
                                   'ocr_file': h.get('ocr_file', '')})
        d['strong'] = d['strong'] or h.get('strong_page', False)
        d['zorok'].update(h.get('zorok_tokens', []))
        d['fred'].update(h.get('fred_tokens', []))
        d['excl'].update(h.get('excluded_tokens', []))
        d['years'].update(h.get('years', []))
        d['cand'].extend(h.get('cand', []))
        if not d['leaf'] or d['leaf'] == '?':
            d['leaf'] = h.get('leaf', '?')
    rows = sorted(bypage.values(), key=lambda r: (not r['strong'], r['page']))
    n_strong = sum(1 for r in rows if r['strong'])
    n_idx = sum(1 for r in rows if (not r['strong'] and (r['zorok'] or r['fred'])))
    n_excl = sum(1 for r in rows if r['excl'] and not r['zorok'] and not r['fred'])

    _append(f"\n---\n\n## {vol} — {parish} baptism index ({span}) — FINISH — {_ts()}\n\n")
    _append(f"- pages {band_s} of full volume · span {span} · **structure={kind}{fb}**\n")
    _append(f"- OCR: {ocr_done}/{ocr_total} leaves in band\n")
    _append(f"- candidates: **{n_strong} STRONG-page (Zorok* + Frederic* co-occur, crop-verify)** · "
            f"{n_idx} index-Zorok/Frederic (corroboration) · {n_excl} excluded-lineage\n")
    if not rows:
        _append(f"\n**0 candidate pages** in the OCR'd band — no Zorok* / Frederic* token. "
                f"Structure read as {kind} from this volume's own OCR; band {band_s} covers the "
                f"target.{'' if not vp.get('fallback') else ' (whole-volume = no-miss)'}\n\n")
        return
    _append(f"\n#### {vol} — all Zorok* / Frederic* index candidates (full detail)\n\n")
    _append("| # | Page | Leaf | Tier | Zorok* token (edit) | Frederic* token | Excluded | Yr | Evidence |\n")
    _append("|---|------|------|------|--------------------|------------------|----------|----|----------|\n")
    for i, r in enumerate(rows, 1):
        if r['strong']:
            tier = '**STRONG-page**'
        elif r['excl'] and not r['zorok']:
            tier = 'EXCLUDED'
        else:
            tier = 'INDEX-ZOROK'
        de, ref = _best_zorok(r)
        dtok = f"`{sorted(r['zorok'])[0]}` (d{de})" if r['zorok'] else '—'
        ftok = ', '.join(sorted(r['fred'])) or '—'
        excl = ', '.join(sorted(r['excl'])) or '—'
        yr = '/'.join(str(y) for y in sorted(r['years'])) or '—'
        _append(f"| {i} | {r['page']} | {r['leaf']} | {tier} | {dtok} | {ftok} | {excl} | {yr} | {_evidence(r)} |\n")
    _append(f"\n_Tier meaning (index): **STRONG-page** = a Zorok* surname AND a Frederic* first-name "
            f"token co-occur on the page → crop-verify (DOUBTFUL until the crop agrees). "
            f"**INDEX-ZOROK** = Zorok* surname entry only (family present, child name ≠ Frederic). "
            f"**EXCLUDED** = Zoron/Zooren lineage (distinct family). All rows are page-level and "
            f"structure-agnostic (layout can change mid-volume, so no layout was assumed)._ \n\n")

PIDFILE = f'{RUN}/p4_run.pid'
def write_pid():
    try:
        open(PIDFILE, 'w').write(str(os.getpid()))
    except Exception:
        pass
def clear_pid():
    try: os.unlink(PIDFILE)
    except Exception: pass

def main():
    t0 = time.time()
    write_pid()
    try:
      _main_inner(t0)
    finally:
        clear_pid()

def _main_inner(t0):
    state = load_state()
    if state.get('done'):
        print('PHASE 4 ALREADY DONE — nothing to do', flush=True)
        return
    idx_cache = {}
    for vol, parish, span in VOLS:
        vp = state['vols'].setdefault(vol, {'parish': parish, 'span': span,
                                             'phase': 'pending', 'structure': {},
                                             'band': None, 'ocr_pages': 0,
                                             'n_hits': 0, 'n_strong': 0, 'fallback': False})
        if vp.get('complete'):
            continue
        n = min(vol_n_pages(vol), MAX_PAGE)
        idx = idx_cache.get(vol)
        if idx is None:
            idx = load_idx(vol); idx_cache[vol] = idx
        # ---- P0 discovery (coarse grid) — re-enters on -failed (cache-first resume) ----
        if vp['phase'] in ('pending', 'discover', 'discover-failed'):
            grid = list(range(1, n + 1, STRIDE))
            if not vp.get('started'):
                status_start(vol, parish, span, len(grid) * 2)
                vp['started'] = True
            vp['phase'] = 'discover'
            save_state(state)
            # download grid
            for p in grid:
                if not download_page(vol, p):
                    vp['phase'] = 'discover-failed'; save_state(state); break
            if vp['phase'] == 'discover-failed':
                print(f'  {vol}: download fail on grid — leaving for retry', flush=True); continue
            # OCR grid (batch; resumable — ocr_batch skips existing)
            if not ocr_vol(vol, grid):
                vp['phase'] = 'discover-failed'; save_state(state)
                print(f'  {vol}: discovery OCR incomplete — will resume', flush=True); continue
            # per-page structure read
            struct = {}
            for p in grid:
                for s in ('L', 'R'):
                    op = f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt'
                    ps = page_structure(op)
                    if ps:
                        struct[f'{p}_{s}'] = ps
            vp['structure'] = {k: v for k, v in list(struct.items())[:40]}
            # estimate band from THIS volume's own structure
            alpha_letters = []
            for k, v in struct.items():
                if v['kind'] == 'alpha' and v['lead_letter']:
                    alpha_letters.append(v['lead_letter'])
            kinds = [v['kind'] for v in struct.values() if v['kind'] in ('alpha', 'year')]
            if kinds:
                dominant = max(set(kinds), key=kinds.count)
            else:
                dominant = 'unknown'
            vp['structure_kind'] = dominant
            if dominant == 'alpha' and alpha_letters:
                # alphabetical: band = pages whose lead-letter is in D..F (± buffer)
                letter_pages = {}
                for k, v in struct.items():
                    pg = int(k.split('_')[0])
                    if v['lead_letter']:
                        letter_pages.setdefault(v['lead_letter'], []).append(pg)
                band_pages = sorted(set(pg for L in 'DEFG' for pg in letter_pages.get(L, [])))
                if band_pages:
                    lo = max(1, min(band_pages) - BAND_BUF)
                    hi = min(n, max(band_pages) + BAND_BUF)
                else:
                    lo, hi = 1, n   # no D-F bracket found in grid -> whole volume
                vp['band'] = [lo, hi]; vp['fallback'] = not band_pages
            elif dominant == 'year':
                # year-blocked: band = in-window year span (approx pages by year density)
                vp['band'] = [1, n]   # conservative: whole volume for year-blocked
                vp['fallback'] = True
            else:
                vp['band'] = [1, n]; vp['fallback'] = True
            vp['phase'] = 'band'
            save_state(state)
            print(f'  {vol} [{parish}] {span}: structure={dominant} band={vp["band"]} fallback={vp["fallback"]}', flush=True)
        # ---- P1 band OCR + P2 scan — re-enters on band-failed (cache-first resume) ----
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
        # ---- P2 page-level scan (band + discovery grid = no-miss over all OCR'd pages) ----
        if vp['phase'] == 'scan':
            lo, hi = vp['band']
            pages_hit = []
            strong = 0
            grid_pages = {int(k.split('_')[0]) for k in (vp.get('structure') or {})}
            ocr_pages = set(range(lo, hi + 1)) | grid_pages
            for p in sorted(ocr_pages):
                for s in ('L', 'R'):
                    op = f'{PAGE_DIR}/{vol}/pages/{p:03d}_{s}.ocr.txt'
                    res = scan_page(op, vol, parish, idx, p)
                    if res:
                        for r in res:
                            r['leaf'] = f'{p:03d}_{s}'
                        pages_hit.append(res[0])
                        if res[0]['strong_page']:
                            strong += 1
            vp['n_hits'] = len(pages_hit)
            vp['n_strong'] = strong
            # ---- P3 no-miss: if a strong hit fell OUTSIDE the band, re-OCR whole volume ----
            if not vp['fallback']:
                out = 0
                for h in pages_hit:
                    if h['strong_page'] and (h['page'] < lo or h['page'] > hi):
                        out += 1
                        break
                if out:
                    vp['band'] = [1, n]; vp['fallback'] = True
                    vp['phase'] = 'band'  # re-OCR whole volume
                    save_state(state)
                    print(f'  {vol}: out-of-band strong hit -> whole-volume fallback', flush=True)
                    continue
            vp['phase'] = 'done'
            vp['complete'] = True
            # persist hits
            all_hits = json.load(open(HITS)) if os.path.exists(HITS) else []
            all_hits.extend(pages_hit)
            json.dump(all_hits, open(HITS, 'w'), indent=1)
            # per-volume FINISH block in STATUS.md (standing rule)
            ocr_done = ocr_count(vol)
            ocr_total = len(ocr_pages) * 2
            status_finish(vol, parish, span, vp, pages_hit, ocr_done, ocr_total)
            save_state(state)
            print(f'  {vol} [{parish}]: DONE hits={len(pages_hit)} strong={strong} '
                  f'ocr={ocr_done}/{ocr_total}', flush=True)
    n_complete = sum(1 for v in state['vols'].values() if v.get('complete'))
    all_complete = (n_complete == len(VOLS)) and all('complete' in state['vols'][vol] for vol, _, _ in VOLS)
    state['phase'] = 'done' if all_complete else 'incomplete'
    state['done'] = all_complete
    state['elapsed_s'] = round(time.time() - t0, 1)
    save_state(state)
    if all_complete:
        print(f'PHASE 4 ALL {len(VOLS)} VOLUMES DONE', flush=True)
    else:
        print(f'PHASE 4 INCOMPLETE: {n_complete}/{len(VOLS)} complete — NOT marking done '
              f'(resumable; relaunch to finish remaining)', flush=True)

if __name__ == '__main__':
    main()
