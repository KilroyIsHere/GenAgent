# AGATHA detailed runbook

Written after a real run (Antwerpen / Onze-Lieve-Vrouw, death registers,
January 1732, entries 15-21). Follow top-to-bottom; every ID and URL here
was verified live.

## Page-image cache (check FIRST — data is immutable)

Agatha data never changes (historical registers). Once a page image is in the
cache, never re-download it — full-res extractions are costly on the archive's
side. Cache root: `/workspace/agatha/cache/` (protocol in `cache/README.md`).

Layout:
```
/workspace/agatha/cache/
  volumes/<bookpart_id>/
    manifest.json   raw IIIF manifest
    index.json      [{page, label, full_res_url, jp2_service}, ...] (1-based)
    meta.json       {bookpart_id, parish_id, municipality_id, title, date_range,
                     volume_url, manifest_url, n_pages}
    pages/NNN.jpg   full-res page image, NNN zero-padded 3 (1600x1247 gray, ~1.1MB)
  crops/<bookpart_id>/NNN_<name>.png   derived crops (also cached)
  lookup/parishes.json, municipalities.json   known IDs (check before ajax.php)
  session_cookie.txt   "PHPSESSID=...; cookieconsent_status=dismiss"
```

Helper (all commands verified): `python3 /workspace/agatha/agatha_cache.py`
- `list <id>`            → cached page numbers for a volume
- `get <id> <page>`      → CACHE-FIRST: prints "CACHE HIT" if present, else
  downloads from index.json with Referer+cookie (needs session_cookie.txt)
- `crop <id> <page> <x,y,w,h> <name>` → PIL crop saved to crops/<id>/
  (auto re-execs under /workspace/.venv/bin/python for PIL)
- `init <id> <manifest_url> <cookie> <title> <range> <parish_id>`
  → registers a NEW volume: curls the manifest, builds index.json + meta.json
- `du`                   → disk usage: full-res pages / metadata / crops / lookup
- `clean [id]`           → deletes crops only (all volumes, or one); full-res
  pages, index and meta are NEVER touched — crops can always be re-derived.
  Run it if the cache grows large: pages are the precious, immutable part.
- `ensure`               → AUTO-REFRESH: checks the saved session (HTTP 200
  on /en/profil/ = valid); on stale/missing it re-seeds a session +
  re-authenticates via POST /library/login.php and saves a fresh PHPSESSID to
  session_cookie.txt. `check` (diagnostic only) and `login` (force fresh)
  are also available. `get` and `init` call `ensure` first, so a run
  self-heals with no manual re-login.

Protocol rules:
1. Before ANY curl to agatha for an image, run `get` (or check the file
   exists). If cached, use it.
2. Session cookie: `ensure` manages it (auto-re-logins on stale). You usually
   never save it by hand. If a browser login is done anyway, mirror it:
   `echo 'PHPSESSID=...; cookieconsent_status=dismiss' > cache/session_cookie.txt`.
   (Cookies expire server-side — but see the cookie-lifetime note below.)
3. New volume → `init` it, then `get` pages. Every download lands in the
   cache automatically; never write page images to scratch dirs.
4. Crops are derived: name them descriptively (e.g. `002_entries_15_21`);
   keep the source page as the evidence of record.
5. meta.json's date_range is how future runs pick the right volume by date.

### Cookie lifetime (verified 2026-09-14 — saves you a lot of guessing)
- `PHPSESSID` is a **session cookie**: `Set-Cookie` has NO `Expires`/`Max-Age`,
  so there is no fixed expiry — it's valid until the server drops the session
  (server-side idle/TTL, unknown to the client).
- **The cookie is not actually required for the page workflow.** Verified with
  a dead cookie + `Referer`: i3f full-res images (200), ajax.php (200) and the
  volume/viewer page (200) all work. The cookie only gates the logged-in
  header (<AGATHA_USER> vs Login) and /en/profil/. So a stale cookie is a soft problem.
