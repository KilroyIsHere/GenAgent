---
name: genealogy
description: Use for genealogy or parish register research requests.
version: 1.5.0
metadata:
  hermes:
    tags: [genealogy, archives, orchestration, belgium, report]
---

# Genealogy research (dispatcher)

Entry skill for research requests like "look into the St Joris parish,
birth certificates 1765-1767, find any mention of ZORROKENS". The user does
NOT name agatha, kraken-ocr, the cache, or the report format — that is this
skill's job: pick the tools, apply the standing requirements, deliver the
report in the expected shape. This skill is a ROUTER and a report standard;
the mechanics live in the tool skills and are not re-documented here.

## Routing (do this first, every run)
1. Load the tool skills before touching the site:
   - `skill_view(name='agatha-genealogy')` AND its
     `references/runbook.md` (load both — the runbook encodes hard-won
     mechanics; skipping it wastes ~an hour).
   - `skill_view(name='kraken-ocr')` — the OCR service, models, feeding rules.
2. If the source is NOT agatha.arch.be (familysearch, other archive, a
   document the user uploaded): say so and ask which source to use — do not
   guess a site. (research/agatha-archives is a sibling playbook for the same
   agatha source; agatha-genealogy is canonical here.)
3. Check `ls /workspace/agatha/cache/volumes/` + each volume's `meta.json`
   BEFORE any login/site work. If the requested parish + record type + year
   span falls inside a cached volume's `date_range`, skip the login/search
   steps entirely and go straight to page targeting (per the agatha skill,
   step 0/8). Data is immutable — never re-download a cached page.

## Standing user requirements (apply to EVERY run, without being asked)
- **Unattended operation (user directive 2026-09-16).** Do NOT pause mid-run to
  ask for confirmations or permissions — run to completion, and place ALL
  confirmation requests in the report file (a `## Confirmation needed — user
  review` section): DOUBTFUL rows, illegible fields, cost/scope trade-offs,
  anything the user should eyeball. The user reviews the report at the end.
  Steps the skills already prescribe (crops, OCR, downloads within the task
  scope) need no approval at all.
- **Confirmation requests point to LOCAL CACHED IMAGES, not IIIF URLs.** The
  user reviews far faster from the cache: every verification request in the
  report links the cached page jpg and/or the saved crop png (absolute
  Windows `file:///` link, e.g.
  `file:///D:/AI/workspace/agatha/cache/volumes/<id>/pages/018_L.jpg`,
  `file:///D:/AI/workspace/agatha/cache/volumes/<id>/crops/<crop>.png` — the
  report lives in the Obsidian vault, so relative links would not resolve).
  Save a crop specifically for a DOUBTFUL/needs-review row. The IIIF full-res URL is still recorded per
  row as provenance (city + church + volume + page + URL), but the clickable
  review evidence is the cache file.

- **Cache-first.** Reuse `/workspace/agatha/agatha_cache.py` and the volume
  cache; persist newly resolved IDs (parish/municipality/bookpart) into
  `/workspace/agatha/lookup/*.json` and verified page→month anchors into
  `meta.json` as you go, so the next run starts from verified facts.
- **Reading tool: Kraken `small.safetensors`, per leaf, always.** Serve the
  OCR service each leaf separately (`split_leaves.py` → `NNN_L.jpg`/
  `NNN_R.jpg`, then `ocr_batch.sh`, ≤10 parallel jobs). NEVER a two-page
  spread, never `medium` unless the user explicitly asks.
