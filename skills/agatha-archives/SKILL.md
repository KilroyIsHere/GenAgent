---
name: agatha-archives
description: "Query agatha.arch.be Belgian archive genealogy registers."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Genealogy, Archives, IIIF, Belgium, OCR, Historical-documents, Browser]
    related_skills: [pdf, blocked-page-recovery]
---

# AGATHA Belgian Archive Registers

AGATHA (https://agatha.arch.be) is the State Archives of Belgium's online genealogy
search. Queries like "death records, Antwerp, Onze-Lieve-Vrouw, January 1732,
entries 15-21" go through: login → parish/record-type search → volume results →
Mirador IIIF viewer → full-res page images → per-leaf Kraken OCR → transcribe the cursive.

Use this skill when asked to look up baptisms/marriages/deaths or to read specific
pages/entries from Belgian archival registers. A more complete, deployment-specific
skill is `agatha-genealogy` (page-image cache, per-leaf OCR pipeline, verified
anchors) — if it exists, prefer it; this skill covers the site mechanics.

Full verified playbook (account details, ajax.php endpoints, known IDs, curl
recipe, pitfalls) is in `references/agatha-playbook.md` — read it before the
first run; it has everything that cost real time to discover.

## Reading rule (user mandate)
The Kraken OCR service (`kraken-ocr` skill, `small.safetensors` — trained on
this cursive Dutch/Latin hand) is the ONLY normal reading tool. Never read pages
with the agent's own vision model: not full pages, not batches, not contact
sheets. Vision is a last-resort tie-breaker for a single specific line/region
after per-leaf OCR has failed, and must be flagged "vision-verified, low
confidence" in the output.

## Core workflow (5 steps)

1. **Log in** via `browser_exec` (credentials in references file). The Login link
   is hidden in the collapsed mobile hamburger menu — toggle it first.
   Verified: header shows the username + `PHPSESSID` cookie. Grab the cookie with
   `js("document.cookie")` for later curl calls.
2. **Find the parish**: the municipality/parish fields are jQuery UI autocompletes
   (`.val()` does NOT work; use `fill_input` for real keystrokes). Faster: POST
   `ajax.php` directly with curl (`method=getMunicipalities` /
   `getParishFromMunicipality`) to get PLACEPOINT_ID / PARISH_ID, then set the
   hidden form fields and submit `#PR_FORM`. Record types: `TYPEACTES_PR[]`
   1=baptism 2=marriage 3=death. The requested year range is only a filter —
   volumes are fixed historical registers; pick the volume whose span actually
   contains the requested month.
3. **Get the volume page**: results row clicks call `gotoClick()` →
   `window.open('/en/search/genealogie/<BOOKPART_ID>')`. Hook `window.open` in JS
   to capture the URL, then navigate.
4. **Download full-res page images** (the key trick): the viewer page HTML embeds
   `manifest_path` (IIIF Presentation 2 JSON). Fetch it with curl (Referer +
   PHPSESSID) → each canvas has a `rendering` link
   `https://i3f.arch.be/iiif/.../<name>_r.jp2/full/full/0/default.jpg`. Download:
   `curl -H "Referer: https://agatha.arch.be/" -H "Cookie: PHPSESSID=..." <url> -o page.jpg`.
   Top-level browser navigation to image URLs 403s; canvas reads are cross-origin
   tainted — the curl+Referer route is the reliable one. Thumbnails are too small
   to read cursive.
5. **Locate the month, then transcribe — per-leaf Kraken OCR**: canvas labels
   are just "p. N" with no dates. Register pages are two-column spreads and
   month headings can be ANYWHERE on the page. **Never date by
   pages-per-year extrapolation** and never "confirm" a guessed month with the
   same page's single (possibly garbled) OCR header line — that is circular.
   Method: split each spread into its two leaves (`split_leaves.py`), OCR each
   leaf with Kraken `small` (`ocr_batch.sh`, ≤10 parallel jobs); leaf-top
   headings OCR cleanly, and every entry anchors to the nearest month heading
   ABOVE it in the SAME column (a leaf can straddle two months — check for a
   mid-leaf heading). Then read the entries from the per-leaf OCR. 18th-c.
   Flemish cursive needs best-effort transcription: gloss abbreviations
   (een kind, cathe, kerkhof, etc.), search names with a generous
   case-insensitive variant list, and flag illegible or crossed-out lines
   honestly. A variant list is a FLOOR, not the search — Kraken mangles
   cursive surnames enough that a real edit-distance (Levenshtein) fuzzy
   pass over the surname slot is required for a no-miss result; see the
   "Fuzzy name search" pitfall below and `references/fuzzy-name-scan.md`. Left-margin numerals are day-of-month (reset at each heading),
   right-margin are monthly tallies — quote month+day. Report gaps, don't
   invent entries.

## Pitfalls

- Login link invisible until the mobile hamburger is toggled.
- Parish select disabled until a municipality is selected; a blank results page
  usually means the parish was never actually selected (or a cookie banner is covering).
- `web_extract` may be unavailable in this deployment — use curl or browser_exec.
- reCAPTCHA iframes on the viewer are decorative; nothing to solve.
- Browser Python variables don't persist across `browser_exec` calls — persist
  IDs/URLs to files in `$BH_AGENT_WORKSPACE`.
- PIL needs a venv (`uv venv` + `uv pip install pillow`) if cropping locally;
  in this deployment `/workspace/.venv` already has it (used by
  `split_leaves.py`).
- **Do not use the agent's own vision model to read these pages** (user
  mandate): it misreads 4-digit years and does not scale to batches/contact
  sheets. The Kraken small model (per-leaf input) is the reading tool; month
  names from leaf-top OCR are reliable. Anchor the volume's final year with its
  last page (closing prayer "Pie Jesu Domine", monthly + "in toto" totals)
  and verify against `meta.json` date_range.
