#!/usr/bin/env python3
"""SLOT-AWARE (token-stream) fuzzy scan of the St-Andries REGISTER window
(1667-1712) for the birth of Frederic Zorokens/Zorrokens.

STRUCTURE (assessed from real 6245 OCR -- see structure_assessment.md):
  The register is a CONTINUOUS TOKEN STREAM, not line-structured. A line wraps
  arbitrarily, and the "Infans" marker sits MID-LINE, not line-leading:

    <father_first> <father_name> <mother_first> <mother_name>
        Intans / Infans / Intaus ...      <- INFANS marker (variable, ~8 OCR forms)
        <child_first> [<child_second>]
        suse / susc ... <godfather> <godmother> ...
        Parentes / Parentos / Pareutes ...  <- entry CLOSER (variable)

  - FATHER ZONE  = all name tokens from the previous CLOSER (or leaf start)
                   up to the INFANS marker. Variable length (compound
                   surnames: van X, de X, ...).
  - CHILD ZONE   = first 1-3 name tokens AFTER the INFANS marker.
  - GODPARENT ZONE = tokens after the child zone up to the next CLOSER.

MATCH RULES (positional gates on the token stream, fuzzy matcher validated on
the Johannes re-scan):
  STRONG   : FATHER ZONE has a Zorok* token  AND  CHILD ZONE has a Frederic*
             token.
  NEAR     : FATHER ZONE has Zorok*  AND  Frederic* appears in GODPARENT ZONE
             (or beyond) -- crop-verify (real child name after garbled OCR, or
             a godfather named Frederic; position alone can't fully decide).
  FATHER   : FATHER ZONE has Zorok*  but no Frederic anywhere in the entry
             (sibling under a Zorokens father; corroboration/context).
  EXCLUDED : FATHER ZONE token is in the distinct-lineage set (Zoron/Zooren/
             van Zoron/Zorone) -- documented near-miss, never a candidate.

B-initial: father-zone Zorok* token starting with 'B' (e.g. Borrokens) ->
DOUBTFUL flag, crop-verify (D->B misread of Zorokens is plausible).
"""
import json, os, re, glob

VOL_DIR = "/workspace/agatha/cache/volumes"
OUT = "/workspace/agatha/runs/frederic_zorokens/frederic_scan.json"

CORPUS = [
    ('6244', 'St-Andries', 'bapt REGISTER', '1671-1685', 1, 186),
    ('6243', 'St-Andries', 'bapt REGISTER', '1660-1671 (1667-1671 in window)', 1, 184),
    ('6245', 'St-Andries', 'bapt REGISTER', '1685-1706', 1, 233),
    ('6246', 'St-Andries', 'bapt REGISTER', '1706-1727', 1, 100),
]
WINDOW = (1667, 1712)

# --- exact validated matcher (verbatim from fuzzy_zorrokens.py) ---
FULL  = ("zorokens", "zorrokens")
STEMS = ("zorok", "zorrok")
FULL_TH = 3
STEM_TH = 1

FRED = ("frederic", "friederic", "frederix", "frideric", "phrederic",
        "frederick", "frederik", "fredericius", "fridericus")
FRED_TH = 3
FRED_STEM = ("freder", "frider", "phreder")

EXCLUDED_LINEAGE = {"zoron", "zooren", "vandonren", "zorone", "zorons"}

YEAR_RE = re.compile(r'\b1[67][0-9][0-9]\b')

# INFANS marker: forms observed in real 6245 OCR. Token-leading case-insensitive.
# 351 infans, 133 intans, 61 infaus, 28 intaus, 11 inhans, 5 ingans, 5 incans,
# 4 inpans, 3 infaur, 3 infant, 2 infand, ... all share: starts with "in", then
# a vowel/blend, then "a", then "n", then a tail. Robust pattern:
INFANS_RE = re.compile(r'^in[f]?[a-z]?n[a-z]{0,4}$', re.I)
# Also capture the "infans"-family by explicit high-frequency forms as a floor.
INFANS_EXACT = {
    'infans', 'intans', 'infaus', 'intaus', 'inhans', 'ingans', 'incans',
    'inpans', 'infaur', 'infant', 'infand', 'intorras', 'intauds', 'intaub',
    'intant', 'intano', 'intand', 'insfans', 'insdans', 'inhaus', 'inhan',
    'ingaas', 'infous', 'infaux', 'infaub', 'infaris', 'infais', 'infant',
    'intas', 'intaus', 'infans:', 'intans:',
}
# Parentes/Parentos/Pareutes/Parontes -> closer. Variable.
PARENT_RE = re.compile(r'^par[aeo]u?nt[eo]$|^par[aeo]u?nt[eo]\.$', re.I)
PARENT_EXACT = {'parentes', 'parentos', 'pareutes', 'parontes', 'parentus',
                'parente', 'paronts', 'pareutis', 'parontis'}

