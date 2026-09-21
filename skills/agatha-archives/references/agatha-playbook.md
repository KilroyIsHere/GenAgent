# AGATHA verified playbook (from a real run: Antwerpen OLV deaths, Jan 1732)

Everything below was verified working in a live session. Read before the first run.

## Account

- Login: user `<AGATHA_USER>`, password `<AGATHA_PASSWORD>` (user-provided; do not ask again).
- Flow: `https://agatha.arch.be/en/search/genealogie/` → toggle the mobile
  hamburger (the Login link is inside the collapsed navbar and not clickable
  otherwise) → Login modal → `fill_input` on `#username` / `#password` (real
  keystrokes required) → click Login.
- Verify: header shows "<AGATHA_USER>" with Profile/Close session; `PHPSESSID` cookie set.
- Accept the cookie-consent banner if it covers the page.
- reCAPTCHA anchor iframes appear on the viewer; decorative, never blocked anything.

## Search form (main page)

- Two tabbed forms: parish `#PR_FORM` and civil `#CS_FORM`; both POST to
  `/en/search/genealogie/results/`. Church registers → PR.
- Municipality field `#PLACE_PR` and parish-modal field `#parish` are jQuery UI
  autocompletes backed by `POST /en/search/genealogie/ajax.php`.
  Synthetic `.val(x).trigger('input')` does NOT drive them. Two reliable routes:
  (a) call ajax.php directly (below) for the IDs, then set hidden fields in JS and submit;
  (b) `fill_input` real keystrokes and pick from the dropdown.

### ajax.php methods (curl with Referer + PHPSESSID works)

```bash
curl -s -H "Referer: https://agatha.arch.be/en/search/genealogie/" \
     -H "Cookie: PHPSESSID=<session>" \
     -X POST "https://agatha.arch.be/en/search/genealogie/ajax.php" \
     -d "method=getMunicipalities&term=Antwerpen&type=PR"          # municipality list (PLACEPOINT_ID, CURRENT_NAME)
     # method=getParishFromMunicipality&PLACEPOINT_ID=<id>         # parish list (PARISH_ID, names)
     # method=getPlaces&term=<text>                                 # parish modal search
```

Selecting a municipality populates `#PLACEPOINT_ID_PR`, `#CURRENT_NAME_PR`, and
`refreshParishSelect(resJSON)` fills the `#PARISH_SELECT` bootstrap-select (which
is disabled until a municipality is chosen).

### Form fields

- Record-type checkboxes `#TYPEACTES_N_PR`, name `TYPEACTES_PR[]`: 1=baptisms/births,
  2=marriages, 3=funerals/deaths. Custom `#EDITORIALFORM_PR` (value `TYPEACTES_OTHER_PR[]`)
  for special record types (status animarum, memory masses, ...).
- Period: `#CHOOSE_DATE_PERIODE_PR` select (1=From, 2=Before, 3=After, 12=...),
  `#SHOW_PERIODE_PR` = year(s), `#exactYear_PR` = exact year.
- CRITICAL: the requested year range is only a filter. Volumes are fixed registers
  (e.g. "1732-1774" is ONE volume). If the user asks for January 1732 within a
  "1775-1793" request, the right volume is the one starting 1732. Submit with just
  parish + record type and pick the right volume from results.

### Known IDs (verified)

- Antwerpen (municipality): PLACEPOINT_ID = 12
- Antwerpen: Onze-Lieve-Vrouw (parish): PARISH_ID = 13
- Antwerpen: Sint-Joris (parish): PARISH_ID = 20
- OLV death volume 1732-1774: BOOKPART_ID = 6571 → `https://agatha.arch.be/en/search/genealogie/6571`
- OLV death volume 1775-1792: BOOKPART_ID = 6572 (manifest suffix _00282_000; COL=511, DOC=511_9000_000)
- Sint-Joris baptism volume 1760-1774: BOOKPART_ID = 6294 (manifest suffix _00152_000; COL=511, DOC=511_9000_000)
- All OLV death volumes (verified 2026-09-14): 1568-1593, 1680-1692, 1692-1701,
  1702-1711, 1712-1731, 1732-1774 (=6571), 1775-1792 (=6572)
- Persist every newly resolved parish/municipality ID to
  `/workspace/agatha/cache/lookup/parishes.json` / `municipalities.json`
  IMMEDIATELY after discovery (this deployment; check there before any
  ajax.php re-query).

### Results page

- Table of volumes; row cells (each `<td>`, NOT the `<tr>`) have a jQuery click
  handler that calls `gotoClick(BOOKPART_ID)` →
  `window.open('/en/search/genealogie/<BOOKPART_ID>')`.
