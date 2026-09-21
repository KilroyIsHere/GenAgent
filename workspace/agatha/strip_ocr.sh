#!/usr/bin/env bash
# Serial re-OCR of p44_R strips (2 at a time to avoid OOM)
cd /workspace/agatha/cache/crops/6266
for y in 760 860 960 1060 1160; do
  echo "=== OCR strip $y ==="
  curl -sS -X POST http://host.docker.internal:8008/ocr-path \
    -H 'Content-Type: application/json' \
    -d "{\"path\":\"/workspace/agatha/cache/crops/6266/044_strip_${y}.png\",\"model\":\"small.safetensors\"}" \
    -o "strip_${y}.ocr.txt"
  head -c 200 "strip_${y}.ocr.txt"; echo
done
echo ALLOK
