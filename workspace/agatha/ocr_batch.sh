#!/bin/bash
# OCR a set of leaves via the Kraken service, max 10 parallel.
# Usage: ocr_batch.sh VOL PAGES...
#   e.g. ocr_batch.sh 6571 155 156 157 158 159
# Splits each spread into _L/_R leaves (reusing existing splits), then OCRs
# all leaves with small.safetensors, writing <vol>/pages/NNN_L.ocr.txt etc.
set -u
URL=http://host.docker.internal:8008/ocr-path
VOL=$1; shift
mkdir -p /workspace/agatha/logs
LOG=/workspace/agatha/logs/ocr_${VOL}_$(date +%H%M%S).log
echo "== start vol=$VOL pages=$* $(date)" > "$LOG"
/workspace/agatha/.venv_pil/bin/python /workspace/agatha/split_leaves.py "$VOL" "$@" >>"$LOG" 2>&1
# splits must exist before any OCR job starts
for p in "$@"; do
  for s in L R; do
    f="/workspace/agatha/cache/volumes/${VOL}/pages/$(printf %03d $p)_${s}.jpg"
    [ -s "$f" ] || { echo "SPLIT MISSING: $f" | tee -a "$LOG"; exit 1; }
  done
done
for p in "$@"; do
  for s in L R; do
    out="/workspace/agatha/cache/volumes/${VOL}/pages/$(printf %03d $p)_${s}.ocr.txt"
    src="/workspace/agatha/cache/volumes/${VOL}/pages/$(printf %03d $p)_${s}.jpg"
    ( curl -sS -X POST "$URL" -H 'Content-Type: application/json' \
        -d "{\"path\":\"${src}\",\"model\":\"small.safetensors\"}" \
        -o "$out" 2>>"$LOG" ) &
    # throttle to 10 concurrent
    while [ "$(jobs -rp | wc -l)" -ge 10 ]; do wait -n; done
  done
done
wait
echo "== done vol=$VOL $(date)" >> "$LOG"
fail=0
for p in "$@"; do
  for s in L R; do
    f="/workspace/agatha/cache/volumes/${VOL}/pages/$(printf %03d $p)_${s}.ocr.txt"
    if [ ! -s "$f" ]; then echo "EMPTY/FAIL: $f"; fail=1; fi
  done
done
[ $fail -eq 0 ] && echo "ALL OK vol=$VOL pages=$*"
echo "LOG: $LOG"
