---
name: agatha-genealogy
description: Look up Belgian parish registers on agatha.arch.be.
version: 0.9.0
metadata:
  hermes:
    tags: [genealogy, archives, agatha, iiif, ocr]
---

# AGATHA genealogy queries (agatha.arch.be)

Answer "look up X in the Belgian state archives" queries on
https://agatha.arch.be/en/search/genealogie/ — church registers (baptisms,
marriages, deaths). The site is image-based: you search for a volume, then
download and read the actual register pages as full-resolution images. The
detailed gotcha list and copy-paste runbook live in `references/runbook.md`
(load it with `skill_view(name='agatha-genealogy', file_path='references/runbook.md')`
before starting — it encodes hard-won mechanics; skipping it wastes ~an hour).

## When to Use
- User asks to look up births, marriages, or deaths in Belgian/Antwerp parish
  or civil registers on agatha.arch.be.
- Don't use for: other archive sites, or already-transcribed datasets.

## Prerequisites
- `browser_exec` (login + form submit + capturing BOOKPART_IDs), `terminal`
  curl (all data downloads).
- **Reading the manuscript: the Kraken OCR service (see `kraken-ocr` skill) —
  `small.safetensors` is trained on this cursive Dutch/Latin hand and is the
  primary reading tool. `vision_analyze` is AVAILABLE (2026-09-16) as a
  crop-only tie-breaker, to be used ONLY when OCR truly fails on a specific
  line/cell: crop the region, call vision on the crop, and flag the result
  "vision-verified, low confidence" in the report. NEVER use vision on full
  pages, batches, or contact sheets — it does not work at that scale.**