- `ensure` capability check: `GET /en/profil/` → 200 = valid, else stale.
- Hand-rolled login (what `ensure` does internally):
  ```
  # 1) seed a session
  curl -s -c jar.txt -o /dev/null -A "$UA" \
       -H 'Referer: https://agatha.arch.be/' \
       https://agatha.arch.be/en/search/genealogie/
  # 2) authenticate (body '1' = success)
  curl -s -b jar.txt -c jar.txt -X POST \
       -H 'Origin: https://agatha.arch.be' \
       -H 'Referer: https://agatha.arch.be/en/search/genealogie/' \
       -H 'Content-Type: application/x-www-form-urlencoded' \
       --data 'username=<AGATHA_USER>&password=<AGATHA_PASSWORD>&app=/en/search/genealogie' \
       https://agatha.arch.be/library/login.php
  # 3) save: PHPSESSID=<value> > cache/session_cookie.txt
  ```

Seeded (2026-09-14): volume 6571 = Antwerpen OLV deaths 1732-1774, 188 pages,
pages 1-9 cached. January 1732 = page 2 left leaf. Crops cleared via `clean`;
re-derive with `crop` (pages are the evidence of record).

## Login flow details
- URL: https://agatha.arch.be/en/search/genealogie/
- Toggle the mobile hamburger menu FIRST — the "Login" link is inside the
  collapsed navbar and not clickable/visible otherwise. A stray double-click
  can open then immediately close the modal; if the modal won't open, check
  the header (it may have logged you in) or re-toggle the hamburger.
- Fill `#username`, `#password` with `fill_input` (CDP real keystrokes),
  click the Login button in the modal.
- Verify: header changes from "Login" to "<AGATHA_USER>" (Profile / Close session);
  `document.cookie` has `PHPSESSID`.
- Google reCAPTCHA anchor iframe present on the viewer: decorative, never
  blocked anything in practice.
- Accept the cookie-consent banner if it overlays content (it makes the
  results page appear blank).

## Search form mechanics
- Two tabbed forms on the main page: parish (PR) and civil (CS). Church
  registers = PR. Form: `#PR_FORM`, POST to `/en/search/genealogie/results/`.
- `#PLACE_PR` (municipality) and the parish modal's `#parish` are jQuery UI
  autocompletes backed by `/en/search/genealogie/ajax.php` (POST, JSON
  responses). Selecting an item populates hidden fields `PLACEPOINT_ID_PR`,
  `CURRENT_NAME_PR` and populates the `#PARISH_SELECT` bootstrap-select via
  `refreshParishSelect()`.
- Synthetic `.val(x).trigger('input')` does NOT drive the autocomplete.
  Reliable route: call ajax.php directly to get the exact IDs, then set the
  hidden inputs + select in JS and submit the form (or drive the real select
  event). `fill_input` works for the autocomplete text fields when needed.

### Direct ajax.php lookups (curl)
```
curl -s -H "Referer: https://agatha.arch.be/en/search/genealogie/" \
     -H "Cookie: PHPSESSID=<from browser>" \
     -X POST "https://agatha.arch.be/en/search/genealogie/ajax.php" \
     -d "method=getMunicipalities&term=Antwerpen&type=PR"
```
Returns JSON list with `PLACEPOINT_ID`, `CURRENT_NAME`. Same pattern:
- `method=getParishFromMunicipality&PLACEPOINT_ID=<id>` → PARISH_ID + parish names
- `method=getPlaces&term=<text>` → place/parish autocomplete (used inside the parish modal)

