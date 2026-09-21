# Agatha page-image cache

Persistent, cross-invocation cache of full-res page images extracted from
agatha.arch.be. Data on the site is static (historical registers never
change), so images are cached forever: once a page image is here, no next
invocation should ever hit the agatha servers for it again.

## Layout

    /workspace/agatha/cache/
      volumes/<bookpart_id>/
        manifest.json           # IIIF manifest for this volume (from agatha page HTML)
        index.json              # per-canvas: page, label, full_res_url, jp2_service
        pages/NNN.jpg           # full-res page image, NNN = 1-based canvas index (zero-padded 3)
        pages/NNN_L.jpg / NNN_R.jpg   # left/right leaf splits (split_leaves.py) — Kraken input
        pages/NNN*.ocr.txt      # OCR outputs: NNN.small.ocr.txt (full spread) and
                                # NNN_L.ocr.txt / NNN_R.ocr.txt (per-leaf; authoritative)
        meta.json               # volume metadata: bookpart_id, parish, type, date range, title
                                # + page_year_map / page_month_map (verified date anchors, added after first use)
      crops/<bookpart_id>/NNN_<name>.png   # derived crops, also cached (re-derive only if missing)
      lookup/
        parishes.json           # parish_id -> {name, municipality, bookparts per type}
        municipalities.json     # municipality_id -> name (Antwerpen = 12 verified)
      session_cookie.txt        # PHPSESSID+cookieconsent cookie for curl fetches
      README.md                 # this file

## Helper (all commands verified)

`/workspace/agatha/agatha_cache.py` — the single entry point for future runs:

    python3 agatha_cache.py list <bookpart_id>            # which pages are cached
    python3 agatha_cache.py get <bookpart_id> <page>      # cache-first fetch (auto-refresh)
    python3 agatha_cache.py crop <id> <page> <x,y,w,h> <name>   # cached crop
    python3 agatha_cache.py init <id> <manifest_url> <cookie> --title ... --range ... --parish-id N
    python3 agatha_cache.py du                            # disk usage per category
    python3 agatha_cache.py clean [bookpart_id]           # drop crops, KEEP full-res pages
    python3 agatha_cache.py ensure                        # auto-refresh: check + re-login if stale
    python3 agatha_cache.py check                         # (diagnostic) report cookie validity
    python3 agatha_cache.py login                         # force a fresh re-login now

`du` breaks usage into full-res pages / volume metadata / crops / lookup.
`clean` deletes crops only (all volumes, or one via argument) — full-res
pages, index and meta are never touched, and crops can always be re-derived
from the cached pages. Prefer `clean` over deleting files by hand: it frees
space and removes the now-empty per-volume crop dirs.

## Invariants / rules for future invocations

1. CHECK FIRST: before any curl to agatha, look for the file in this cache.
   If present, use it. Agatha data is immutable; never re-download.
2. File naming: page N of volume V is `volumes/V/pages/NNN.jpg` (NNN zero-padded to 3 digits).
   Canvas index is 1-based (canvas 1 = cover/first page).
3. Every new download must be written to the cache, not to a scratch dir.
4. Crops are derived artifacts: name them descriptively; they're safe to
   regenerate but keep the source page if the crop is the only evidence.
5. meta.json must record the volume's date range so future runs can pick the
   right volume by date (the user-supplied year range is only a filter; the
   volume whose span contains the target month is the one to open).
6. A login session is only needed for agatha page navigation; images are
   fetched by curl with the session cookie + Referer header (see runbook.md).

## Session cookie lifetime + auto-refresh (verified 2026-09-14)

- The agatha `PHPSESSID` is a **session cookie** — `Set-Cookie` carries no
  `Expires`/`Max-Age`, so it has **no fixed wall-clock expiry**. It is valid
  until the server drops the PHP session.
- **Nothing in the page workflow actually requires the cookie.** Verified
  with a dead cookie: i3f.arch.be full-res images (200), ajax.php lookups
  (200) and the viewer page all work with just a `Referer` header. The cookie
  only gates the logged-in header (<AGATHA_USER> vs. Login) and `/en/profil/`. A stale
  cookie is therefore a soft problem — but `ensure` keeps it valid anyway.
- **Auto-refresh:** `ensure` does a capability check on `/en/profil/`
  (HTTP 200 = valid; anything else = stale). On stale/missing it re-seeds a
  session (GET the search page for a fresh PHPSESSID) and re-authenticates via
  `POST /library/login.php` (`username`, `password`, `app=/en/search/genealogie`
  → body `1` = success), then saves the new PHPSESSID to `session_cookie.txt`.
- `get` and `init` call `ensure` first, so a normal run self-heals without
  any manual re-login. `check` reports validity; `login` forces a fresh one.
- Login recipe (if you ever need it by hand): seed with
  `curl -c jar -o /dev/null <search page>` to get a PHPSESSID, then
  `curl -b jar -c jar -X POST library/login.php --data 'username=...&password=...&app=/en/search/genealogie'`.

## Verified seeds (as of 2026-09-14)

- Volume 6571: Antwerpen, Onze-Lieve-Vrouw (parish_id 13, municipality_id 12),
  funerals/deaths, 01/01/1732 - 30/11/1774, 188 pages.
  Pages 1-9 are cached (see pages/). Page 2 left leaf = Januarij 1732,
  entries 1-31 (two-column register; month headings can appear anywhere on a page).
  Crops were cleared 2026-09-14 via `clean` — re-derive with `crop` if needed.