- **Auto-crop is for DETECTION + SORTING, never a gate (user directive 2026-09-18).** Crop-verify (and the vision tie-breaker) exist to FIND candidates, RANK them, and CATCH POSITIVES — a crop-agreeing candidate is a CONFIRMED hit and that is its main value. But it must NEVER gate or stop the run. An unattended run ALWAYS runs to FULL completion over every in-scope volume, and ALWAYS ends by emitting a COMPLETE RANKED HUMAN-REVIEW document (a single table: # / Vol p.leaf / entry No. approx / what-to-check line / image link / ocr link / Y-N blank / Reason blank), ranked CONFIRMED > DOUBTFUL(crop-agree) > DOUBTFUL(crop-not) > NEAR > GAP > B-initial > FATHER. **A NEGATIVE crop verdict does NOT drop a candidate** — it stays in the review list with full evidence, because the user reviews the final set (negatives included) personally and does not fully trust auto-crop to dismiss negatives. So: crop confirms positives cheaply, but the human-review list is the deliverable and must exist even when there are zero candidates (then state the sweep is complete + the not-digitized boundary). This applies to every multi-parish / multi-volume sweep, index AND register.
- **Vision-model reading: crop-only, when OCR truly fails (2026-09-16).**
  The Kraken small model is the primary reading tool (trained on the user's
  cursive Dutch/Latin hand). `vision_analyze` is AVAILABLE and may be used
  as a tie-breaker for ONE specific line/cell after per-leaf OCR has failed
  on it: crop the region and call vision on the crop, then flag the reading
  "vision-verified, low confidence" in the report. NEVER use vision on full
  pages, batches, or contact sheets — it does not work at that scale. If the
  Kraken service is down, tell the user `docker start kraken` and wait —
  never fall back to vision for bulk reading.
- **Register structure is per-PAGE, not per-volume — detect it before scanning.**
  The entry layout (which token is the child vs father vs mother, and which
  marker opens an entry) can change WITHIN a single volume when a different
  cleric writes a different way. Two distinct layouts exist in St-Andries
  registers (2026-09-17): **child-after** (`<father names> Infans/Intans
  <child> suscept <godparents>` — 6245: 2181 `infans` vs 25 `filia`) and
  **child-first / filius** (`<child> filia/filius [legitimus|spurius]
  <father_first> <father_name> et <mother> suscept <godparents>` — 6246:
  2359 `filia/filius` vs 8 `infans`; child name BEFORE the marker, father
  AFTER it — the inverse). Detect structure per PAGE by counting the
  discriminative markers (filia/filius vs infans/infans-family) on the token
  stream and routing to the matching segmenter; never hard-code one layout
  for a whole volume. Applying the wrong parser returns 0 (or garbled) hits
  silently — a 0-hit on a structure-mismatched page is NOT a reliable
  no-hit until re-scanned with the correct per-page structure.
- **Dates from the page's own heading, read per-leaf.** Anchor each entry to
  the nearest month heading above it in the same column; a leaf can span two
  months. Never extrapolate by pages-per-year density, never "confirm" a
  guessed month against the same page's single OCR header line (circular —
  it produced a real wrong date, 2026-09 vol 6294 p87).
- **Indexes point, registers confirm — and the index structure must be
  discovered first, never assumed.** An index gives a month+day for a target
  surname, but the authoritative date must still come from the register page's
  own heading. Its layout is NOT fixed (year→names / year+month→names /
  year+unsorted): OCR a page sample to learn the sort key before searching, or
  you will miss entries. **A parish can have multiple index volumes for the
  same record type with different content — search ALL that cover the period
  (the results list is paginated; check "N of M results").** In the report,
  say the date was "located via index (vol <id>, <structure>) — confirmed on
  register p<N>" (list every index volume consulted).
- **Names: open-ended variant scan.** 18th-c. cursive mangles surnames
  hard; search case-insensitively with a variant list, keep it open-ended,
  re-run the scan after every OCR round with newly observed variants added.
  **Fuzzy pass is PRIMARY, not a backup:** a fixed prefix/regex net (e.g.
  `\bdo[rz]…`) only matches tokens *starting* with the prefix, so it
  structurally misses in-name drift (`Zovrekens`, a real Zorokens form) and
  initial-letter misreads (a `Borrokens`-initial line where a D→B cursive
  error is plausible). Run a Levenshtein full-name pass (≤ 3) over every
  candidate surname AND first-name token — it catches those, and it is
  *cleaner* too: a genuinely distinct lineage (`Zoron`/`Zooren`/`van Zoron`,
  distance > 3) does NOT surface as a fuzzy candidate, so it stays excluded
  rather than flooding the net. Gate fuzzy hits to the child's surname/
  first-name slot (not a godparent/witness/adjacent family). A B-initial line
  whose first name ≈ the target and whose date is in-window is a DOUBTFUL
  crop-verify candidate — never auto-folded either way. Reuse the exact same
  validated matcher across searches: the matcher costs seconds, the
  OCR/download is what's expensive. Near-misses are review candidates, never
  confirmed hits; report honestly what was found, missed, or excluded. **When cross-checking an entry
  against an index (or another line), match on child's first name + father's
  name + date — NEVER on surname spelling:** the same entry can differ by one
  letter between sources (2026-09-15: register "Johannes, Petri Zorropens"
  = index "Zorrokens Joannes 9 Januarii") and must not be excluded.
