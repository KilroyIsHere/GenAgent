# Fuzzy name search over an already-OCR'd register corpus

Condensed notes from the 2026-09-17 re-scan of the **Johannes Petri Zorrokens**
corpus (22 volumes / ~5,200 `.ocr.txt` files). Purpose: after a fixed-pattern
sweep (or a prior search) has OCR'd a corpus, re-scan the SAME files with real
edit-distance matching to catch the surname spellings a prefix-anchored regex
structurally cannot see. **No new OCR, no downloads — seconds, not minutes.**

## Why the fixed net misses (the actual gap)

The sweep used a case-insensitive regex on the surname stem:
`\\bdo[rz][rre]*[a-z]{0,8}\\b` for Zorrokens. It only fires on tokens that START
with `zor`/`zorr`/`doz`. So it is structurally blind to:

- **Wrong leading letter** — a B-initial `Borrokens` family (real, recurring
  across OLV-Noord/OLV-Zuid/St-Jacobus/St Joris, 1730s–40s). A `do[rz]` regex
  can NEVER match this. Its best target-shaped line was 6119 p121
  `joannes Petrus Borrokens` (1739): child name matches the Joannes+Petrus
  pattern, surname is B-initial. Needs a crop/human call on B-vs-D — do NOT
  decide surname identity from OCR alone.
- **Inserted/extra letter** — `Zovrekens` (D-initial with a `v` the prefix
  missed; 6327 p67, St-Laurentius). Again D-initial so a broader stem would
  catch it, but the tight prefix did not.
- **Dropped vowel / letter** — `Zorockens`, `Zoorekens`, `zorrokes`.

These are precisely the cursive OCR failures a no-miss search must not drop.

## Matcher that worked (design)

Score each candidate surname-slot token against BOTH target surnames
(`zorokens` AND `zorrokens`):

1. **Whole-token Levenshtein <= 3** — clean, reviewable, low false-positive rate.
   This is the primary layer.
2. **Distinctive-stem CONTAINS pass** — substring match on `zorok`/`zorrok`/
   `zorock` (>=5-char stem). This is what recovers `van Zorokens` / `vzorokens`
   / `Zoorekens` that whole-token distance (long token) would rate above 3.
   Strip a leading particle (`van`/`de`/`den`/`vd`) before scoring so a
   scribe-attached particle doesn't push the distance up.

First-name slot: score against the target given name(s) (`joannes` +
`petri`/`petrus`) with the same <=3 rule, but keep it as a CONFIRMATION signal,
not a primary gate — the match key is **first-name + fuzzy-surname + date**,
never surname alone.

## Two traps (both bitten this session)

- **Short-stem contains at distance 2 FLOODS.** A contains match on a 3–4-char
  stem (`zor`, `zoro`) at Levenshtein 2 pulled in Theodorus, Doncker, Van
  Zooren, Ludovicus — ~10,000 hits, unusable. Keep the stem DISTINCTIVE (>=5
  chars) and the whole-token distance <=3. Prefer far fewer real candidates over
  a big net: ~1,400 reviewable hits >> 9,958 noise.
- **No SLOT gate = flood.** A fuzzy surname token must only count in the
  CHILD's own surname / first-name field. If you match across the whole line,
  godparents, witnesses, and neighbouring families all fire and bury the signal.
  Gate the fuzzy surname to the surname slot and the fuzzy first-name to the
  first-name slot.

## Output discipline

- Every fuzzy hit is **DOUBTFUL until a crop-verify of that line agrees**
  (Kraken hallucinates cursive surnames and capitals).
- Report as a **DELTA vs the fixed net**: for each candidate say whether the
  previous regex could have matched it (no -> it is what the fuzzy pass ADDED).
  That is what makes the re-scan's value visible to the user.
- Reuse the proven evidence-link convention: the user's viewer resolves
  `file:///D:/AI/workspace/agatha/cache/...` (Windows absolute), NOT relative
  `../../../../` links. Verify every link target exists on disk before
  delivering.

## Corpus / window provenance for this search

- Search: "Birth of Johannes Petri Zorrokens" — anchor = 2 Feb 1722 St Andries
  index entry (6223 p48 `Zorokens. Joes Petrus … Februari 2`).
- Corpus (already OCR'd): 13 baptism index vols (6379, 6141, 6088, 6119, 6223,
  6224, 6160, 6161, 454853, 6327, 6189, 6209, 6300) + San Felipe 6355 +
  St Joris legacy registers (6290–6293) + St Joris indexes (6260/6262/6265/6266).
- Window 1715–1741. Fixed-net results: `lookup/full_sweep_results.json`.
  Fuzzy results: `lookup/fuzzy_zorrokens_results.json`. Matcher:
  `scripts/fuzzy_name_match.py`.
