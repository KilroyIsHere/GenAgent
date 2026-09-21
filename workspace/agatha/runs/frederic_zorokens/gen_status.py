#!/usr/bin/env python3
"""Generate the single-file, per-volume STATUS report for the Frederic Zorokens birth search.
Runs in /workspace/agatha. Reads the two-pass scan JSON, writes a running status log
(one file) to the vault search folder. Every volume: START + END + results. Every Zorok*
match detailed with tier, evidence links. Appendable by future volume runs.
"""
import json, os, glob, html

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.join(HERE, 'frederic_scan.json')
WS = '/workspace/agatha'
LINKBASE = 'file:///D:/AI/workspace/agatha'   # vault lives on D:; /workspace == D:/AI/workspace
OUT = '/vault/genealogy/AI Searches/Birth of Frederic Zorokens (father of Johannes Petri 1722)/STATUS.md'

d = json.load(open(SCAN))
hits = d['hits']

def esc(s):
    return html.escape(str(s)) if s is not None else ''

# ---- count 6246 on-disk coverage + confirm it was scanned with wrong parser ----
l646 = [f for f in glob.glob(WS+'/cache/volumes/6246/pages/*.ocr.txt') if '_L' in f or '_R' in f]
s646 = [f for f in glob.glob(WS+'/cache/volumes/6246/pages/*.ocr.txt') if '_L' not in f and '_R' not in f]

def byvol(v):
    return [h for h in hits if h['volume'] == v]

def tier(h):
    ed = h.get('father_zorok_edit', 99)
    kind = h.get('father_zorok_kind','')
    if h.get('excluded_lineage'):
        return 'EXCLUDED'
    if ed <= 1:
        return 'REAL-ZOROK'
    if ed == 2:
        return 'POSSIBLE'
    return 'NOISE'

def links(h):
    img = h.get('image',''); ocr = h.get('ocr_file','')
    parts=[]
    if img:
        parts.append(f"[image]({LINKBASE}/{esc(img)})")
    if ocr:
        parts.append(f"[OCR]({LINKBASE}/{esc(ocr)})")
    if h.get('iiif_url'):
        parts.append(f"[full-res]({h['iiif_url']})")
    return ' · '.join(parts)

# ---- classify real vs noise for headline ----
real = [h for h in hits if tier(h)=='REAL-ZOROK']
noise = [h for h in hits if tier(h)=='NOISE']
possible = [h for h in hits if tier(h)=='POSSIBLE']
excluded = [h for h in hits if tier(h)=='EXCLUDED']

lines = []
A = lines.append
A('# STATUS — Birth of Frederic Zorokens')
A('')
A(f"**Target:** baptism (birth) of **Frederic Zorokens/Zorrokens** — father of Johannes (2nd Petri/Petrus) Zorokens, 2 Feb 1722, St Andries (anchor, user-confirmed).")
A(f'**Window:** {d["window"]}  ·  **Parish (anchor):** St-Andries  ·  **Scope:** A (1685–1712)')
A('')
A('> **Single-file running status log.** One entry block per volume (START → END → results). '
  'Append to this file as each volume completes — do not replace. '
  'Every Zorok* match is listed with tier, edit distance, and clickable evidence. '
  'No match detail is reported "in chat only" — it lives here.')
A('')
A('## TL;DR (interim)')
A('')
A(f'- **6245** (1685–1706): COMPLETE. {len(byvol("6245"))} Zorok* matches, all **FATHER-only** (no child named Frederic). '
  f'{len(real)} real Zorokens (d0–d1), {len(possible)} possible (d2), {len(noise)} stem-contains noise (d3), {len(excluded)} excluded-lineage (Zoron/Zooren).')
A(f'- **6246** (1706–~1715, pp 1–100): COMPLETE but **STRUCTURALLY UNSURE** — scanned with the 6245 parser (child-AFTER-marker), but 6246 is the inverted *filius* layout (child-FIRST, father-AFTER). '
  f'0 matches returned → **NOT a reliable no-hit** until re-scanned with the 6246 (old line) filter.')
A('- **0 STRONG / 0 NEAR / 0 GAP** for a child named Frederic so far.')
A('- **Phase 4 (multi-parish fallback) NOT yet run** (paused at user request).')
A('')
A('---')
A('')
A('## Volume log')
A('')

def vol_block(vol, span, pages_desc, status, ocr_cov, struct_note, extra=''):
    vh = byvol(vol)
    A(f'### {vol} — St-Andries bapt register ({span}) — **{status}**')
    A(f'- **Scope:** pages {pages_desc} · **OCR coverage:** {ocr_cov}')
    A(f'- **Structure:** {struct_note}')
    A(f'- **Zorok* matches:** {len(vh)}  (all FATHER-only unless noted)')
    if extra:
        A(f'- **Note:** {extra}')
    A('')

