#!/usr/bin/env python3
"""Per-volume STATUS writer for the Frederic Zorokens search.

Standing rule (user): every time a volume is started / finished, write it AND
its results to a single append-only STATUS.md in the search subfolder, with
every candidate match detailed. The user reviews this file, not the transcript.

Single file:
  /vault/genealogy/AI Searches/Birth of Frederic Zorokens
  (father of Johannes Petri 1722)/STATUS.md

Append-only: never clobber. init writes a header only if the file is missing;
all subsequent entries are appended.
"""
import os, time

SEARCH_DIR = ("/vault/genealogy/AI Searches/"
             "Birth of Frederic Zorokens (father of Johannes Petri 1722)")
STATUS = os.path.join(SEARCH_DIR, "STATUS.md")
# STATUS.md sits 4 levels under the vault root; /workspace is a sibling of
# /vault, so the correct evidence-link base is 4x up.
LINK = "../../../../workspace/agatha/"

def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

def _w(s):
    os.makedirs(SEARCH_DIR, exist_ok=True)
    with open(STATUS, "a") as f:
        f.write(s)

def init(search_title="Birth of Frederic Zorokens (father of Johannes Petri, 2 Feb 1722, St Andries)"):
    if os.path.exists(STATUS) and os.path.getsize(STATUS) > 0:
        return  # append-only: never clobber an existing status file
    _w(f"# STATUS — {search_title}\n\n")
    _w("Scope A (1685–1712). Single end-to-end, resumable, cache-first run.\n\n")
    _w("Append-only. One entry per volume: a START marker when OCR begins, then a\n")
    _w("FINISH block with the full scan results. Every candidate match is listed here\n")
    _w("(page/leaf, tier, edit distance, child tokens, year, and clickable image + OCR +\n")
    _w("full-res evidence). A volume scanned with the wrong parser is marked UNSURE (not a\n")
    _w("reliable no-hit) until re-scanned with the correct structure filter.\n\n")

def start(vol, pages, date_range, ocr_total, note="", desc=""):
    hdr = f"## {vol} — {desc} — START" if desc else f"## {vol} — START"
    _w(f"---\n\n{hdr} — {_ts()}\n\n")
    _w(f"- pages {pages}  ·  {date_range}\n")
    _w(f"- OCR leaves queued: {ocr_total}\n")
    if note:
        _w(f"- note: {note}\n")
    _w("- status: OCR in progress…\n\n")

def _years_str(yrs):
    if not yrs:
        return "year unanchored (in-window assumed)"
    return "year " + "/".join(str(y) for y in yrs)

def _tier_line(h, kind):
    """One detailed line for a hit. kind in strong/near/gap/father/excl."""
    vol, page, leaf = h.get('volume'), h.get('page'), h.get('leaf')
    if kind == 'gap':
        d = h.get('line_zorok_tok'); de = h.get('line_zorok_edit')
        kind_s = h.get('line_zorok_kind')
        fk = h.get('line_fred_tok'); fe = h.get('line_fred_edit')
    elif kind == 'father':
        d = h.get('father_zorok_tok'); de = h.get('father_zorok_edit')
        kind_s = h.get('father_zorok_kind')
        # FATHER-only: the useful detail is the ACTUAL child name (whose child
        # it is) — not a missing Frederic. Show the real child-zone tokens.
        ct = h.get('child_zone_tokens', [])
        fk = (' '.join(ct[:2]) + ' (child, not target)') if ct else '—'
        fe = ''
    else:
        d = h.get('father_zorok_tok'); de = h.get('father_zorok_edit')
        kind_s = h.get('father_zorok_kind')
        fk = h.get('fred_child_tok') or h.get('fred_godp_tok')
        fe = h.get('fred_child_edit') or h.get('fred_godp_edit')
    binit_s = "  (B-initial → crop-verify)" if h.get('b_initial') else ""
    fe_s = f" (d={fe})" if fe != '' else ""
    return (f"  - **{vol} p{page}/{leaf}** — Zorok* `{d}` (d={de}, {kind_s}) "
            f"· child ≈ `{fk}`{fe_s} · {_years_str(h.get('years_near', []))}{binit_s}")

def _evidence(h):
    img = h.get('image', '')
    ocr = h.get('ocr_file', '')
    iiif = h.get('iiif_url', '')
    s = (f"    · [img]({LINK}{img}) · [ocr]({LINK}{ocr})")
    if iiif:
        s += f" · [full-res]({iiif})"
    return s

def finish(vol, pages, date_range, scan, ocr_done, ocr_total, unsure=False, note="", desc=""):
    """Write a FINISH block for one volume with every candidate detailed.
    `scan` is the per-volume scan JSON (hits/gaps). Marked UNSURE if the slot
    parser is not reliable for this volume's structure (0-hit not a no-hit)."""
    hits = scan.get('hits', [])
    gaps = scan.get('gaps', [])
    strong = [h for h in hits if h.get('verdict') == 'STRONG']
    near = [h for h in hits if h.get('verdict') == 'NEAR']
    excl = [h for h in hits if h.get('excluded_lineage')]
    father_clean = [h for h in hits
                    if h.get('verdict') == 'FATHER' and not h.get('excluded_lineage')]

    flag = "  ·  **UNSURE — wrong parser for this volume's structure, re-scan required**" if unsure else ""
    hdr = f"## {vol} — {desc} — FINISH" if desc else f"## {vol} — FINISH"
    _w(f"---\n\n{hdr} — {_ts()}\n\n")
    _w(f"- pages {pages}  ·  {date_range}\n")
    _w(f"- OCR: {ocr_done}/{ocr_total} leaves\n")
    _w(f"- scan: files={scan.get('n_ocr_files_scanned', '?')} "
       f"entries={scan.get('n_entries', len(hits))}\n")
    _w(f"- **{len(strong)} STRONG** · {len(near)} NEAR · {len(father_clean)} FATHER "
       f"· {len(excl)} excluded-lineage · {len(gaps)} GAP (crop-verify){flag}\n")
    if note:
        _w(f"- note: {note}\n")

    def _block(title, rows, kind):
        if not rows:
            _w(f"\n**{title}: 0**\n")
            return
        _w(f"\n**{title} ({len(rows)}):**\n")
        for h in rows[:80]:
            _w(_tier_line(h, kind) + "\n")
            _w(_evidence(h) + "\n")
        if len(rows) > 80:
            _w(f"    · … and {len(rows) - 80} more (full list in "
               f"`runs/frederic_zorokens/frederic_scan.json`)\n")

    _block("STRONG (father Zorok* + child Frederic)", strong, 'strong')
    _block("NEAR (father Zorok* + Frederic in godparent zone)", near, 'near')
    _block("GAP (line-net safety hit the slot parser missed)", gaps, 'gap')
    _block("FATHER only (Zorokens sibling corroboration)", father_clean, 'father')
    _block("EXCLUDED lineage (Zoron/Zooren — distinct family)", excl, 'excl')
    _w("\n")