- To capture BOOKPART_IDs (e.g. to list ALL volumes for a parish+record type,
  needed when a requested year range spans two volumes): drive the real form in
  browser_exec — set `#PLACEPOINT_ID_PR`/`#CURRENT_NAME_PR`, enable + set the
  parish option in `#PARISH_SELECT`, check `#TYPEACTES_3_PR`, click the submit
  button — then on the results page:
  ```js
  window.__got = [];
  window.gotoClick = (id) => { window.__got.push(id); return true; };
  const row = [...document.querySelectorAll('#table_body tr')].find(t => t.innerText.includes('1775'));
  [...row.querySelectorAll('td')].forEach(td => jQuery(td).trigger('click'));
  // window.__got now holds the BOOKPART_ID
  ```
  The handler is bound per `<td>`: `tr.click()`, `jQuery(tr).trigger('click')`, and
  native MouseEvents all do nothing. Each td fires the handler once (captured once
  per td — dedupe).
- ajax.php `method=filterResults` (params: ta/tao/ti/tio = editorialform arrays,
  y, y2, yt, pub, p=parish id, pp=placepoint id) only returns a new results URL —
  the volume list itself loads via paginationjs POSTing `method=getResults` to
  ajax.php, which does not resolve from plain curl. Use the browser-driven route above.
- Multi-year range spanning two volumes: find both boundary volumes, then register
  the new one: fetch `https://agatha.arch.be/en/search/genealogie/<id>` in the
  browser, read `var manifest_path = "..."` from the page HTML, and `init` it into
  the page-image cache (see cache section). Example: a 1766-1775 request needs
  both 6571 (ends 1774-11-30) and 6572 (starts 1775-01-01).
- Blank results page → parish not actually selected, or cookie banner overlay.

## Viewer / IIIF (reading pages)

- `/en/search/genealogie/<BOOKPART_ID>` renders a Mirador IIIF viewer in iframe
  `https://agatha.arch.be/viewer`. Canvases = physical pages, labeled "p. N" only — NO dates.
- The viewer page HTML embeds:
  `var manifest_path = "https://agatha.arch.be/en/data/json/<COL>/<COL>_<DOC>/<COL>_<DOC>_00281_000/<COL>_<DOC>_00281_000.json";`
  (Antwerpen OLV deaths: COL=511, DOC=511_9000_000, suffix _00281_000.)
- Fetch the manifest JSON (IIIF Presentation 2) with curl + Referer + PHPSESSID.
  A plain browser-tab navigation to it 403s; curl with cookies works.
- Each canvas: `label: "p. N"` + a `rendering` link to the full-res image:
  `https://i3f.arch.be/iiif/<COL>/<COL>_<DOC>/<COL>_<DOC>_00281_000/<COL>_<DOC>_00281_000_0_<NNNN>_r.jp2/full/full/0/default.jpg`

### Full-res download (the key trick)

```bash
curl -s -o page_N.jpg \
  -H "Referer: https://agatha.arch.be/" \
  -H "Cookie: PHPSESSID=<session>" \
  "https://i3f.arch.be/iiif/.../full/full/0/default.jpg"
```

Verified: ~500KB JPEG, native 2000x1676. Why the alternatives fail:
- Top-level browser navigation to the image URL → 403 (session/origin check).
- canvas.drawImage in the viewer → tainted canvas (cross-origin i3f.arch.be), unreadable.
- `agatha.arch.be/data/thumbnails/...` → only 150x115 / 640x360, too small for cursive.

### Locating the target month

- Canvas 1 is often a title page (e.g. "Mortuarum partes Januari 1732 ad 30 Nov 1774");
  entries start on the next pages.
- Register pages are often two-column spreads; the month heading can appear ANYWHERE
  on a page (top of a column, mid-column, margin). Do not assume position.
- **Never date by pages-per-year density**, and never "confirm" a guessed month by
  reading the same page's single OCR header line — the header OCR can be garbled,
  which makes this circular. Real incident (2026-09-15, vol 6294 p87): the top line
  OCR'd "December 1765" while the entry actually sat under a Januari 1766 column
  heading, and the report shipped the wrong month.
- Method: check `meta.json` `page_month_map`/`page_year_map` (verified anchors)
  first; otherwise pick a candidate window of ±a few pages, split those spreads
  into leaves (`/workspace/agatha/split_leaves.py VOL PAGES...`), OCR each leaf
  with Kraken small (`/workspace/agatha/ocr_batch.sh`, ≤10 parallel). Leaf-top
  headings OCR cleanly per column; anchor every entry to the nearest heading
  ABOVE it in the SAME column (a leaf can straddle two months). Record each
  verified anchor back into `meta.json` as you go.
- January of a volume's first year is within the first 2-4 pages. Mid-volume
  months: candidate window from the anchors, then per-leaf OCR — not blind
  bisection.

### Volume boundary / year mapping (multi-year searches, verified 2026-09-14)

- To find which pages a given year occupies mid-volume: use the verified
  `meta.json` anchors to pick a candidate window, then per-leaf OCR the window
  and read the leaf-top month/year headings. OLV deaths run ~4.25 spreads per
  year (≈188 pages over 1732-1774) — density figures are OK for picking a
  window, NEVER for assigning a date to an entry.