- **Multi-parish fallback — the target's birth parish is often NOT the anchor
  parish.** For generation-back searches (parent's birth, grandparent's
  marriage) the parish of the event is frequently different from the anchor
  parish (where the confirmed known entry sits). If the anchor parish's
  register sweep returns no candidate for the target, do NOT conclude
  "no record" — sweep the other parishes **in the same city as the anchor**
  (the anchor's municipality, NOT every city) for the same record type +
  period. **Index-first:** OCR only the target letter range of
  each parish's index (alphabetical indexes are cheap; the D+F letter range
  across the remaining parishes is hours, the register is days). **Register
  only for parishes whose index surfaces a fuzzy candidate** (Levenshtein ≤ 3
  full-name, reuse the exact validated matcher from the anchor-parish run).
  Parishes with no index hit are Excluded (index searched) and pay no
  register cost. **Gated:** this fallback fires ONLY if the anchor parish
  yields nothing; if the anchor confirms a hit, it never runs and costs
  zero. Template: the 2026-09-17 Johannes Petri Zorrokens 1722 birth search
  (13-volume cross-parish sweep) is the established pattern.
- **Push results into a single-file status report — NEVER chat-only.** Every
  multi-volume search keeps ONE running status file in its search subfolder
  (e.g. `STATUS.md`), one append-only block per volume: **START** (scope,
  pages, structure) → **END** (OCR coverage, blank/failed pages) → **results**.
  **Volume label convention (every block, every parish):** every volume number
  in `STATUS.md` is written together with what it means — `**<vol> —
  <municipality/city> <parish> <record-type> register (<date-span>; <in-window
  note if partial>)**` — e.g. `6245 — St-Andries baptism register (1685–1706)`
  or `6243 — St-Andries baptism register (1660–1671; 1667–1671 in window)`.
  Index volumes use the same form: `6222 — St-Andries baptism INDEX (1628–1671)`.
  Put the description in the block header AND in the TL;DR; a bare number like
  `## 6244 — START` is NOT acceptable — the reviewer must be able to tell what
  the volume is (parish, record type, date span) without cross-referencing the
  plan. This applies to all 16 parishes in an Antwerp multi-parish sweep, not
  just the anchor. Keep one `VOL_DESC` map in the runner so the description is
  generated (not typed per block) and can't drift between the START and FINISH
  blocks.
  **Results are a MARKDOWN TABLE, never loose text rows.** Every volume's
  FINISH block renders its candidate list as one table with the fixed columns
  `| # | Page | Leaf | Tier | Zorok* token (edit) | B-init | Child-zone tokens |
  Yr | Evidence |` — identical across every volume and every parish (the
  6245/6246 blocks in the 2026-09-17 Frederic search are the template). Loose
  bullet/`- p123 ...` text rows are NOT acceptable; the user reviews a
  consistent table, not prose. The writer emits the table from the per-volume
  scan JSON, not hand-typed.
  **Child-zone tokens are CLEAN — stop at the godparent boundary.** The
  `susc(ept)/accept` token (and its OCR-mangled forms `susc…`, `sisc…`,
  `susept…`, `huscept…`, `Jeu steptores`, `husceptores`, etc.) is the
  godparent-boundary marker meaning "godparents follow" — it is NOT part of the
  child name. The child zone = tokens after the `infans/filia/filius` marker
  up to (but NOT including) the first godparent-boundary token. The parser
  must truncate the child zone at that boundary (a `cutoff_child()` helper),
  so a displayed child name never contains `suscept`/`susie`/`accept`/`sisc`/
  `huscept`. A child-name cell that still carries a godparent token is a parser
  bug, not data — fix the cutoff, not the row. (2026-09-17: the 6244/6243
  blocks first came out with godparent tokens in the child column; the fix was
  a cutoff regex at the segmenter, not hand-editing rows.)
  Every candidate match is listed **in the file** with page/leaf, a tier
  (REAL-ZOROK d0–d1 / POSSIBLE d2 / NOISE d3 / EXCLUDED lineage), the matched
  token + edit distance, child-zone tokens, in-window year, and clickable
  evidence (image + OCR relative links + full-res IIIF) — the user must never
  have to ask for the details because they were only said in chat. Append a
  block each time a volume starts AND completes; never replace the file, and
  never leave a "found some matches" claim without the per-match table in the
  file. When a volume is scanned with the WRONG parser/structure (structure
  mismatch), its block is marked **UNSURE** and a 0-hit is NOT a reliable
  no-hit until re-scanned with the correct per-document structure. Template:
  2026-09-17 Frederic Zorokens search (`STATUS.md`, 6245 full table + 6246
  UNSURE flag).