- **A 0-byte viewer page from curl is NOT "no manifest" — it needs session state.** GET
  `https://agatha.arch.be/en/search/genealogie/<id>` with just the cookie can
  return an empty body (exit 0, 0 bytes). Fix: open the viewer page in
  browser_exec and extract `var manifest_path=` from the live DOM (the page
  carries the IIIF Presentation 2 JSON path), then fetch/init the volume as
  usual. Verified 2026-09-15: volumes 6291 and 6265 (Sint-Joris) could only be
  initialized this way; plain curl got nothing for either.
- **A Latin genitive on the FATHER line is not a match on the target's second given name.**
  18th-c. registers write the father as the genitive of his FIRST name: "Petri
  Zorrokens" = son of Petrus — even when the target man carries "Petri" as his
  OWN second given name ("Johannes Petri Zorrokens"). So a line whose father
  reads "Petri ..." is NOT automatically the target, and a second given name
  does NOT mean "son of Petrus". Confirm matches on the CHILD's own name
  field: both given names present, right one first ("Johannes" +
  "Petri/Petrus/Baptista"); indexes often record only the first name, so an
  index row like "Joannes 8 febr 1736" is a candidate, not a confirmation —
  verify the second name on the register crop. If the user says the father's
  name is unknown, the father is never a search constraint: child name +
  surname only. A wrong reading inverts the whole search (2026-09-15: target
  was the FATHER of the 1766 child, born pre-1742; "Joannes Baptista 1742"
  with father line "Petri Zorrokens" is a sibling, excluded because his own second name is Baptista).
  - **A name index can be MULTI-CYCLE (year-banded), not a single A→Z run.** Before hunting one surname band (e.g. the D-section of a Zorrok* search), OCR a spread of pages ACROSS the whole volume and check that the dominant surname letter is monotonic with page number. If the letters are non-monotonic (e.g. C at p10, W at p61, C again at p142) the volume runs A→Z several times — once per year-band — and a single-band hunt misses most cycles. In that case (or whenever the structure is in doubt AND the volume spans many years) do a structure-agnostic FULL-volume variant scan: OCR every page and grep the open-ended surname-variant list — the no-miss approach that matches the user's quality-over-speed rule. Cost note: a 200-page volume ≈ 7 min at 10-way parallel Kraken `small`, so full-scanning is affordable; the band-hunt only saves time if the structure is a confirmed single A→Z run.
 - **A fixed prefix-anchored variant regex is a BLIND SPOT for mangled surnames — always run a Levenshtein fuzzy pass too.** The obvious approach is a case-insensitive regex on the surname stem, e.g. `\\bdo[rz][rre]*[a-z]{0,8}\\b` for Zorrokens. That only matches tokens that START with the exact prefix, so it is structurally blind to: (a) a wrong leading letter — a B-initial `Borrokens` family is invisible to a `do[rz]` regex; (b) an inserted/extra letter mid-word — `Zovrekens`, `Zoorekens`; (c) a dropped vowel/letter. These are exactly the cursive OCR failures you must not miss. When you have already OCR'd a corpus (a sweep ran, a prior search exists), re-scanning the SAME `.ocr.txt` files with a real edit-distance matcher is FAST (no new OCR, seconds, not minutes) — treat it as a mandatory second pass, not optional. Design that worked (2026-09-17, re-scan of the 22-volume Johannes Petri Zorrokens corpus, ~5200 OCR files): score the surname-slot token against BOTH target surnames (e.g. `zorokens` AND `zorrokens`) with whole-token Levenshtein ≤3 (clean, reviewable), PLUS a distinctive-stem CONTAINS pass (`zorok`/`zorrok`/`zorock`) so `van Zorokens` / `vzorokens` / `Zoorekens` still fire. TWO traps: (1) a short-stem contains at distance 2 FLOODS with unrelated names (Theodorus, Doncker, Van Zooren, Ludovicus…) — keep the stem distinctive (≥5 chars) and the whole-token distance ≤3; (2) gate by SLOT — a fuzzy surname match only counts in the CHILD's own surname/first-name field, never a godparent/witness/neighbouring-family field, or unrelated families flood the result. Keep the match key = first-name + fuzzy-surname + date, never surname alone. Every fuzzy hit is DOUBTFUL until a crop-verify of the line agrees (Kraken hallucinates cursive surnames). Report the fuzzy findings as a DELTA vs the fixed net (which lines the regex could never have matched) so the user sees exactly what the fuzzy pass added. Reusable matcher: `scripts/fuzzy_name_match.py`.
  - **Reconcile the parish enumeration BEFORE committing OCR cost** (a partial/earlier scope table has silently skipped whole parishes). When enumerating the covering volumes for a parish (or all parishes), via the site search / `ajax.php getResults` at pageSize=50: (a) DE-DUPE duplicate physical scans — the same scan is frequently listed under several year-range bookpart IDs (observed: 6141/6142/6143, 6088/6089, 6327/6328, 6189/6190 are each ONE physical scan); identical page count = same scan, so sweep it once. (b) Check the `avail` flag on every enumerated volume: `avail: false` means the volume is listed but NOT digitized to full-res — it cannot be OCR'd; record it as "covering volume exists, not digitally accessible" and move on (never silently drop it). (c) If a parish has no covering INDEX but a covering chronological REGISTER, OCR the date slice of the register (e.g. San Felipe del Castilla 6355 1700-1795) — a register is the only covering source for that parish. (d) Re-verify the enumeration is complete (direct `getResults` at pageSize=50; max parish total is small so one page covers it) rather than trusting a scope table carried over from a prior aborted run.
  second name is Baptista).