def is_infans(t):
    tl = t.lower().strip('.:,;')
    if tl in INFANS_EXACT: return True
    return bool(INFANS_RE.match(tl)) and tl.startswith('in') and 'n' in tl[2:]

def is_parent(t):
    tl = t.lower().strip('.:,;')
    if tl in PARENT_EXACT: return True
    return bool(PARENT_RE.match(tl))

def lev(a, b):
    a = a.lower(); b = b.lower()
    if a == b: return 0
    la, lb = len(a), len(b)
    if la < 1 or lb < 1: return max(la, lb)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]

def clean(tok):
    t = re.sub(r'[^a-zA-Z]', '', tok).lower()
    for pre in ('vd', 'van', 'de', 'den', 'opden'):
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
                w = t[i:i + len(s)]
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

# Token regex: a name token is >=2 letters (allowing internal apostrophes/hyphens).
TOK_RE = re.compile(r"[A-Za-z][A-Za-z'\-\.]{1,}")

def tokenize_leaf(ocr):
    """Flatten a leaf's OCR text into an ordered token stream with (line, col).
    Returns list of (tok, line_idx, pos_in_line)."""
    txt = open(ocr, errors='ignore').read()
    lines = txt.split('\n')
    stream = []
    for li, line in enumerate(lines):
        for m in TOK_RE.finditer(line):
            stream.append((m.group(0), li, m.start()))
    return stream, lines

def segment_entries(stream, lines):
    """Segment the token stream into entries. Each entry is
    {'father': [toks], 'child': [toks], 'godp': [toks], 'infans_tok': str,
     'line': int, 'span': (tok_idx_start, tok_idx_end)}
    An entry begins at an INFANS marker and ends at the next PARENT closer or
    the next INFANS marker (whichever comes first). Tokens BEFORE the first
    INFANS marker (or after a CLOSER, before the next marker) belong to the
    NEXT entry's father zone (they are the 4 parent names).

    We do this in one pass: keep a rolling 'father_acc' buffer. On INFANS:
    commit the entry with father_acc as the father zone, reset father_acc.
    On PARENT: also clear father_acc (it was the closer line + any noise).
    Everything else appends to the appropriate zone of the open entry, or to
    father_acc if no entry is open.
    """
    entries = []
    father_acc = []
    cur = None  # open entry dict
    for ti, (tok, li, pos) in enumerate(stream):
        if is_infans(tok):
            # Open a new entry: father zone = father_acc (tokens since last closer)
            cur = {
                'father': list(father_acc),
                'child': [],
                'godp': [],
                'infans_tok': tok,
                'line': li,
                'span': (ti, None),
                'in_child': True,
                'child_count': 0,
            }
            entries.append(cur)
            father_acc = []
            continue
        if is_parent(tok):
            # Closer: ends the current entry. Any tokens after it (until next
            # marker) start the next father zone.
            if cur is not None:
                cur['span'] = (cur['span'][0], ti)
                cur = None
            father_acc = []
            continue
        # Regular name token
        if cur is None:
            father_acc.append(tok)
        else:
            if cur['in_child'] and cur['child_count'] < 3:
                cur['child'].append(tok)
                cur['child_count'] += 1
                if cur['child_count'] >= 3:
                    cur['in_child'] = False
            else:
                cur['godp'].append(tok)
    # Trailing open entry
    if cur is not None:
        cur['span'] = (cur['span'][0], len(stream) - 1)
    return entries