- Login: user `<AGATHA_USER>` / password `<AGATHA_PASSWORD>` (user's own credentials).
- PIL for cropping: system python3 lacks PIL — use `/workspace/.venv/bin/python`
  (already set up).

## Execution mode — UNATTENDED (user directive 2026-09-16)

The run goes end to end WITHOUT asking the user for confirmations mid-run.
All work the skills prescribe is pre-authorized: local crops, Kraken small
OCR (including crops on cached pages), cache downloads/init, site searches
within the task's scope, report updates. Do not pause to ask "may I do X?" —
just do it. (Earlier 2026-09-15 rule — crop+OCR runs without waiting — is
subsumed by this.)

Everything that would have needed a confirmation (illegible field, DOUBTFUL
row, cost/scope trade-off, a vision-model tie-breaker, a scope extension)
goes instead into the report file under a `## Confirmation needed — review
at end` section, and the run continues. The user reviews the report at the
end.

Hard limits that still apply even in unattended mode:
- **Kraken model stays `small`** (medium only if the user explicitly asked in
  the task itself).
- **No destructive cache ops** (`clean`, deleting cached pages) unless the
  task itself requested it — note the need in the report instead.
- **Scope discipline:** stay within the task's stated period/parish/record
  type. If the work clearly requires reading many more pages than the task
  implies, do NOT silently balloon it: log a cost note in the report's
  Confirmation-needed section and continue with the scoped subset.

Review requests in the report MUST point to LOCAL CACHED IMAGES (absolute Windows `file:///` links to the workspace cache — `file:///D:/AI/workspace/agatha/cache/volumes/<doc_id>/pages/...` — the page jpg and any saved crop png), because the user reviews from the cache, not the archive.
The full-res IIIF URL is still recorded per row as provenance — and EVERY report row (confirmed, DOUBTFUL, Excluded) carries BOTH the IIIF URL and clickable ABSOLUTE `file:///` cache links to the local evidence, so the user verifies from cache without re-downloading (user rule 2026-09-16): e.g. `![OCR](file:///D:/AI/workspace/agatha/cache/volumes/<vol>/pages/<NNN>.ocr.txt) · [image](file:///D:/AI/workspace/agatha/cache/volumes/<vol>/pages/<NNN>.jpg)` (absolute Windows path — the report now lives in the Obsidian vault at `/vault/genealogy/AI Searches/<search-name>/`, so relative links would not resolve; convert the sweep's results-JSON `ocr_file`/`image` /workspace paths to this form, e.g. `agatha/cache/volumes/<vol>/...` → `file:///D:/AI/workspace/agatha/cache/volumes/<vol>/...`). A hit row with an IIIF URL but no cache link is an incomplete row.

## Unattended long-sweep architecture (auto-recover + logging)

For Phase-5-scale work (dozens of volumes, hundreds+ pages, multi-hour
OCR), do NOT drive every page from the agent loop — it floods context and a
mid-run crash loses hours. Instead run a small set of durable, resumable
Python scripts and let cron + a heartbeat watch them. Pattern (proven on the
2026-09-16 Phase-5 ZORROK* sweep, 13 index scans / ~2769 pages):

**1. The sweep script (`full_sweep.py` pattern) — resumable, self-logging,
   and failure-aware (hardened 2026-09-16).** One script, one logical unit
   (e.g. "full-volume variant sweep"). For each volume: download ALL pages
   (curl, cache-first, `Referer` + `Cookie`), OCR all pages at ≤10 parallel
   Kraken small, scan for the surname variants + in-range dates, and append a
   per-volume record to a results JSON (`lookup/<run>_results.json`:
   `completed` map + `all_hits` list) AFTER each volume. Skip any volume
   already marked `done` and any page already OCR'd (`.ocr.txt` exists,
   non-empty). Log to `logs/<run>.log` (progress + in-range hits). A crash
   loses at most the in-progress volume; relaunch `python3 full_sweep.py` and
   it resumes. In-range hits print live AND land in the JSON (the JSON is the
   source of truth; the log is for humans).
   **NEVER mark a volume `done` on best-effort results (the 2026-09-16
   defect):** the original script did ONE download + ONE OCR attempt per page
   and set `done=True` unconditionally — so an EMPTY OCR or a 403/timeout
   page was silently dropped, absent from the hits scan (`scan_page` returns
   `[]` for a missing `.ocr.txt`), and a relaunch skipped the "done" volume
   forever. That is a no-miss violation, not a cost. Hardened pattern:
   (a) `dl()` and `ocr()` retry up to 3× with backoff (3s/6s/9s); `ocr()`
   REMOVES a 0-byte output file between attempts (a 0-byte `.ocr.txt` would
   otherwise be read as "cached ok" on the next attempt); (b) the volume
   record carries `dl_fail`/`ocr_fail` counts and `done=True` ONLY when both
   are 0 — a volume with failures prints `!! NOT marked done` and re-runs on
   relaunch; (c) persistent failures are expected to exist (dark/blank leaves
   genuinely OCR to EMPTY no matter how many times you try — real instance:
   6141 p102, a genuinely blank leaf) — that is what the audit + vision pass
   below is for, NOT more blind retries.

**2. Dependent work self-waits (Kraken OOM discipline).** Anything that
   follows the sweep and would add load (e.g. a register slice for a parish
   whose only covering source is a chronological register, not an index) runs
   as a separate script that FIRST polls the sweep's results JSON and only
   starts when the sweep is fully done — Kraken OOMs at >3 parallel jobs and
   queueing a concurrent batch behind the sweep stalls it. Set a done-FLAG file
   (`lookup/<run>_done`) when finished so a watcher can flip state.

**3. Heartbeat script (15-min, newest-first) — the abend safety net.**
   `scripts/genealogy_heartbeat.py` runs in the background (parented to the
   gateway PID 1, so it outlives the chat session). Every 15 min it reads
   `progress.json` (written by the running session at milestones) + file
   mtimes and inserts a `### <UTC>` snapshot at the TOP of
   `HEARTBEAT.md` (newest first, so a crash is visible as a stale/missing
   newest entry). Keep updating `progress.json` at every milestone (phase,
   parish, volumes, hits, ETA, next) so the heartbeat reflects reality — a
   stale `progress.json` makes the heartbeat useless.

**4. Monitor-gated cron for self-heal + completion (NOT for chatting).**
   A cron job every ~10 min with a `monitor_script` (state gate) + a
   self-heal prompt. The gate (`sweep_state.py`) emits deterministic lines
   with coarse ENUM values (never counters/timestamps), so the line stays
   STABLE during normal progress and the agent only wakes on a real flip:
   `sweep=<running|dead|done> sanfelipe=<running|down|done>` plus
   `audit13=<pending|clean|failures>`. On `dead`/`down` the agent relaunches
   the (resumable) script; on `audit13=clean` the index work is no-miss
   CERTIFIED (every page verified on disk); on `audit13=failures` the agent
   runs the vision-band pass on the flagged pages (see audit certifier above)
   and records the outcome; on `sanfelipe=done` + `audit13=clean` it writes
   the completion report. If `audit13` is `pending` with nothing running,
   relaunch the audit (it self-waits; idempotent). Grant the job the
   `vision` toolset if the prompt's failure path needs vision_analyze. This
   is what makes the job finish without the user.
   - **Path gotcha (cost a lost fire 2026-09-16):** cron resolves
     `monitor_script` against `$HERMES_HOME/scripts/`. Here
     `HERMES_HOME=/opt/data`, so the gate MUST live at
     `/opt/data/scripts/sweep_state.py` — NOT `~/.hermes/scripts/` (which is
     `/opt/data/home/.hermes/scripts/`, a DIFFERENT dir). Verify with
     `python3 /opt/data/scripts/<gate>.py` before trusting the job.
   - **api_server delivery caveat (cost a wrong promise 2026-09-16):** this
     deployment is the `api_server` platform — pull-based HTTP, NO push
     channel (no Telegram/Discord/etc.). A cron job CANNOT push a message
     into the user's chat: the fire log shows `API server uses HTTP
     request/response, do not send()`. So set `deliver=local` (avoids the
     failing send that can get the job auto-paused on a streak) and make the
     job's deliverable a DURABLE FILE — e.g. append every milestone to
     `COMPLETION_REPORT.md` — which the user/I read on next check-in. Do NOT
     promise the user "I'll ping you when it's done" for a cron on this
     platform; instead promise a durable report + the 15-min heartbeat. Every
     candidate row in that report needs the IIIF URL AND relative cache links
     (same format as the report rule above) — the results JSON's
     `ocr_file`/`image` fields give them verbatim.

**5. Audit certifier (the no-miss guarantee — filesystem, not flags).**
   A separate long-lived script (`sweep_audit.py` pattern) runs AFTER the
   sweep and any dependent slice (self-waits on the sweep process + the
   slice's done-flag, so it never contends with a Kraken batch). It is
   AUTHORITATIVE and independent of the sweep's own done flags: for EVERY
   page of EVERY volume it checks the actual cache files (jpg >10KB AND
   non-empty `.ocr.txt`), retries any hole 3× via the sweep's own dl/ocr
   (so it recovers ANY crash state — if the sweep died at vol 10/13, the
   audit downloads+OCRs vols 11-13 itself; the sweep's resumability is the
   belt, the audit is the suspenders). Persistent failures land in
   `lookup/sweep_failures.json` — each with volume/parish/page, IIIF URL,
   image + ocr paths, and `needs: vision wide-band crops or human read` —
   i.e. surfaced, never silently skipped. It writes flag files:
   `audit13_done` (count of unresolved; 0 = clean) after the index volumes
   and `audit_done` after the dependent slice. The dependent slice must gate
   on the AUDIT flag (not the sweep's done count) so it starts only after
   the pages are actually read. **Vision resolution of audit-flagged pages:**
   crop the page into ~4 WIDE horizontal bands (wide > narrow), run
   `vision_analyze` per band; if all bands confirm a blank/ruled-unfilled
   page, write a vision-verified blank marker into the `.ocr.txt` (so the
   audit re-passes clean) and record it in the report; if any band has
   content, transcribe it into the `.ocr.txt` (marked "vision-verified, low
   confidence") and re-run the variant scan on it. **DUAL naming convention —
   check both before calling a page a hole:** NEW volumes use per-page
   `NNN.jpg` + `NNN.ocr.txt`; LEGACY St Joris volumes (6290/6291/6292/6293)
   use full-res SPREAD halves `NNN_L.jpg`/`NNN_R.jpg` (each ≈ 2 scan pages)
   with `NNN_L.ocr.txt`/`NNN_R.ocr.txt`, plus plain `NNN.jpg` single-leaf
   files. A naive per-page audit (expecting `NNN.jpg`+`NNN.ocr.txt`)
   false-alarms hundreds of "holes" on legacy volumes — real incident
   2026-09-16: 6290/6291/6292/6293 initially reported full of holes; actual
   coverage was 219/220/230/140 leaves COMPLETE). `sweep_audit.py` therefore
   has a `phase_legacy()` dual-convention verify (zero Kraken cost,
   verify-only: every in-scope leaf NNN has `_L`/`_R` jpg >10KB + non-empty
   `_L`/`_R` `.ocr.txt`; leaves beyond the research window — e.g. 6293's
   141-284, out of the 1742-1748 scope — are NOT holes). A vision-verified
   blank marker inside the `.ocr.txt` counts as a non-empty result. It writes
   `audit_legacy_done` (0 = clean) + `legacy_failures.json`.

   **ON-DEMAND ONLY (user decision 2026-09-16):** the legacy check is NOT part
   of the default audit — St Joris 6290-6293 are CLOSED, so re-checking them on
   every run is noise. Run it explicitly with `python3 sweep_audit.py
   --legacy` when a legacy audit is requested. The cron monitor emits the
   third line `legacy=<clean|failures>` only when the flag file exists (i.e.
   the on-demand audit ran); default completion is `sweep=done AND
   audit13=clean AND sanfelipe=done` (+ `legacy=clean` if present).

**6. Durability:** background processes parented to the gateway PID 1
   (check with `ps -o ppid=`) survive if the chat session closes. `terminal`
   background jobs in the session do NOT — for unattended work the process
   must be gateway-parented (the session's terminal background path handles
   this) and resumable.

**Report for the user (when they check in or next check-in):** current
volume + done count + rough ETA (grounded in measured pages/sec, not the
optimistic first-volume estimate), what's self-waiting, and the
not-digitized parishes (agatha lists a covering volume but `avail=False` =
not digitized to full-res — record as "not digitally accessible", never
silently skip).

## Priority: quality over speed (user's governing rule)

A missed entry costs far more than a few extra OCR pages (10 parallel
jobs ≈ 2-3 min/page). Whenever scope is ambiguous — which pages/blocks/
volumes to read, where a year's block starts or ends — read MORE, not less.
Operational rules:

- **A clean-readable header is a floor, not a boundary.** Read beyond it
  until the next year header is actually found; if a boundary header OCRs
  garbled, extend one more page/leaf (2026-09-15: 6260's 1766 block opens
  on p205_R under a garbled "AN NI 1766" header — stopping at the clean
  p206_L header dropped two real entries, incl. a January baptism the user
  caught on review).
- **Cross-check both directions.** Every index entry needs a register-side
  match AND every register line near the target surname/date (within the
  variant scan) needs an index-side match. A mismatch in EITHER direction
  is DOUBTFUL, never an exclusion.
- **Never stop a variant scan at the first hit page** — scan all pages of
  the target year; the family can appear in several months.
- **Tie-breaker for ambiguous findings: DOUBTFUL beats Excluded.** When
  unsure whether a line is the target, it goes in DOUBTFUL — the human
  reviewing the report must never find a silently dropped candidate.
- **Excluded and DOUBTFUL rows need the full-res IIIF URL too** (verbatim
  from index.json), so the human can verify against the original image
  without re-downloading.
- If completeness vs. time is a real trade-off (large multi-year spans),
  tell the user the cost (page count × ~2-3 min) and let them decide —
  never cut silently.

## Core workflow

### Indexes — check these FIRST (before bisecting a register)
A parish may have a pre-made name **index** (a separate scanned volume that
points at register entries; a typical entry = person's first name + father's
name + year + month + day). If one covers your target year span it is the
fast way to locate a target surname, then jump straight to the register page
(via step 8 anchors) for the full entry — no density/heading bisection of the
whole register.

**DO NOT assume the index's structure — discover it first, or you will miss
information.** Layout varies per volume: usually split by YEAR then names
(alphabetical within the year); sometimes by YEAR/MONTH then names; sometimes
by YEAR with UNSORTED names (roughly chronological). Before searching an index
you have not already mapped, OCR a small spread of pages (the first 3–5
content pages + one mid-volume page) with per-leaf Kraken and determine (a)
the sort key — surname / year / year+month / unsorted, (b) where the
year/month headers sit, (c) the entry layout. **If you assume
alphabetical-by-surname on a year-then-unsorted index (or vice versa) you land
on the wrong pages or skip the target entirely.** Record each volume's
confirmed structure in `lookup/index_volumes.json` (per bookpart: `structure`
+ year-anchor pages) so the next run skips re-discovery. Confirmed so far: OLV
baptism index 6081 (1560–1580) = alphabetical by SURNAME, grouped by year
(year headers, names sorted within year), verified by OCR of p5.

**An index can be MULTI-CYCLE (year-banded) — several A→Z cycles in ONE
volume, and a single A→Z run is NOT the default assumption.** Verified
2026-09-16 (Phase 5, 13 Antwerp baptism-index scans): OLV-Noord (6141, one
physical scan also listed as 6142/6143 under different year labels) showed
letters that DO NOT descend monotonically down the page count — A at p2, D at
p72, C at p142, B at p182 — i.e. the index re-cycles A→Z once per year-band,
so there are ~3 D-sections, not one. A "first D-band probe" sweep finds only
the FIRST cycle and silently misses the rest (exactly the no-miss failure
mode). Detection: OCR a spread of ~8–12 pages across the whole volume; if the
dominant leading-letter per page is NOT non-decreasing, the volume is
multi-cycle. **Decision rule the user set (2026-09-16): multi-cycle volume →
FULL-SCAN every page (approach A, structure-agnostic, no-miss); single
monotonic A→Z run → D-band hunt only (approach B, cheaper).** At 10-way Kraken
a 200-page full scan is ~7 min, so the cost of A is acceptable and it removes
the risk of a missed cycle. Also: a physical scan can be LISTED UNDER MULTIPLE
BOOKPART_IDs with different year-range labels (6141/6142/6143; 6088/6089;
6327/6328; 6189/6190) — DEDUPE by physical scan (same IIIF base) before
sweeping or you OCR the same pages twice. (The 6379 first-volume estimate
"~7 s/page" was download-heavy; later volumes are OCR-bound at ~4–5 s/page —
ground ETAs in the measured rate, not the first volume.)

- **How to search indexes:** same `#PR_FORM`, but check the **Indexs** column
  checkboxes `TYPEINDEX_PR[]` (value 1=baptism/birth, 2=marriage,
  3=funeral/death) INSTEAD OF (or in addition to) the Records column
  `TYPEACTES_PR[]`. Set the parish exactly as in step 2/3 (enable the
  bootstrap-select first — see step 3 caveat), submit, and the results page
  lists the index volumes in the same `tr.row-results` table; capture each
  BOOKPART_ID the same way (hook `window.open`, click the row `<td>`).
- **An index volume is just a IIIF scan:** it opens in the same Mirador viewer,
  has the same `manifest_path` JSON. Cache it with `agatha_cache.py init`,
  download pages with `get`, and read them with per-leaf Kraken small exactly
  like a register (index pages here are single ~3000×2400 landscape pages;
  `split_leaves.py` + `ocr_batch.sh` still apply). Indexes are scanned
  handwriting, NOT digital text — so the open-ended surname variant scan still
  applies (an index does not rescue you from 18th-c. OCR mangles).
- **Read the WHOLE year block, not just the page where the year header
  appears — and check the previous leaf for an earlier/garbled header.** A
  year's entries can span several columns, a surname's entries can be split
  across a leaf boundary, and the header can OCR garbled (6260 p205_R's
  1766 header read "AN NI 1766") so you anchor the block at the WRONG page.
  Verified 2026-09-15 (6260, St-Joris): the 1766 block opens on p205_R, not
  p206_L — the D-section spans p205_R (D'Hert → Demol) through p206_L
  (Dirckx → De Craecker). The Zorrokens entries are SPLIT across that
  boundary: p205_R has "Zorrokens Joannes 9 Januarii 1766" and "Zorrokens
  Franciscus 15 July" (plus a "Zorrokens Petrus" line, date 18/29
  ambiguous); p206_L has "Zorrokens Franciscus 4 Sept, Josephus". Reading
  only p206_L — the page whose header read cleanly "1766" — missed three
  real entries, including the January one. Locate the year's first column by
  scanning for the first year header (OCR-garbled or not, cross-check with
  the alphabetical position of the names), then read every column until the
  NEXT year header, and finish the surname's alphabet range on both sides of
  any leaf/page boundary.
- **Cross-checking an index against the register: match on child's first
  name + father's name + date, NOT on the index's surname spelling.** The
  index and the register can spell the same family a letter apart (verified
  2026-09-15: index 6260 "Zorrokens" p205_R = register 6294 p87_R "jounnit
  [Johannes] Petri Zorropens" Januari 1766 — same entry, one letter
  difference; dismissing the register line as "different family" was wrong
  and dropped a confirmed hit). When an index entry's child-name +
  father-name + date matches a register line, that is a CONFIRMED match even
  if the surname differs by a letter — and conversely, a register line that
  matches an index entry this way must NOT be excluded from the results.
- **Index entry = a pointer.** It gives you the month+day of the act; use it
  to target the register page, then VERIFY the date against the register's own
  heading (standing rule — the index points, the register confirms).
- **Indexes don't exist for every parish/record type.** OLV (PARISH_ID 13) has
  baptism indexes 1560–1624 (BOOKPART 6081=1560-1580, 6083=1581-1601,
  6082=1601-1624) and marriage indexes 1542–1612 (6427=1542-1612, 6428=
  1583-1585) but **NO funeral/death index** — so for OLV deaths you still
  bisect register 6571/6572. Always run the index search for the requested
  record type; if the results are empty, fall back to the register workflow.
- **Search ALL indexes covering the period — a parish can have several for
  the same record type, and they do NOT contain the same information.**
  Verified 2026-09-15 (Sint-Joris baptisms): 14 index volumes total, and the
  year 1766 alone is covered by 6260 (1700–1776) AND 6262 (1700–1784) —
  two different compilations (different page counts, different content;
  searching only 6260 missed entries that exist only in 6262: the 1766
  Zorokens block — Anna 24 martii, Joanna 18 maij, Maria 6 julii — appears
  only in 6262 p198_R). Enumerate the FULL result list, pick EVERY volume
  whose span contains the target year, and search each one
  (structure-discovery first if unmapped). Skipping one of several covering
  indexes = silently missing information.
- **Same rule for base records (Registers column): a parish can have MULTIPLE
  documents for the same record type, and the results table is paginated for
  them too.** A period like "1760-1790" may be served by several volumes with
  overlapping or adjacent spans — enumerate the FULL result list (check the
  "N of M results" line, page through or set 25/50 per page), then work
  EVERY volume whose span contains the target month, not just the first
  match. The same "different compilations, different content" trap as with
  indexes applies: two volumes covering the same years can carry different
  entries.
- **The results table is PAGINATED (default 10/page) — "1-10 of 14 results"
  means 4 are hidden.** Before trusting an enumeration, check the "N of M
  results" line; if M > 10, either set 25/50 per page or click through all
  pages (pagination anchors `<a>` with text "1","2",… in the footer nav).
  Capture BOOKPART_IDs from every page (hook `gotoClick` to record without
  navigating, click each row's View).
- Persist any newly discovered index volumes to
  `/workspace/agatha/lookup/index_volumes.json` (parish → record-type →
  [{bookpart, span, label, **structure**}]), so the next run checks them
  without re-searching — and without re-rediscovering the structure. A
  `structure` field is mandatory: an index with no recorded structure must be
  structure-mapped (OCR a page sample) before it is searched.

0. **Check the local volume registry FIRST (before any login/site work).**
   Every cached volume has `meta.json` at
   `/workspace/agatha/cache/volumes/<bookpart_id>/meta.json` carrying
   `parish_name`, `record_type`, `date_range` and — after the first visit —
   a `page_year_map` of verified page→year anchors (see step 8). If the
   requested parish + record type + year span falls inside a cached
   volume's `date_range`, skip steps 1–4 entirely and jump to step 5/8.
   `ls /workspace/agatha/cache/volumes/` shows what's on hand;
   `python3 agatha_cache.py list <id>` prints title, range, cached pages.
   Only when the target volume is NOT cached do steps 1–4 (login, ajax.php
   ID resolution, form submit, BOOKPART_ID capture) — the search form is
   the universal way to find *any* parish's volume list: submit with just
   the parish + record type (no period) and the results page lists every
   volume with its year span; hook `window.open` then click a row's `<td>`
   to capture its BOOKPART_ID.
1. **Log in** on the search page. The Login link is hidden inside the
   collapsed mobile navbar — toggle the hamburger menu first, then the modal
   opens. Fill `#username`/`#password` with `fill_input` (real keystrokes),
   click Login. Verify: header shows "<AGATHA_USER>" with Profile / Close session, and
   `document.cookie` contains a `PHPSESSID`. Accept the cookie-consent banner
   if present. (The reCAPTCHA iframe on the viewer is decorative — ignore.)
2. **Resolve IDs via ajax.php, not the UI autocomplete.** The municipality and
   parish fields are jQuery UI autocompletes that do NOT respond to synthetic
   `.val().trigger('input')`. POST directly instead:
   - `method=getMunicipalities&term=<text>&type=PR`
   - `method=getParishFromMunicipality&PLACEPOINT_ID=<id>`
   - `method=getPlaces&term=<text>`
   All to `/en/search/genealogie/ajax.php` with `Referer` + `PHPSESSID` header;
   responses are JSON with `PLACEPOINT_ID` / `PARISH_ID` / `CURRENT_NAME`.
   Known: Antwerpen municipality PLACEPOINT_ID=12; Antwerpen OLV PARISH_ID=13;
   Antwerpen Sint-Joris PARISH_ID=20 (baptisms 1760-1774 = BOOKPART 6294).
   Persist every newly resolved ID to /workspace/agatha/lookup/parishes.json
   immediately (browser_exec Python vars do not persist across calls).
3. **Submit the search form** `#PR_FORM` (POST to
   `/en/search/genealogie/results/`): hidden `PLACEPOINT_ID_PR`,
   `CURRENT_NAME_PR`, parish select, record-type checkbox `TYPEACTES_PR[]`
   (1=baptisms, 2=marriages, 3=deaths), period optional. **The requested year
   range is only a filter — pick the volume whose actual span contains the
   requested month** (e.g. January 1732 lives in the 1732-1774 volume, not a
   1775-1793 request). Submit with just parish + record type if unsure.
4. **Get the BOOKPART_ID.** On the results page the row click calls
   `gotoClick(BOOKPART_ID)` → `window.open('/en/search/genealogie/<id>')`.
   A plain `.click()` navigates nowhere: hook `window.open` first
   (`window.open=(u)=>{captured.push(u);return null;}`), then click the row.
   (Known: OLV deaths 1732-1774 = 6571, 1775-1792 = 6572; Sint-Joris baptisms
   1760-1774 = 6294.)
5. **Check the page-image cache FIRST (data is immutable — never re-download
   a page you already have).** All extracted images live under
   `/workspace/agatha/cache/` (see `cache/README.md`): `volumes/<bookpart_id>/`
   holds `index.json` (per-page full-res URLs), `manifest.json`, `meta.json`
   (title + date range), `pages/NNN.jpg`; crops in `crops/<bookpart_id>/`.
   Use the helper `python3 /workspace/agatha/agatha_cache.py`:
   - `list <id>` — which pages are cached for a volume
   - `get <id> <page>` — cache-first page fetch (downloads only if missing;
     **auto-refreshes the session cookie itself** — it calls `ensure` first,
     so a stale/expired session re-logs-in automatically, no manual step)
   - `crop <id> <page> <x,y,w,h> <name>` — cached crop (auto-uses
     /workspace/.venv for PIL)
   - `init <id> <manifest_url> <cookie> <title> <range> <parish_id>` — register
     a new volume after finding its manifest
   - `du` — disk usage by category (pages / metadata / crops / lookup)
   - `clean [id]` — drop crops only (all volumes or one); full-res pages,
     index and meta are never touched (crops re-derive from pages). Run this
     if the cache grows large: pages are the precious, immutable part.
   - `ensure` — auto-refresh: check the saved session (200 on /en/profil/ =
     valid); on stale re-seeds + re-authenticates and saves a fresh PHPSESSID.
     `check` (diagnostic) and `login` (force fresh) also available.
     **Run `ensure` first thing in any agatha session; `get`/`init` already
     call it, so it's usually invisible.**
   Every new download MUST land in the cache (the helper does this); never use
   scratch dirs. Also check `lookup/parishes.json` + `municipalities.json`
   before re-querying ajax.php for known parishes. Known seeds (all registered,
   with verified date maps): volume 6571 (Antwerpen OLV deaths
   1732-1774, 188 pages, FINAL page p188 = Nov 1774) and 6572 (Antwerpen OLV
   1775-1792, 96 pages, all of 1775 on p2–7, p8 starts Jan 1776) and 6294
   (Antwerpen Sint-Joris baptisms 1760-1774, 234 pages, PARISH_ID 20, verified
   per-leaf page_month_map covering p65-p125 — see meta.json).
   `/workspace/agatha/lookup/` holds `parishes.json` + `municipalities.json`
   (Antwerpen=12, OLV=13, Sint-Joris=20): persist every newly resolved ID there
   IMMEDIATELY after discovery — this session's Sint-Joris resolution was lost
   when the dir was never created.
   **Session cookie:** it's a PHP *session* cookie (no Expires/Max-Age) — no
   fixed expiry; valid until the server drops it. Verified: images, ajax.php
   and the viewer page all return 200 even with a dead cookie + Referer, so
   a stale cookie is a soft problem — but `ensure` keeps it valid anyway.
6. **Get a fresh volume's manifest** (cache miss on the volume itself): the
   volume page HTML contains `var manifest_path=` pointing at a IIIF
   Presentation 2 JSON. curl it (Referer + cookie) and `init` it. After the
   first visit, record verified page→year anchors in `meta.json`
   `page_year_map` (first register page, a few mid anchors, final page + the
   volume's end year) — that's the only re-search-proof way to target months
   later without re-bisecting the whole volume. For two-column spreads prefer
   a per-leaf `page_month_map` (built during step 9 from the per-leaf OCR
   headings, e.g. vol 6294): it records which month each COLUMN of each page
   starts in, which `page_year_map` cannot express (a spread can straddle two
   months).
7. **Download pages** (cache miss): curl the `full/full/0/default.jpg` URL
   from index.json with `Referer: https://agatha.arch.be/` + `Cookie:` (the
   helper's `get` does exactly this). Full-res images 403 on bare navigation
   and canvas reads are tainted; site thumbnails (150x115) are too small.
   Cached pages are 1600x1247 grayscale JPEG, ~1.1 MB each — they are the input
   to the per-leaf Kraken OCR pipeline (step 9), not input to your vision model.
8. **Locate the target month. The month heading on the page IS the date —
   never extrapolate it.** Check the volume's `meta.json` `page_month_map`
   (per-column, for spreads) / `page_year_map` FIRST — verified anchors (e.g.
   6571: p155=Jan 1766, p188=Nov 1774 final; 6572: p2=Jan 1775, p8=Jan 1776;
   6294: per-leaf map p65-p125) usually land you on the right page directly; if the target is outside the anchored range, use the
   anchors only to pick a *candidate page window* (±a few pages), then **read
   the actual headings by OCR**. Pages 1-2 are often title pages. Register
   pages are two-column spreads and **month headings can appear anywhere on
   the page** (column top, mid-column, margin) — don't assume position.
   **Hard rule learned 2026-09 (vol 6294, St-Joris): assigning a month by
   pages-per-year density and then "confirming" it with the same page's single
   OCR header line is circular and wrong** — the header OCR can be garbled
   (p87 top line read "December 1765" while the real mid-page boundary was
   Januari 1766). Correct method: split the spread into its two leaves
   (`split_leaves.py`), OCR each leaf with Kraken small (headers at leaf tops
   OCR far better in single-leaf mode), and anchor every entry to the nearest
   month heading **above it in the same column**. A leaf may start in one
   month and continue into the next: re-read the mid-leaf header when the
   entry sits below a second heading. Record each verified page→month anchor
   into `meta.json` `page_year_map` as you go so the next run starts from
   verified facts, not density math.
9. **Read the entries with Kraken OCR, per leaf.** The left-margin numerals
   are the DAY OF THE MONTH within each column (they reset at every month
   heading; several entries share a day) — NOT sequential entry numbers; the
   right-margin numerals are monthly tallies. Quote "month + day", never
   "entry number N". The standard pipeline (in
   `/workspace/agatha/`): `split_leaves.py VOL PAGES...` splits each cached
   spread into `NNN_L.jpg` / `NNN_R.jpg` (Kraken handles single pages only —
   one leaf per job), then `ocr_batch.sh VOL PAGES...` OCRs all leaves with
   `small.safetensors` at ≤10 parallel jobs (the Kraken service; see
   `kraken-ocr` skill), writing `NNN_L.ocr.txt` / `NNN_R.ocr.txt`. Expect
   `deceased — street/locality — burial place` for death registers; for
   baptism registers the columns are child / father / mother / godparents.
   Search the `.ocr.txt` files with a generous case-insensitive variant list
   (18th-c. OCR mangles surnames heavily: for ZORROKENS the observed variants
   were Zorrokens, Zorrohens, Zorropens, Zoropens, Zorohens, Zorogens,
   ZoroEens, Zorotens, Zoropent, Zorons, Zorrokeus, Zorohent, Zorr — 2026-09-15:
   the "Zor/Zorok/Zorr" families; keep the list open-ended and re-run the scan
   after every OCR round with any newly observed variant added) — and treat
   near-misses (Zorro, Zors, Zorne, Zoronick, Zorothea, van Zoront) as review
   candidates, never as confirmed hits. **When an entry is a candidate match
   for an index (or another register line), decide by child's first name +
   father's name + date — NEVER by surname spelling.** Verified 2026-09-15:
   register "jounnit Petri Zorropens" (Jan 1766) IS the index's "Zorrokens
   Joannes 9 Januarii" — one letter apart, same entry; excluding it as a
   "different family" dropped a confirmed hit. Run the same variant scan over BOTH
   the full-spread and the per-leaf OCR files; the per-leaf files are the
   authoritative reading (cleaner, columns not interleaved). If a number/name is missing (e.g. no burial that
   day), report that honestly — do not guess. Your own vision model is
   reserved for a single genuinely illegible line after the OCR attempts
   failed — and must be stated as such in the report.
10. **Report** with a gloss of recurring abbreviations: "een kind" = a child
   (burial of a child of the named person); "cathe" = cathedral (Grote Kerk);
   "kerkhof" = churchyard, "kerk" = inside the church; "minderbroers" =
   Minorite/Franciscan; "predikheren" = Premonstratensians. Names/streets are
   best-effort transcriptions of 18th-c. Flemish cursive — flag illegible or
   crossed-out lines as such.

## Pitfalls
- **Do not read manuscript pages with your own vision model.** The Kraken
  small model is trained on this hand and is the reading tool; vision is a
  last-resort single-line tie-breaker only, and using it on a contact sheet of
  many pages is wrong (it doesn't work at that scale — the user has flagged
  this explicitly).
- `web_extract` is unavailable in this deployment (SearXNG search-only
  backend) — use curl with Referer + session cookie or browser_exec.
- Login link hidden until the hamburger menu is expanded; a missed click
  opens nothing and can double-toggle the modal closed.
- The parish bootstrap-select is disabled until a municipality is selected —
  if `PARISH_ID[]` is missing from the POST, the select is still disabled (you
  set the hidden `PLACEPOINT_ID_PR` but never enabled the `<select>`/its
  `.dropdown` wrapper + toggle button). Enable all three before it submits.
- **Index search:** the Indexs column uses `TYPEINDEX_PR[]` (1/2/3) — a
  different field than the Records column `TYPEACTES_PR[]`. Searching with
  only `TYPEACTES_PR[]` checked returns the register volumes, not the index
  volumes, so an "no results" for a known record type can mean you checked
  the wrong column.
- **Index results are paginated (10/page).** "1-10 of 14 results" hides the
  last 4 volumes. Always read the "N of M results" line and page through (or
  bump to 25/50/page) before concluding you have the full list. The parish
  select and the municipality autocomplete are the two fields that must be
  set correctly or the search silently narrows.
- Manifest fetch and image fetch both 403 without `Referer: https://agatha.arch.be/`
  (manifest: `https://agatha.arch.be/`; image: same). Cookies from the
  logged-in browser session are required; grab via `js("document.cookie")`.
- Blank results page = cookie banner overlay or parish not actually selected
  (check the select's value).
- Entry numbers skip or continue across pages — never assume "entries 15-21"
  sit on one page.
- **Full-res image URLs are offset by an arbitrary amount vs the
  canvas/page number, and the offset varies per volume:** the IIIF canvas
  "p. N" does NOT reliably map to image file `..._0_N_r.jp2` (observed 2026-09-15:
  6294 canvas 87 → `_0086_r`; 6262 canvas 198 → `_0199_r`; 6260 canvas 205 →
  `_0205_r` — three different offsets in three volumes). Always quote the
  `full_res_url` from the cached `index.json` verbatim; never hand-build it
  from the page number.

## Verification
- Logged in: header shows the username + PHPSESSID in cookies.
- Search works: results page lists volume rows with year ranges.
- Download works: `file page_N.jpg` reports a valid JPEG ~300KB-1MB.
- A month is only "verified" when it was read from the page's own heading via
  OCR (ideally per-leaf) and the entry is positioned relative to that heading
  — never from pages-per-year arithmetic. When in doubt, flag the date as
  doubtful in the report rather than guessing.
- Before answering: every requested entry number is either transcribed or
  explicitly reported as missing/illegible — count them, don't eyeball.
