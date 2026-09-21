---
name: kraken-ocr
description: Use the local Kraken OCR service at http://host.docker.internal:8008 to transcribe historical handwritten genealogy documents. Use small.safetensors by default; use medium.safetensors only when the user explicitly asks.
version: 2.0.0
author: Local
license: MIT
platforms:
  - windows
  - linux
metadata:
  tags:
    - ocr
    - kraken
    - handwriting
    - genealogy
    - docker
---

# Kraken OCR

OCR for historical handwritten documents (parish registers, civil records, notarial records) via the local Kraken service.

## Execution & approvals — run simple crop+OCR without waiting (user directive 2026-09-15)

A "simple crop + OCR job" (crop an image that already lives under `/workspace`
and POST it to `/ocr-path` or `/ocr` with `small.safetensors`) is **local,
read-only, and non-destructive**: no network fetch of source data, no mutation
of the source image. **The user has directed: DO NOT wait for an approval card
for these — just run them.** Don't pause the workflow to ask permission to crop
+ OCR a file you already have. Fire the job, read the result, continue.

Still confirm first for: OCR with a model other than `small` (medium needs an
explicit user request), anything that downloads NEW source data from the
archive, deleting/overwriting source images, and scope that balloons to many
more pages than planned. The line: **crop + Kraken-small on files already under
/workspace → run immediately; network fetch, non-small model, or destructive
write → confirm.**

## Core settings (defaults; change only if the user asks)

