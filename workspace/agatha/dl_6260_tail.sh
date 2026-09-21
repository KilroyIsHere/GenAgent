#!/usr/bin/env bash
# 6260 tail window 1743-1752 (est p151-182): download serial, then OCR
cd /workspace/agatha
for p in $(seq 151 182); do python3 agatha_cache.py get 6260 $p >/dev/null || echo "FAIL $p"; done
bash ocr_batch.sh 6260 151 152 153 154 155 156 157 158 159 160 161 162 163 164 165 166 167 168 169 170 171 172 173 174 175 176 177 178 179 180 181 182 2>&1 | tail -2