# --- CHILD-FIRST (filius/filia) structure ---
# St-Andries 6246 (and some 6245 pages) lay the entry out with the child NAME
# BEFORE the filia/filius marker and the father+mother AFTER it:
#   ... <date> <child_christian_name> filia/filius [legitimus|legitima|spurius|
#   naturalis] <father_first> <father_name> et <mother_first> <mother_name> ...
#   [susc|suscept] <godparents>
# Evidence (2026-09-17, real 6246 OCR): 2359 filia/filius-family tokens vs 8
# infans in 6246, vs 25 filia vs 2181 infans in 6245. Per-page detection below
# handles a cleric changing layout MID-VOLUME.
FILIA_RE = re.compile(r'^fil[iy][a-z]{1,5}$', re.I)
FILIA_EXACT = {'filia', 'filius', 'filias', 'filins', 'filiis', 'filiut',
               'filiuis', 'filint', 'filiub', 'filinis', 'filicis', 'filiud',
               'filius:', 'filia:', 'filiu', 'filiud', 'filiud'}

def is_filialia(tok):
    tl = tok.lower().strip('.:,;')
    return tl in FILIA_EXACT or bool(FILIA_RE.match(tl))

def detect_structure(stream):
    """Per-page structure: 'child-first' if the page uses filia/filius markers
    (child before marker), else 'child-after' (6245 default, child after an
    Infans marker). Robust to a mid-volume layout change."""
    n_filia = sum(1 for t, _, _ in stream if is_filialia(t))
    n_infans = sum(1 for t, _, _ in stream if is_infans(t))
    if n_filia >= 3 and n_filia > n_infans:
        return 'child-first'
    return 'child-after'

def segment_childfirst(stream, lines):
    """Segment a child-first (filia/filius) leaf. Each filia/filius marker opens
    an entry: child = name tokens just BEFORE the marker; father/mother = the
    tokens after it; godparents = tokens after the first susc/suscept/cept
    closer in the father zone. Returns the same entry schema as
    segment_entries() so scan_one() handles both structures identically."""
    n = len(stream)
    midx = [i for i, (t, _, _) in enumerate(stream) if is_filialia(t)]
    entries = []
    for k, i in enumerate(midx):
        end = midx[k + 1] if k + 1 < len(midx) else min(n, i + 18)
        after = stream[i + 1:end]
        father = [t for t, _, _ in after][:10]
        start_prev = (midx[k - 1] + 1) if k > 0 else 0
        before = stream[max(start_prev, i - 5):i]
        child = [t for t, _, _ in before]
        godp = []
        for j, (t, _, _) in enumerate(after):
            if re.match(r'^(susc|suscep|suscp|cept)', t.lower()):
                godp = [x for x, _, _ in after[j + 1:]]
                break
        entries.append({
            'father': father, 'child': child, 'godp': godp[:12],
            'infans_tok': stream[i][0], 'line': stream[i][1],
            'span': (i, end), 'childfirst': True,
        })
    return entries


# --- child-zone cutoff: susc/accept = godparent boundary, NOT part of child name ---
_SUS_RE = re.compile(r'^(susc|susie|suscept|suscipt|susept|suse|sus|accept|accepta|accepto|sisc|scpt|fult|fulc|suhc|suht|susap|susep|susrept|susaept|sisceet|siceet|suseptor|susceptor|suscio|sucept|susceptores|susceptora|suseptoras|fulept|fuscept|huscept|husc)', re.I)
def cutoff_child(toks):
    """Truncate the child-zone token list at the first godparent-boundary token
    (susc(ept)/accept and its OCR-mangled forms). The godparents FOLLOW the
    boundary; the child name is only the tokens before it."""
    out = []
    for t in toks:
        tt = t.strip().strip('.,;:')
        if not tt:
            continue
        if _SUS_RE.match(tt):
            break
        out.append(t)
    return out

