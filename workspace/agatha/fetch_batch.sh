#!/bin/bash
# fetch_batch.sh VOL P1 P2 ... — serial cache-first page downloads
cd /workspace/agatha
VOL=$1; shift
for p in "$@"; do
  python3 agatha_cache.py get "$VOL" "$p" >/dev/null 2>&1
done
echo "done $VOL"