- **Quality over speed (user's governing rule).** A missed entry costs
  more than a few extra OCR pages. When scope is ambiguous (which
  pages/blocks/volumes to read), read MORE, not less: read beyond clean
  headers until the next header is found; if a boundary header OCRs
  garbled, extend one more leaf. Cross-check both directions — every
  index entry needs a register-side match AND every register line near
  the target surname/date needs an index-side match; a mismatch is
  DOUBTFUL, never an exclusion. Tie-breaker for ambiguous findings:
  DOUBTFUL beats Excluded — a human reviewer must never find a silently
  dropped candidate. Excluded and DOUBTFUL rows carry the full-res IIIF
  URL so the human can verify against the original without re-downloading.

## Workflow (order matters; details in the tool skills)
1. **Check for indexes FIRST — and search ALL of them.** For the requested
   parish + record type, check `lookup/index_volumes.json` (cached index
   volumes); if not cached, run the index search on the site (check the
   **Indexs** column `TYPEINDEX_PR[]` checkboxes, not the Records column).
   **A parish can have SEVERAL index volumes for the same record type, and
   they do NOT contain the same information** (verified 2026-09-15: St-Joris
   1766 baptisms exist in two different index compilations; searching only
   one missed entries). The results table is also paginated (10/page) — read
   the "N of M results" line and page through if M > 10. Select EVERY volume
   whose span contains the target year and search each one. **The same
   exhaustive-enumeration rule applies to base records (Registers column): a
   parish can have multiple register documents for the same record type —
   enumerate the full list and work every volume covering the target month.** For each:
   **first discover its structure** (OCR a small page spread — layout is
   usually year→names, sometimes year/month→names, sometimes year+unsorted;
   NEVER assume, or you'll miss entries), record it in
   `lookup/index_volumes.json`, then locate the target surname's month+day
   using that structure (per-leaf Kraken), and jump to the register for the
   full entry. **Read the WHOLE year block, not just the page with the clean
   year header:** the block may open on the previous leaf under a garbled
   header, and a surname's entries can be split across the leaf boundary —
   OCR from the first (even garbled) year header until the next. If no index
   exists for that parish/record type (e.g. OLV has
   no funeral/death index), fall through to the register workflow below.
2. Cache/volume check (routing step 3). If cached: `agatha_cache.py
   list <id>` + read `meta.json` `page_month_map`/`page_year_map` anchors.
3. If the volume is not cached: `agatha_cache.py ensure` (auto re-login),
   resolve municipality + parish IDs (check `lookup/*.json` FIRST), submit
   the search form, capture BOOKPART_ID, fetch the manifest, `init` the
   volume. Persist IDs + date range immediately (and any index volumes to
   `lookup/index_volumes.json`).
4. Target the year/month: use verified anchors to pick a candidate page
   window (±a few pages); download that range (cache-first `get`).
5. Split + OCR per leaf (`split_leaves.py`, `ocr_batch.sh`), `small` model.
6. Variant scan over BOTH full-spread and per-leaf OCR files (per-leaf is
   the authoritative reading); pull full entry context around every hit.
7. Anchor each hit to its month heading (per-leaf); record verified
   anchors back into `meta.json`.
8. Write the report (format below) into the Obsidian vault at
   `/vault/genealogy/AI Searches/<search-name>/` — one subfolder per specific
   search, named descriptively after what was searched (e.g. "Birth of
   Johannes Petri Zorrokens", "Marriages of the Zorrokens family 1765-1767").
   The report file is `<family>_<parish>_<span>.md` (or the run's conventional
   name); a long unattended run's completion report goes in the SAME subfolder.
   The execution plan (EXECUTION_PLAN.md) is search-specific, so it ALSO goes
   in this subfolder alongside the report. Other operational scaffolding
   (progress.json, HEARTBEAT.md, sweep scripts, logs, results JSON) stays under
   /workspace — the vault subfolder holds the deliverable report, its completion
   report, and the plan.
9. Report to the user: file path, confirmed hits, doubtful cases flagged
   for human review, what was excluded.

## Report format (markdown file in the Obsidian vault
`/vault/genealogy/AI Searches/<search-name>/` — this is the deliverable)
One file per research request. Every finding must let a HUMAN verify it
without re-doing the work:

```
# <NAME> in <Parish> <record type> <period>
Source: <volume title>, BOOKPART <id>, viewer
https://agatha.arch.be/en/search/genealogie/<id>, <date range>

## Findings
### 1. Page <N> — <Month> <Year> (~day <D>) — CONFIRMED
- OCR (leaf/line): `<exact OCR line>`
- Reading: child / father / mother / godparents (per record type)
- Full-res image: <exact IIIF jpg URL from index.json>
- Viewer: <URL>
- Cache: [NNN.jpg](file:///D:/AI/workspace/agatha/cache/volumes/<id>/pages/<NNN>.jpg) ·
  [NNN_L.ocr.txt](file:///D:/AI/workspace/agatha/cache/volumes/<id>/pages/<NNN>_L.ocr.txt) /
  [NNN_R.ocr.txt](file:///D:/AI/workspace/agatha/cache/volumes/<id>/pages/<NNN>_R.ocr.txt)

## Confirmation needed — review at end
(every question the run could not resolve itself: illegible fields, DOUBTFUL
readings, scope/cost decisions. Each item links the LOCAL CACHED page jpg
and any saved crop (absolute `file:///` Windows link) so the user reviews
from cache, with the IIIF full-res URL as provenance. The run never blocks on these.)

## DOUBTFUL — for human review
(any finding you are NOT confident about: mark DOUBTFUL with the reason,
 e.g. "OCR reading ambiguous, could be X or Y" — the user's rule: when you
 are not sure, it goes in the file as doubtful so a human can review.
 Each DOUBTFUL row links the cached page jpg + crop as the review evidence.)

## Excluded near-misses
(names that matched but are not the target, with page + reason + full-res
IIIF URL — so the human can re-verify against the original image; if you
are unsure a row truly isn't the target, it belongs in DOUBTFUL instead,
never here)
```

Cache refs are ABSOLUTE Windows `file:///` links to the workspace cache
(images, OCR files, crops): `file:///D:/AI/workspace/agatha/cache/...` — the
cache lives at `D:/AI/workspace/agatha` (NOT under a `genealogy` segment; the
WSL `/workspace` maps to `D:\AI\workspace`). The report sits in the Obsidian
vault at `/vault/genealogy/AI Searches/<search-name>/`, so relative links to
the cache would not resolve — use the absolute `file:///` form so a reviewer
clicking from the vault lands on the evidence directly. NEVER link files that
don't exist — verify with `find` on the /workspace path first (e.g. 6262 is
whole-page only, no `_L`/`_R` leaf splits; 6294 pages use zero-padded
`087.jpg`, not `87.jpg`).