- YEAR digits in this cursive are OCR-fragile (a year can come back as "1744"
  or "1769" for a 1774/1767 heading); the month NAME and the day numerals are
  reliable. Resolve the year from sequence + `meta.json` date_range, and confirm
  the volume end via its last page: closing prayer "Pie Jesu Domine / Dona eis
  Requiem sempiternam" + monthly tally + "in toto N" grand total.
- Hand-written folio numbers in the page corners are ALSO unreliable. Do not use
  them for the page→date map — use month headings.
- New volume start: page 2 (after the blank/title spread) carries the first
  month heading (e.g. "Ia Januarij 1775" on 6572 p2); the volume's first year
  ends a few pages later (6572 p8 = Jan 1776, so 1775 = p2-p7).

### Wide-range name search (e.g. "find ZORROKENS, 1766-1775", verified workflow 2026-09-15)

- Build the page map as above (first/last page of the range per volume).
- Bulk-download every page in range: `for p in $(seq A B); do agatha_cache.py get <id> $p; done`
  (cache-first; pages are immutable — never re-download).
- **Read with per-leaf Kraken OCR, not vision**: `split_leaves.py <id> <pages...>`
  then `ocr_batch.sh <id> <pages...>` (Kraken small, ≤10 parallel). Full-spread
  OCR as a coarse extra pass is fine, but per-leaf files are the authoritative
  reading (columns not interleaved by line number).
- Search the `.ocr.txt` files with a generous case-insensitive variant list.
  18th-c. script mangles surnames badly: for ZORROKENS the observed family is
  Zor/Zorok/Zorr — Zorrokens, Zorrohens, Zorropens, Zoropens, Zorohens,
  Zorogens, ZoroEens, Zorotens, Zoropent, Zorons, Zorrokeus, Zorohent, Zorr.
  Keep the list open-ended and RE-RUN the scan after adding any newly observed
  variant (an incomplete list cost a missed entry in the 2026-09-15 run).
  Near-misses (Zorro, Zors, Zorne, Zoronick, Zorothea, van Zoront) go into the
  report as review candidates, never as confirmed hits.
- Scale: the per-leaf OCR batch handles ~50 pages in ~25-40 min at 10 parallel;
  no vision subagent fleet needed. (The old vision-fleet approach — parallel
  subagents doing per-page vision_analyze — is deprecated: the user has ruled
  out vision as the reading tool.)
- Confidence flagging for the user: mark anything not fully legible as DOUBTFUL
  in the report so a human reviews it (user preference, 2026-09-14: they want
  exact agatha URL + page + cache-file reference per finding for human review).

### Transcribing 18th-c. Flemish cursive

- Entry format: `deceased — street/locality — burial place` (baptism registers:
  child / father / mother / godparents).
- LEFT-MARGIN numerals are the DAY OF THE MONTH (reset to 1 at every month
  heading; several entries share a day). Confirmed on multiple pages in the
  2026-09-15 per-leaf OCR runs. RIGHT-margin numerals are monthly death-count
  tallies (+ "in toto" grand total at volume end). Do not quote "entry number N"
  for an agatha register line — quote the month + day.
- Crossed-out/illegible lines: flag them. Report gaps honestly, never invent entries.
- Glossary (recurs across volumes): "kint/kent/kind" = a child (burial of child of
  named person); "cath. kerkhof" = cathedral churchyard; "kerkhof" = churchyard;
  "kerk" = buried inside the church; "minderbroers" = Minorite/Franciscan house;
  "predikheren" = Premonstratensian/Preachers' house.
- Street names that look like surnames: "dornick / doornick straet" = a street,
  not a person (frequent in OLV death entries) — exclude when filtering names.
- Per-leaf Kraken OCR is the reading tool (see "Wide-range name search"); tight
  crops are only needed for the rare genuinely illegible single line, where a
  vision tie-breaker may be used and must be flagged as low-confidence.

## Environment notes (this deployment)

- `web_extract` tool is unavailable (backend is SearXNG, search-only) — use terminal curl
  with Referer + session cookie, or browser_exec.
- Browser session/cookies/tabs persist across browser_exec calls; Python variables do NOT —
  persist IDs/URLs to files under $BH_AGENT_WORKSPACE.
- Get the session cookie with `js("document.cookie")` and reuse in curl.
- System python3 lacks PIL; use the existing `/workspace/.venv` (has pillow;
  used by `split_leaves.py`) or `uv venv` + `uv pip install pillow` elsewhere.
  Cropping is only for the rare single-line vision tie-breaker — never as the
  reading path.
- Page-image cache (this deployment, verified 2026-09-14): helper
  `python3 /workspace/agatha/agatha_cache.py` (list/get/crop/init/du/clean/ensure/check/login)
  over `/workspace/agatha/cache/` — volumes/<id>/{index.json,manifest.json,meta.json,pages/NNN.jpg},
  crops/, lookup/parishes.json + municipalities.json, session_cookie.txt. `get`/`init` call
  `ensure` (auto re-login). Check the lookup files before re-querying ajax.php; register
  every new volume with `init` after finding its manifest_path.