vol_block('6245', '1685–1706', '1–233', 'COMPLETE',
          '465/466 leaves (1 blank title page 001_L — terminal, not a failure)',
          'child-AFTER-`Infans`-marker (token-stream; variable marker forms). Assessed from real 6245 OCR (see structure_assessment.md).')

A('')
A('#### 6245 — all Zorok* matches (full detail)')
A('')
A('| # | Page | Leaf | Tier | Zorok* token (edit) | B-init | Child-zone tokens | Yr | Evidence |')
A('|---|------|------|------|--------------------|--------|-------------------|----|----------|')
v5 = byvol('6245')
# order: real/possible first, then excluded, then noise
order = {'REAL-ZOROK':0,'POSSIBLE':1,'EXCLUDED':2,'NOISE':3}
v5s = sorted(v5, key=lambda h:(order[tier(h)], h.get('page',0)))
for i,h in enumerate(v5s,1):
    t = tier(h)
    zorok = f"`{esc(h.get('father_zorok_tok'))}` (d{h.get('father_zorok_edit')})"
    binit = 'yes' if h.get('b_initial') else ''
    child = ', '.join(esc(c) for c in h.get('child_zone_tokens',[])[:4])
    yr = ','.join(str(y) for y in h.get('years_near',[])) or '—'
    A(f"| {i} | {h.get('page')} | {h.get('leaf','?')} | **{t}** | {zorok} | {binit} | {child} | {yr} | {links(h)} |")
A('')
A('**Real Zorokens (d0–d1) — the only ones worth a human/crop eye:**')
A('')
for h in sorted(real, key=lambda h:h.get('page',0)):
    child = ', '.join(esc(c) for c in h.get('child_zone_tokens',[])[:4])
    A(f'- p{h.get("page")} (`{h.get("leaf")}`): father **{esc(h.get("father_zorok_tok"))}** (d{h.get("father_zorok_edit")}), child ≈ *{child}* — not Frederic. {links(h)}')
A('')
A('All are **FATHER-only** (a Zorokens man appears as the father of another child) — corroboration that the family is present in 6245, but **none is a child named Frederic**.')
A('')

vol_block('6246', '1706–1727 (1706–~1715 window)', '1–100', 'COMPLETE — UNSURE (wrong parser)',
          f'{len(l646)}/200 L-R leaves + {len(s646)} single-file pages (2 blank title pages)',
          'inverted **filius/filia** layout — child **FIRST**, then `filius/filia [legitimus/legitima]`, then father + mother. **Differs from 6245.** The scan applied the 6245 parser (child-after-marker) to these pages — a structural mismatch. Confirmed from real 6246 OCR: 1168× `filia` + 847× `filius` markers.',
          extra='**0 matches is NOT a reliable no-hit.** The structure-agnostic line net (the "old filter") DID run over 6246 too; an independent re-run found 5 pages carrying a Zorok* token, none with a Frederic child. Re-scan with the 6246/line filter (per-leaf structure tagging) is REQUIRED before 6246 can be called clean.')
A('')
A('**6246 Zorok* token pages seen in the independent structure-agnostic re-run (child-first layout):**')
A('')
A('| Page | Zorok* token seen | Frederic child? | Note |')
A('|------|-------------------|-----------------|------|')
A('| (5 pages) | dekens, joanna **zorrokens**, harekens, doerehens, zoriens | **No** | none is a child named Frederic; all father/parent references |')
A('')
A('---')
A('')
A('## Open items / next steps (your call)')
A('')
A('1. **Extend 6246 past page 100** (covers 1715–~1717 boundary margin, in case Frederic falls just outside 1–100).')
A('2. **Re-scan 6246 with the 6246 (child-first / filius) filter**, per-leaf structure tagging — make the 6246 no-hit clean and unambiguous.')
A('3. **Phase 4 — multi-parish fallback** (index-first, same city as St Andries, fuzzy matcher, per-document structure assessment) — fires only if the window stays empty.')
A('')
A('> Standing rule (this run): every volume START and END is written here with its results; every Zorok* match is detailed in-file, not chat-only. Structure is assessed per-document (can change mid-volume).')
A('')
A(f'_Generated from `frederic_scan.json` ({d["n_ocr_files_scanned"]} OCR files). Evidence links use base `{LINKBASE}` (sibling of `/vault`)._')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT,'w').write('\n'.join(lines)+'\n')
print("WROTE", OUT, os.path.getsize(OUT), "bytes")
print("v5:", len(v5), "| real:", len(real), "| possible:", len(possible), "| noise:", len(noise), "| excluded:", len(excluded))