### Known IDs (verified)
- Antwerpen (municipality): PLACEPOINT_ID = 12
- Antwerpen: Onze-Lieve-Vrouw (parish): PARISH_ID = 13, PLACEPOINT_ID = 12
- Antwerpen: Sint-Joris (parish): PARISH_ID = 20
- Antwerpen OLV death volume 1732-1774: BOOKPART_ID = 6571
  (URL https://agatha.arch.be/en/search/genealogie/6571)
- Antwerpen OLV death volume 1775-1792: BOOKPART_ID = 6572
- Antwerpen Sint-Joris baptism volume 1760-1774: BOOKPART_ID = 6294
  (URL https://agatha.arch.be/en/search/genealogie/6294, COL=511, DOC=511_9000_000, SFX=_00152_000)
- These also live in `/workspace/agatha/cache/lookup/parishes.json` — persist
  every newly resolved ID there immediately; it is the first place to check
  before any ajax.php call.

### Record types
Checkboxes `#TYPEACTES_N_PR`, name `TYPEACTES_PR[]`:
- 1 = baptisms/births, 2 = marriages, 3 = funerals/deaths.
- Free-select `#EDITORIALFORM_PR` for non-standard record types.

### Period
- `#CHOOSE_DATE_PERIODE_PR` select: 1=From, 2=Before, 3=After (other codes exist).
- `#SHOW_PERIODE_PR` = year(s); `#exactYear_PR` = exact year.
- The requested range is only a filter: volumes are fixed historical registers
  (e.g. "1732-1774" is ONE volume). If the user asks for January 1732 but says
  "1775 to 1793", the right volume is the one that STARTS in 1732. Safest:
  submit parish + record type only, then pick the volume from results.

### Submitting / results
- Submit `#PR_FORM` with a real submit click. Results land on
  `/en/search/genealogie/results/...` as a table of volumes (label = parish +
  year range, plus a "View" cell).
- Row click calls `gotoClick(BOOKPART_ID)` →
  `window.open('/en/search/genealogie/<BOOKPART_ID>')`. A plain `.click()`
  navigates nowhere. Hook first: `window.open=(u)=>{captured.push(u);return
  null;}` (in js), then click the row `<td>`. Or read the `results` array in
  page JS for BOOKPART_IDs.

## Viewer / IIIF details
- `/en/search/genealogie/<BOOKPART_ID>` renders a Mirador IIIF viewer
  (iframe `https://agatha.arch.be/viewer`, cross-origin).
- The volume page HTML embeds:
  `var manifest_path = "https://agatha.arch.be/en/data/json/<COL>/<COL>_<DOC>/<COL>_<DOC>_<SFX>/<COL>_<DOC>_<SFX>.json";`
  (Antwerpen OLV death volume: COL=511, DOC=511_9000_000, SFX=_00281_000.)
- Manifest = IIIF Presentation 2. Canvas `label` = "p. N" (NO dates), with a
  `rendering` link:
  `https://i3f.arch.be/iiif/<COL>/<COL>_<DOC>/<COL>_<DOC>_<SFX>/<COL>_<DOC>_<SFX>_0_<NNNN>_r.jp2/full/full/0/default.jpg`
- **Full-res download (the key trick):**
  `curl -s -o page_N.jpg -H "Referer: https://agatha.arch.be/" -H "Cookie: PHPSESSID=..." "https://i3f.arch.be/iiif/.../full/full/0/default.jpg"`
  Verified: ≈500KB JPEG, ~3000x2299. Bare top-level navigation to the image
  URL 403s; canvas drawImage is tainted (cross-origin). So curl+Referer is
  the reliable path. Fetching the manifest from a plain browser tab also 403s;
  curl with the session cookie works.
- Site thumbnails at `https://agatha.arch.be/data/thumbnails/...` are tiny
  (150x115 / 640x360) — not readable.

### Locating the target month
- Canvas labels are dateless. Page 1 is often a title page (the death volume
  starts "Mortuarum partes Januari 1732 ad 30 Nov 1774").
- Pages are two-column spreads; month headings can appear ANYWHERE on a page
  (top of a column, mid-column, margin).
- **Never extrapolate months from pages-per-year density, and never "verify" a
  guess by reading the same page's single garbled OCR header line** — that was
  circular and produced a wrong date (vol 6294 p87: top line OCR'd "December
  1765" while the entry actually sat under a Januari 1766 column heading).
- Correct method: check `meta.json` `page_month_map`/`page_year_map` first;
  otherwise pick a ±few-page candidate window, then split each spread into
  leaves (`/workspace/agatha/split_leaves.py VOL PAGES...`) and OCR each leaf
  with Kraken small (`ocr_batch.sh`); leaf-top headings OCR cleanly per column.
  Anchor every entry to the nearest month heading ABOVE it in the SAME column;
  a leaf can straddle two months (mid-leaf heading). Record each verified
  anchor back into `meta.json`.
- January of the volume's first year is within the first 2-4 entry pages.
  Mid-volume: use the candidate window, not blind bisection over vision reads.
- In the real run: page 1 = title page; the open spread on page 2 contained
  the "Januarij 1732" heading (left leaf) with entries 1-31 in a two-column
  layout.

### Reading 18th-c. Flemish cursive
- **Reading tool: the Kraken OCR service, per leaf** (`small.safetensors` is
  trained on this cursive Dutch/Latin hand). Pipeline: `split_leaves.py`
  (spreads → `NNN_L.jpg`/`NNN_R.jpg`, because Kraken handles single pages) →
  `ocr_batch.sh` (≤10 parallel jobs) → `NNN_L.ocr.txt`/`NNN_R.ocr.txt`.
  Do NOT read pages with the agent's own vision model (full pages, batches,
  contact sheets): it was ruled out by the user and does not work at that
  scale. Vision is a last-resort tie-breaker for ONE specific illegible line
  after per-leaf OCR failed, and must be flagged as low-confidence in the report.
- Full-spread OCR is fine as a coarse pass but interleaves the two columns by
  line number — never use its line numbers to position entries relative to
  headings; the per-leaf files are the authoritative reading.
- Expect for deaths: `deceased — street/locality — burial place`; for
  baptisms: child / father / mother / godparents.
- Abbreviations: "een kind" = a child (burial of a child of the named
  person); "cathe" = cathedral (Grote Kerk); "kerkhof" = churchyard, "kerk"
  = inside the church; "minderbroers" = Minorite/Franciscan house;
  "predikheren" = Premonstratensian (Preachers') house.
- Left-margin numerals = day of the month (reset at each heading; several
  entries share a day); right-margin numerals = monthly tallies. Quote
  month+day, never "entry number N".
- Names: search with a generous case-insensitive variant list and treat
  near-misses as review candidates, not hits (see SKILL.md step 9 for the
  observed ZORROKENS family and near-misses).

## Environment/tooling notes
- `web_extract` unavailable in this deployment (SearXNG search-only backend).
- browser_exec: browser state (cookies, tabs) persists across calls; Python
  variables do NOT — persist IDs/URLs to a file in $BH_AGENT_WORKSPACE.
- Grab the session cookie via `js("document.cookie")` and reuse in curl.
- PIL: system python3 has no PIL; use the existing `/workspace/.venv` (has
  pillow; used by `split_leaves.py`) or `uv venv` + `uv pip install pillow`.
  Cropping is for the rare single-line vision tie-breaker only — the reading
  path is per-leaf Kraken OCR.
- `fill_input(selector, text)` = real CDP keystrokes (needed for autocompletes);
  `js("...val(...)")` does not trigger the autocomplete widgets.

## Minimal recipe (copy-paste)
1. CACHE FIRST: `python3 /workspace/agatha/agatha_cache.py list <id>` — if the
   volume + needed pages are cached, jump to step 8 (no site traffic at all).
   Check `lookup/parishes.json` for known parish IDs.
2. Otherwise log in (flow above). Save cookie:
   `echo '<document.cookie PHPSESSID+consent>' > cache/session_cookie.txt`
3. ajax.php getMunicipalities → municipality PLACEPOINT_ID.
4. ajax.php getParishFromMunicipality → parish PARISH_ID (+ name).
5. Fill #PR_FORM (hidden PLACEPOINT_ID_PR / CURRENT_NAME_PR, parish select,
   TYPEACTES_PR[] checkbox, period optional). Submit.
6. Results: hook window.open, click volume row → BOOKPART_ID.
7. Open https://agatha.arch.be/en/search/genealogie/<BOOKPART_ID>; read
   manifest_path from page HTML. If the volume is unknown, register it once:
   `agatha_cache.py init <id> <manifest_url> <cookie> "<title>" "<range>" <parish_id>`
8. `agatha_cache.py get <id> <page>` for each needed page (cache-first).
9. `split_leaves.py <id> <pages...>` + `ocr_batch.sh <id> <pages...>` →
   per-leaf Kraken small OCR in the cache (the reading step; vision is a
   last-resort single-line tie-breaker only).
10. Read month+day from the per-leaf OCR (anchor each entry to the heading
    above it in the same column); transcribe; flag illegible lines; report
    with glossed abbreviations, per-finding URL + page + cache-file refs, and
    honest confidence notes (doubtful items clearly marked for review).
