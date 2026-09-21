#!/bin/bash
# Full-volume OCR of 6292 (baptisms 1729-1742), canvas 1-230.
# Splits leaves (skips missing canvases, e.g. 0057), OCRs with max 10 parallel.
set -u
URL=http://host.docker.internal:8008/ocr-path
VOL=6292
BASE=/workspace/agatha/cache/volumes/$VOL
mkdir -p /workspace/agatha/logs
LOG=/workspace/agatha/logs/ocr_${VOL}_full_$(date +%H%M%S).log
echo "== start $(date)" > "$LOG"
# 1) split all present page spreads
for p in $(seq 1 230); do
  z=$(printf %03d $p)
  f="$BASE/pages/${z}.jpg"
  if [ -s "$f" ]; then
    /workspace/.venv/bin/python /workspace/agatha/split_leaves.py $VOL $p >>"$LOG" 2>&1
  else
    echo "SKIP missing canvas $z" >>"$LOG"
  fi
done
echo "== splits done $(date)" >>"$LOG"
# 2) OCR existing leaves, throttled to 10
n=0
for p in $(seq 1 230); do
  z=$(printf %03d $p)
  for s in L R; do
    src="$BASE/pages/${z}_${s}.jpg"
    out="$BASE/pages/${z}_${s}.ocr.txt"
    if [ -s "$src" ] && [ ! -s "$out" ]; then
      ( curl -sS -X POST "$URL" -H 'Content-Type: application/json' \
          -d "{\"path\":\"${src}\",\"model\":\"small.safetensors\"}" \
          -o "$out" 2>>"$LOG" ) &
      n=$((n+1))
      while [ "$(jobs -rp | wc -l)" -ge 10 ]; do wait -n; done
    fi
  done
done
wait
echo "== done $(date) jobs=$n" >>"$LOG"