- URL: `http://host.docker.internal:8008` — the ONE correct URL; works from the Hermes container, WSL, and the Windows host. Never `kraken:8000` (container hostname, unreliable) and never `localhost:8008` (resolves to the local environment, not the Docker host).
- Model: `small.safetensors` (default; better results than other tested models on the user's documents). `medium.safetensors` only on explicit user request (e.g. comparison runs). Never switch models automatically.
- Endpoint: `POST /ocr-path` when the file already lives under `/workspace` — preferred. `POST /ocr` (multipart upload) only when the file is not in the shared workspace.
- Server defaults: device=cpu, precision=32-true, batch_size=8, line_workers=0 → the minimal `{path, model}` payload is sufficient; send explicit fields only when overriding.
- Paths: `D:\AI\workspace` (Windows) = `/workspace` in BOTH the Hermes and Kraken containers. Always send `/workspace/...` to the API; never `D:\...`.
- GPU: never `cuda:0` unless the user explicitly asks.

## OCR an image

```bash
curl -sS -X POST http://host.docker.internal:8008/ocr-path \
  -H 'Content-Type: application/json' \
  -d '{"path":"/workspace/agatha/cache/volumes/6571/pages/155.jpg","model":"small.safetensors"}'
```

Multiple pages: 10 parallel jobs is the standard concurrency (measured). Do not exceed 10 simultaneous jobs without a reason. For ad-hoc crops (targeted re-reads, band re-OCR) fire them in parallel too:

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -s -F "file=@${i}.jpg" -F "model=small.safetensors" \
    http://host.docker.internal:8008/ocr -o ${i}.ocr.txt &
done
wait
```

```bash
for p in $(seq 155 164); do
  curl -sS -X POST http://host.docker.internal:8008/ocr-path \
    -H 'Content-Type: application/json' \
    -d "{\"path\":\"/workspace/agatha/cache/volumes/6571/pages/${p}.jpg\",\"model\":\"small.safetensors\"}" \
    > "/workspace/agatha/cache/volumes/6571/pages/${p}.small.ocr.txt" &
done; wait
```

Persistence: write `.ocr.txt` files only when the user wants OCR saved. Name them `NNN.<model>.ocr.txt` (e.g. `155.small.ocr.txt`, `155.medium.ocr.txt`) so outputs from different models compare side by side; a bare `NNN.ocr.txt` means the default (small) model. If the user only wants the text in chat, don't create files.

## Performance (measured on the 32-core CPU-only host)

- One job = exactly one core at 100% (flat "100%" in Docker Desktop, ~3-4% of the machine). Per-line forward passes are too small for torch's threads to engage.
- `line_workers` is a no-op here: 0 vs 16 measured identical. Do not "fix" speed by changing it or the service defaults.
- Throughput comes only from parallel jobs (10 jobs ≈ 10 of 32 cores). Reference wall times, full-res page (~850 KB): small ≈ 2-3 min, medium ≈ 6 min; scales ~linearly with concurrent jobs.

## Feeding the model

- **`POST /ocr-path` returns PLAIN TEXT, not JSON** (observed 2026-09-15):
  the response body is the raw OCR text itself — `json.loads()` on it fails
  with "Extra data". Read `r.read().decode()` directly; do not wrap the
  response in a JSON parser.

- **One page per job — never a two-page spread.** The model was trained on
  single pages; for register spreads, split first (`/workspace/agatha/
  split_leaves.py VOL PAGES...` produces `NNN_L.jpg`/`NNN_R.jpg`) and OCR
  each leaf separately. Per-leaf OCR is materially better for the month
  headings at leaf tops, which carry the dating of every entry below them.
- **Vision-model rule (user mandate):** this OCR model is trained on the
  user's cursive Dutch/Latin documents and is the reading tool. The agent's
  own vision model must NOT be used to read these documents (full pages,
  batches, or contact sheets) — it does not work at that scale and has been
  explicitly ruled out. Vision is a last-resort tie-breaker for a single
  specific line or region after OCR has failed, and any such use must be
  flagged in the output as "vision-verified, low confidence".
- **Month headings are the most reliable field:** with per-leaf input the
  leaf-top heading (e.g. `Januari 1766`) OCRs cleanly. Entries are anchored to
  the nearest heading above them in the same column; a leaf can span two
  months, so also check for a mid-leaf heading. Never date a page by
  pages-per-year extrapolation.

## Raw OCR rules

Treat Kraken output as raw transcription. Preserve uncertain, malformed, or incomplete text. Never invent names, dates, places, abbreviations, or missing words. Corrections are a separate, requested step, with uncertainty made explicit (`Joannes [?] Peeters`, `Maria van [unclear]`). Keep raw and corrected versions separate. Surnames mangle hard in 18th-c. script — when searching a name, use a generous case-insensitive variant list (e.g. ZORROKENS → Zorrohens, Zorropens, Zoropens, Zorohens, Zorogens, ZoroEens, Zorotens, Zoropent, Zorons, Zorrokeus, Zorohent, Zorr — observed 2026-09-15; keep it open-ended and add newly observed variants) and treat near-misses (Zorro, Zors, Zorne, Zoronick, Zorothea, van Zoront) as review candidates, not hits. One incomplete variant list cost a missed entry in the 2026-09-15 run — re-run the scan after adding any new variant. The same letter-apart mangling
   appears IN BOTH index and register, so a register line one letter off from
   an index entry is the SAME family, not a different one.

Model comparison note (vol 6571 page 155, small vs medium): genuinely mixed — medium better on names (Elisabetha, hofstraat), small better on streets and line completeness. Not a clear winner; small stays the default.

## Error handling

- Connection failure → `curl -sS http://host.docker.internal:8008/health`; if down, report it, don't retry indefinitely.
- Model missing → check `/models`; `small.safetensors` required; no automatic substitution.
- File not found → confirm the file exists under `/workspace` and the API received a Linux path (not `D:\...`).
- API errors carry `error`, `returncode`, `stdout`, `stderr`, `command` — keep them when diagnosing and classify (missing image / missing model / segmentation / recognition / execution / networking / service down). Never reduce an error to "OCR failed."

## Troubleshooting (Windows host)

```cmd
docker ps --filter name=kraken            :: container running?
curl.exe http://localhost:8008/health     :: health from Windows
docker exec kraken ls -lh /workspace/...  :: Kraken sees the file?
docker exec hermes ls -lh /workspace/...  :: Hermes sees the same path?
```

## Security

- OCR only files under `/workspace`; do not expose arbitrary host/container paths.
- Never overwrite or delete source images.
- Never silently modify genealogy names, dates, locations, or historical spellings.
- Use the HTTP API, not `docker exec`, for normal OCR.
- Do not modify Kraken configuration or add shell-like endpoints unless the user explicitly asks.
