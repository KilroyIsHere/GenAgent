#!/usr/bin/env bash
# Download index window pages for the 1735-1752 sweep (serial; cache-first)
cd /workspace/agatha
echo "== 6260 p88-150 =="
for p in $(seq 88 150); do python3 agatha_cache.py get 6260 $p >/dev/null || echo "FAIL 6260 $p"; done
echo "== 6262 p115-168 =="
for p in $(seq 115 168); do python3 agatha_cache.py get 6262 $p >/dev/null || echo "FAIL 6262 $p"; done
echo DONE
python3 agatha_cache.py list 6260 | wc -l
python3 agatha_cache.py list 6262 | wc -l