## Pitfalls
- **NEVER reconstruct data from memory — always re-read the source files.** These are long, data-heavy jobs (hundreds of pages, dozens of candidate rows, per-leaf assignments, edit distances, hit counts). After any context compaction or across sessions, memory of specific data is UNRELIABLE — page/leaf assignments, candidate rows, hit counts, child/father tokens, and file paths WILL be wrong if recalled from memory. Before citing or writing ANY concrete value (a leaf like `154_L`, a candidate row, a count, a token spelling, a file path), re-read the authoritative source file: `p*_hits.json` / the scan JSON for hits and leaf assignments, `STATUS.md` / the notes / the report for prior results, and the on-disk cache (`ls`/`find`) for what actually exists. Verify links against the real filesystem, not a remembered path. (2026-09-17: a human-review table was rebuilt from post-compaction memory and had ~6 wrong leaf assignments and stale file:// links — corrected only after re-reading `p4_hits.json`, the scan JSON, and verifying each image path on disk.) When in doubt, the disk and the source JSON beat the model's recall, every time.
- **Never let auto-crop be the final word on negatives — always emit the ranked human-review list (2026-09-18).** Crop-verify's job is to catch positives and rank; the user does NOT fully trust it to dismiss negatives. So a crop that reads "not the target" is a DOUBTFUL review row, NOT an Excluded row — the candidate stays in the file with its crop + evidence so the human decides. The run must complete fully (every in-scope volume) and terminate with the complete ranked HUMAN_REVIEW table (every non-CONFIRMED candidate included); a run that stops early or silently drops crop-rejected candidates is a defect. (2026-09-18: the Frederic Zorokens run — Phases 2-4 auto-crop-verified 15 rows to "NOT FOUND"; the user independently re-read them and confirmed 14 N + 1 ? on the raw images, which is why the principle was set: trust the images, keep the negatives in the review list.)
- **Never report match details chat-only.** If you say "found N Zorok* matches"
  you MUST have written each match (page, tier, edit distance, token, child,
  evidence links) into the single-file `STATUS.md` for that search first — the
  user reviews the file, not the transcript, and is not to be made to ask for
  results that were only narrated (2026-09-17: user stopped a run because
  matches were reported in chat with no in-file detail).
- **Never write a bare volume number in STATUS.md.** Every volume must carry
  its meaning on the same line — parish, record type, date span — e.g.
  `6245 — St-Andries baptism register (1685–1706)`. A reviewer reading the
  file (or a future run resuming months later) must be able to tell what each
  volume is without cross-referencing the plan or cache. A generated
  `VOL_DESC` map in the runner keeps the description identical between the
  START and FINISH blocks of the same volume. (2026-09-17: the in-flight
  6244 START block was written as `## 6244 — START · pages 1-186 · 1671-1685`
  with no parish/record-type — the user had to ask; the manual 6245/6246
  blocks had the description, the writer-generated ones didn't. Fixed by
  threading a `VOL_DESC` dict through the writer's `start()`/`finish()` calls.)
- **Never render results as loose text rows — always a table.** Every volume's
  FINISH block must emit its candidate list as one markdown table with the
  fixed columns `| # | Page | Leaf | Tier | Zorok* token (edit) | B-init |
  Child-zone tokens | Yr | Evidence |`, identical across every volume and
  parish. Loose `- p123 …` bullets are not a status report; the user reviews
  a consistent table (2026-09-17: 6245/6246 were tables but the writer-generated
  6244 came out as text rows — the user asked for the table format; fix the
  writer to emit the table from the per-volume scan JSON, not hand-typed).
- **Never let a godparent-boundary token leak into the child name.** The
  `susc(ept)/accept` token (and OCR-mangled `susc…`/`sisc…`/`susept…`/
  `huscept…`/`Jeu steptores`) means "godparents follow" — it is NOT part of the
  child name. Truncate the child zone at the first such token (a `cutoff_child()`
  helper at the segmenter). A child-name cell that still contains
  `suscept`/`susie`/`accept`/`sisc`/`huscept` is a parser bug — fix the cutoff,
  don't hand-edit the row (2026-09-17: 6244/6243 first came out with godparent
  tokens in the child column; the cutoff was added at the segmenter and the
  blocks regenerated, NOT edited row-by-row).
- Do not re-document tool mechanics here; if something in this skill and a
  tool skill disagree, the tool skill (or the user) wins — update this
  router, not the copy.
- Stale session is a soft problem: `agatha_cache.py ensure` re-authenticates
  automatically; `get`/`init` call it, so it is usually invisible.
- The month/day comes from the page heading + the left-margin day numerals
  (they reset at each heading); never quote a sequential "entry number".
- Report honestly: a missing/illegible field is reported as such, never
  filled in.
- **Never assume a register's entry layout, and never assume it's constant
  within a volume.** A different cleric mid-volume can flip the layout
  (child-after-Infans ↔ child-first-filius). OCR a page sample, count the
  marker families (Infans vs filia/filius), and detect structure per page —
  2026-09-17: a 6245-style child-after parser applied to the child-first 6246
  returned 0 Zorok* hits while 18 real family entries sat in the father zone,
  so the no-hit was only caught because a structure-agnostic line net was also
  run. If both nets agree and the structure was correctly assessed per page,
  the no-hit is reliable.
- **Never assume an index is alphabetical-by-surname.** Discover its actual
  structure (year→names? year/month→names? unsorted?) by OCRing a page sample
  before searching; an assumption here silently drops hits.
- **Never search only one index for a period.** Enumerate the full (paginated)
 result list, pick every volume whose span covers the target year, and search
 each — a parish's multiple index volumes are distinct compilations with
 different content (real miss 2026-09-15: St-Joris 1766 covered by two
 indexes, only one was searched; the Zorokens 1766 block exists only in the
 second, 6262). **And within each index, read the WHOLE year block — from the
 first (possibly OCR-garbled) year header to the next, across leaf boundaries.**
 A year's entries can start a leaf earlier than the cleanly-OCR'd header
 suggests; anchoring at the clean header page silently drops the first
 entries of the block (real miss 2026-09-15: 6260's 1766 Zorrokens block
 opens on p205_R under a garbled header; reading only p206_L missed the
 January + July entries). **Base records obey the same exhaustive rule:** the
 Registers results table is also paginated and a parish can have MULTIPLE
 register documents for the same record type covering a period — enumerate
 all of them and work every volume whose span contains the target month,
 never just the first match.
 - **Match candidates by child's first name + father's name + date — NEVER by
 surname spelling.** 18th-c. OCR mangles surnames in both index and register
 a letter apart; the same entry can read "Zorrokens" in one and "Zorropens"
 in the other. When child + father + date agree, that is a confirmed match
 even if the surname differs by a letter — and such a line must NOT be
 excluded from the results as a "different family" (real miss 2026-09-15:
 register p87_R "Johannes, Petri Zorropens, Januari 1766" IS index 6260
 "Zorrokens Joannes 9 Januarii").
 - **Never rely on a fixed prefix/regex surname net alone.** A regex like
   `\bdo[rz][rre]*` only catches surnames that *start* with `zor`; it
   structurally missed real lines (a `Zovrekens` spelling, and a
   `Borrokens`-initial line) in the 2026-09-17 Johannes re-scan over the
   already-OCR'd corpus. Pair the seed-variant pass with a Levenshtein ≤ 3
   fuzzy pass (primary); the distinct-lineage exclusion (`Zoron`/`Zooren`/
   `van Zoron`, distance > 3) is preserved for free because those don't
   surface at ≤ 3. A fuzzy re-scan of an already-OCR'd corpus costs seconds
   — run it before concluding an entry is absent, because it surfaces what
   the seed net could never match.
- **Do not stop at the anchor parish when the target's birth parish is
  uncertain.** If you're searching for a parent's birth (a generation back)
  and the anchor parish's register comes up empty, the target may have been
  baptized in a different parish **in the same city as the anchor** (not
  every city — stay scoped to the anchor's municipality) — sweep the other
  parishes' indexes
  (index-first, register only on a fuzzy index hit) before concluding "no
  record exists." A single-parish miss is indistinguishable from a true
  absence without the fallback. (Template: 2026-09-17 Johannes Petri
  Zorrokens 1722 birth search — 13-volume multi-parish sweep.)
