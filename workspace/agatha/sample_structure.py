#!/usr/bin/env python3
"""Download sample pages (structure-discovery) for a list of volumes, then
OCR them via the Kraken service (small.safetensors), 10-way parallel.
Index pages here are single landscape pages (not two-column spreads), so we
OCR the full page directly (no split_leaves)."""
import sys, os, json, subprocess, concurrent.futures as cf

VOL_DIR='/workspace/agatha/cache/volumes'
COOKIE=open('/workspace/agatha/cache/session_cookie.txt').read().strip()
REF='https://agatha.arch.be/'
VOLS=[v.strip() for v in sys.argv[1:] if v.strip()]
PAGES=[int(p) for p in (os.environ.get('PAGES','2 3 4 5 6').split())]

def dl(bid,page):
    vdir=f'{VOL_DIR}/{bid}'
    idx=json.load(open(f'{vdir}/index.json'))
    dst=f'{vdir}/pages/{page:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst)>10000:
        return (bid,page,'cache',0)
    url=idx[page-1]['full_res_url']
    r=subprocess.run(['curl','-sS','-f','-o',dst+'.part','-H',f'Referer: {REF}','-H',f'Cookie: {COOKIE}','-w','%{http_code}',url],capture_output=True,text=True)
    if r.returncode!=0 or r.stdout.strip()!='200':
        return (bid,page,f'ERR {r.stdout.strip()} {r.stderr.strip()[:80]}',1)
    os.rename(dst+'.part',dst)
    return (bid,page,f'ok {os.path.getsize(dst)}',0)

# 1) download all sample pages (serial is fine, small)
jobs=[(v,p) for v in VOLS for p in PAGES]
for (bid,page) in jobs:
    try:
        r=dl(bid,page)
        if r[3]: print('DL',r[0],r[1],r[2])
    except SystemExit as e:
        print('DL',bid,page,'ERR',e)

# 2) OCR all downloaded sample pages, 10-way parallel via Kraken /ocr-path
URL='http://host.docker.internal:8008/ocr-path'
def ocr(p):
    bid,page=p
    vdir=f'{VOL_DIR}/{bid}'
    img=f'{vdir}/pages/{page:03d}.jpg'
    out=f'{vdir}/pages/{page:03d}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out)>0:
        return (bid,page,'cache')
    if not os.path.exists(img):
        return (bid,page,'missing')
    r=subprocess.run(['curl','-sS','-X','POST',URL,'-H','Content-Type: application/json',
                      '-d',json.dumps({'path':img,'model':'small.safetensors'}),'-o',out],
                     capture_output=True,text=True,timeout=300)
    sz=os.path.getsize(out) if os.path.exists(out) else 0
    return (bid,page,'ok' if sz>0 else f'EMPTY {r.stderr[:60]}')

print('--- OCR ---')
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for r in ex.map(ocr, jobs):
        print('OCR',r[0],r[1],r[2])
print('DONE',len(jobs),'sample pages across',len(VOLS),'vols')