def scan_one(ocr, vol, parish, title, drange, lo, hi, idx):
    if os.path.getsize(ocr) <= 0: return []
    base = os.path.basename(ocr)[:-len('.ocr.txt')]
    m = re.match(r'^(\d+)', base)
    page = int(m.group(1)) if m else 0
    if not (lo <= page <= hi): return []
    iiif = ''
    if idx and 0 < page <= len(idx):
        iiif = idx[page - 1].get('full_res_url', '')
    leaf = base

    stream, lines = tokenize_leaf(ocr)
    structure = detect_structure(stream)
    if structure == 'child-first':
        entries = segment_childfirst(stream, lines)
    else:
        entries = segment_entries(stream, lines)

    hits = []
    for e in entries:
        ft, ct, gt = e['father'], cutoff_child(e['child']), e['godp']
        if not ft: continue

        # Father-zone Zorok* (best score)
        fd = [(surname_score(t), t) for t in ft]
        fd = [(s, t) for s, t in fd if s]
        if not fd: continue
        best = min(fd, key=lambda x: x[0][0])
        ddist, dkind, dref, dtok = best[0][0], best[0][1], best[0][2], best[1]
        binit = dtok[0].upper() == 'B'
        excl = clean(dtok) in EXCLUDED_LINEAGE

        # Child-zone Frederic
        cf = [(firstname_score(t), t) for t in ct]
        cf = [(s, t) for s, t in cf if s]
        fred_child = min(cf, key=lambda x: x[0][0])[1] if cf else None
        fred_child_d = min(cf, key=lambda x: x[0][0])[0][0] if cf else None

        # Godparent-zone Frederic
        gf = [(firstname_score(t), t) for t in gt]
        gf = [(s, t) for s, t in gf if s]
        fred_godp = min(gf, key=lambda x: x[0][0])[1] if gf else None
        fred_godp_d = min(gf, key=lambda x: x[0][0])[0][0] if gf else None

        if fred_child:
            verdict = 'STRONG'; fred_tok = fred_child; fred_d = fred_child_d
        elif fred_godp:
            verdict = 'NEAR';   fred_tok = fred_godp;   fred_d = fred_godp_d
        else:
            verdict = 'FATHER'; fred_tok = None;        fred_d = None

        # Year anchoring: the line of the INFANS marker +/- 6 lines
        ml = e['line']
        ywin = '\n'.join(lines[max(0, ml - 6):min(len(lines), ml + 8)])
        years = [int(y) for y in YEAR_RE.findall(ywin)]
        in_window = any(WINDOW[0] <= y <= WINDOW[1] for y in years) if years else True

        cstart = max(0, ml - 4)
        cend = min(len(lines), ml + 6)
        ctx = ' || '.join(l for l in lines[cstart:cend] if l.strip())

        hits.append({
            'volume': vol, 'parish': parish, 'title': title, 'date_range': drange,
            'page': page, 'leaf': leaf, 'infans_line': ml,
            'structure': structure,
            'verdict': verdict,
            'father_tokens': ft,
            'father_zorok_tok': dtok, 'father_zorok_edit': ddist,
            'father_zorok_kind': dkind, 'father_zorok_ref': dref,
            'b_initial': binit, 'excluded_lineage': excl,
            'child_zone_tokens': ct, 'godp_zone_tokens': gt[:12],
            'fred_child_tok': fred_child, 'fred_child_edit': fred_child_d,
            'fred_godp_tok': fred_godp, 'fred_godp_edit': fred_godp_d,
            'infans_marker_tok': e['infans_tok'],
            'years_near': years, 'in_window_1667_1712': in_window,
            'context': ctx[:600],
            'iiif_url': iiif,
            'ocr_file': f'cache/volumes/{vol}/pages/{base}.ocr.txt',
            'image': f'cache/volumes/{vol}/pages/{base}.jpg',
        })
    return hits

