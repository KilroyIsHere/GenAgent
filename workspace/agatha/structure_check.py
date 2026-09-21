#!/usr/bin/env python3
"""Download+OCR consecutive pages to discover a volume's real structure.
Usage: structure_check.py VOL PAGES...  (e.g. 6141 2 3 4 5 6 7 8)"""
import sys, os, json, subprocess, concurrent.futures as cf

VOL_DIR = '/workspace/agatha/cache/volumes'
COOKIE = open('/workspace/agatha/cache/session_cookie.txt').read().strip()
REF = 'https://agatha.arch.be/'
URL = 'http://host.docker.internal:8008/ocr-path'

v = sys.argv[1]
pages = [int(p) for p in sys.argv[2:]]
idx = json.load(open(f'{VOL_DIR}/{v}/index.json'))
n = len(idx)

def dl(p):
    dst = f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return 'cache'
    r = subprocess.run(['curl','-sS','-f','-o',dst+'.part','-H',f'Referer: {REF}','-H',f'Cookie: {COOKIE}','-w','%{http_code}',idx[p-1]['full_res_url']],
                       capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != '200':
        return f'ERR {r.stdout}'
    os.rename(dst+'.part', dst)
    return 'ok'

def ocr(p):
    img = f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    out = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return 'cache'
    subprocess.run(['curl','-sS','-X','POST',URL,'-H','Content-Type: application/json',
                    '-d',json.dumps({'path':img,'model':'small.safetensors'}),'-o',out],
                   capture_output=True, text=True, timeout=300)
    return 'ok' if os.path.exists(out) and os.path.getsize(out) > 0 else 'EMPTY'

for p in pages:
    dl(p); ocr(p)

# Print year + D-surname signal per page
import re
for p in pages:
    f = f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if not os.path.exists(f):
        print(f'--- p{p}: MISSING'); continue
    txt = open(f, errors='ignore').read()
    years = sorted(set(re.findall(r'\b1[67][0-9][0-9]\b', txt)))
    dwords = re.findall(r'\b[dD][a-z]*\b', txt)
    print(f'--- p{p}: years={years}  n={len(txt)}  D-tokens={dwords[:12]}')