# --- PASS 2: structure-agnostic line co-occurrence (the old fuzzy net) ---
# The slot parser depends on recognizing an "Infans" marker to open an entry.
# If a page's OCR garbles the marker into an unrecognized form, the entry is
# never opened and the Zorok*+Frederic pairing is silently skipped. This pass
# has NO slot assumption: any Zorok* token and any Frederic* token co-occurring
# within a +/-2-line window (one leaf is ~2-3 entries, so +/-2 lines is the
# entry span) is a potential hit the slot parser may have missed.
def line_pass(ocr, vol, parish, title, drange, lo, hi, idx):
    if os.path.getsize(ocr) <= 0: return []
    base = os.path.basename(ocr)[:-len('.ocr.txt')]
    m = re.match(r'^(\d+)', base)
    page = int(m.group(1)) if m else 0
    if not (lo <= page <= hi): return []
    iiif = ''
    if idx and 0 < page <= len(idx):
        iiif = idx[page - 1].get('full_res_url', '')
    lines = open(ocr, errors='ignore').read().split('\n')
    toks = [re.findall(TOK_RE, ln) for ln in lines]
    hits = []
    n = len(lines)
    for i in range(n):
        dtok = dtokd = dkind = ftok = ftd = None
        for t in toks[i]:
            if dtok is None:
                s = surname_score(t)
                if s and clean(t) not in EXCLUDED_LINEAGE:
                    dtok, dtokd, dkind = t, s[0], s[1]
        for j in range(max(0, i - 2), min(n, i + 3)):
            for t in toks[j]:
                if ftok is None:
                    s = firstname_score(t)
                    if s:
                        ftok, ftd = t, s[0]
        if dtok and ftok:
            ywin = '\n'.join(lines[max(0, i - 6):min(n, i + 8)])
            years = [int(y) for y in YEAR_RE.findall(ywin)]
            in_window = any(WINDOW[0] <= y <= WINDOW[1] for y in years) if years else True
            cstart = max(0, i - 4); cend = min(n, i + 6)
            ctx = ' || '.join(l for l in lines[cstart:cend] if l.strip())
            hits.append({
                'volume': vol, 'parish': parish, 'title': title, 'date_range': drange,
                'page': page, 'leaf': base, 'line': i,
                'verdict': 'GAP',
                'line_zorok_tok': dtok, 'line_zorok_edit': dtokd,
                'line_zorok_kind': dkind,
                'line_fred_tok': ftok, 'line_fred_edit': ftd,
                'b_initial': dtok[0].upper() == 'B',
                'years_near': years, 'in_window_1667_1712': in_window,
                'context': ctx[:600],
                'iiif_url': iiif,
                'ocr_file': f'cache/volumes/{vol}/pages/{base}.ocr.txt',
                'image': f'cache/volumes/{vol}/pages/{base}.jpg',
            })
    return hits

def main(only_vol=None, out_path=None):
    if out_path is None:
        out_path = OUT
    all_hits = []
    seen = set()
    nfiles = 0
    line_hits = []
    for vol, parish, title, drange, lo, hi in CORPUS:
        if only_vol and vol != only_vol:
            continue
        idxp = f"{VOL_DIR}/{vol}/index.json"
        try: idx = json.load(open(idxp))
        except Exception: idx = []
        ocrs = sorted(glob.glob(f"{VOL_DIR}/{vol}/pages/*.ocr.txt"))
        for ocr in ocrs:
            nfiles += 1
            for h in scan_one(ocr, vol, parish, title, drange, lo, hi, idx):
                key = (vol, h['page'], h['infans_line'], h['leaf'])
                if key in seen: continue
                seen.add(key)
                all_hits.append(h)
            # PASS 2 net (runs on the same files; cheap — no OCR, no Kraken)
            line_hits.extend(line_pass(ocr, vol, parish, title, drange, lo, hi, idx))

    # A GAP is only interesting where the SLOT parser found NO Zorok* entry on
    # that (vol,page). On a page the slot parser already classified, the line
    # pass is just re-finding what the slot parser already decided.
    slot_covered = set((h['volume'], h['page']) for h in all_hits)
    gaps = []
    gseen = set()
    for g in line_hits:
        if (g['volume'], g['page']) in slot_covered:
            continue
        k = (g['volume'], g['page'], g['leaf'], g['line'])
        if k in gseen: continue
        gseen.add(k)
        gaps.append(g)
    gaps.sort(key=lambda g: (g['line_zorok_edit'], g['line_fred_edit'], g['volume'], g['page']))

    all_hits.sort(key=lambda h: (
        {'STRONG': 0, 'NEAR': 1, 'FATHER': 2}.get(h['verdict'], 9),
        h['father_zorok_edit'], h['volume'], h['page']))
    strong = [h for h in all_hits if h['verdict'] == 'STRONG']
    near   = [h for h in all_hits if h['verdict'] == 'NEAR']
    father = [h for h in all_hits if h['verdict'] == 'FATHER']
    excl   = [h for h in all_hits if h['excluded_lineage']]
    out = {
        'target': 'Frederic Zorokens/Zorrokens — baptism (birth), St Andries',
        'anchor': 'Johannes (2nd Petri/Petrus) Zorokens, 2 Feb 1722, St Andries; '
                 'father = Frederici/Fredericus Zorokens/Zorrokens (USER-CONFIRMED)',
        'window': '1667-1712',
        'method': 'TWO-PASS fuzzy scan. PASS 1 (authoritative): SLOT-AWARE '
                  'token-stream — leaf flattened to a token stream, segmented on '
                  'Infans markers (variable, ~8 OCR forms) and Parentes closers; '
                  'father zone = tokens before the marker, child zone = first 1-3 '
                  'tokens after. PASS 2 (safety net): structure-agnostic line '
                  'co-occurrence (old fuzzy net) — any Zorok* token + any '
                  'Frederic* token within +/-2 lines, run to catch the miss-class '
                  'where a garbled Infans marker prevents PASS 1 from opening the '
                  'entry. GAP = a PASS-2 hit on a (vol,page) PASS 1 found no '
                  'Zorok* entry on -> CROP-VERIFY (possible marker-garble miss). '
                  'Fuzzy matcher (full<=3, stem<=1) validated on the Johannes '
                  're-scan. Structure assessed from real 6245 OCR '
                  '(structure_assessment.md).',
        'corpus': [{'vol': v, 'parish': p, 'type': t, 'span': s,
                    'pages': f'{lo}-{hi}'} for v, p, t, s, lo, hi in CORPUS],
        'n_ocr_files_scanned': nfiles,
        'n_entries': len(all_hits),
        'n_strong': len(strong),
        'n_near': len(near),
        'n_father_only': len(father),
        'n_excluded_lineage': len(excl),
        'n_gaps_line_pass': len(gaps),
        'hits': all_hits,
        'gaps': gaps,
    }
    json.dump(out, open(out_path, 'w'), indent=1, ensure_ascii=False)
    if only_vol:
        print(f"[{only_vol}] scanned {nfiles} OCR files (single-volume push)")
    else:
        print(f"[all] scanned {nfiles} OCR files across {len(CORPUS)} volumes")
    print(f"scanned {nfiles} OCR files; {len(all_hits)} Zorok* father-block entries (PASS 1 slot)")
    print(f"  STRONG (father Zorok* + child Frederic): {len(strong)}")
    print(f"  NEAR   (father Zorok* + Frederic in godparent zone): {len(near)}")
    print(f"  FATHER (father Zorok*, no Frederic in entry): {len(father)}")
    print(f"  EXCLUDED lineage (Zoron/Zooren/van Zoron): {len(excl)}")
    print(f"  GAP    (PASS-2 line hit on a page PASS 1 missed): {len(gaps)}  <- crop-verify")
    print("\n=== STRONG ===")
    for h in strong:
        print(f"[{h['volume']} p{h['page']}/{h['leaf']} L{h['infans_line']}] "
              f"zorok={h['father_zorok_tok']}(d={h['father_zorok_edit']},{h['father_zorok_kind']},binit={h['b_initial']}) "
              f"fred={h['fred_child_tok']}(d={h['fred_child_edit']}) yrs={h['years_near']}")
        print(f"    father: {h['father_tokens']}")
        print(f"    child : {h['child_zone_tokens']}")
        print(f"    ctx   : {h['context'][:300]}")
    print("\n=== NEAR (top 40) ===")
    for h in near[:40]:
        print(f"[{h['volume']} p{h['page']}/{h['leaf']} L{h['infans_line']}] "
              f"zorok={h['father_zorok_tok']}(d={h['father_zorok_edit']}) "
              f"fred_godp={h['fred_godp_tok']}(d={h['fred_godp_edit']}) yrs={h['years_near']}")
        print(f"    father: {h['father_tokens']}")
        print(f"    child : {h['child_zone_tokens']}")
        print(f"    ctx   : {h['context'][:260]}")
    print("\n=== GAP (PASS-2 safety net, crop-verify) ===")
    for h in gaps[:40]:
        print(f"[{h['volume']} p{h['page']}/{h['leaf']} L{h['line']}] "
              f"zorok={h['line_zorok_tok']}(d={h['line_zorok_edit']},{h['line_zorok_kind']}) "
              f"fred={h['line_fred_tok']}(d={h['line_fred_edit']}) yrs={h['years_near']}")
        print(f"    ctx : {h['context'][:300]}")

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--vol', default=None, help='scan a single volume only (per-volume push)')
    ap.add_argument('--out', default=None, help='output JSON path (default: canonical OUT)')
    a = ap.parse_args()
    main(only_vol=a.vol, out_path=a.out)
