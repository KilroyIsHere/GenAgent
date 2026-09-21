#!/usr/bin/env python3
import sys, os, json, subprocess, concurrent.futures as cf
VOL='/workspace/agatha/cache/volumes'
COOKIE=open('/workspace/agatha/cache/session_cookie.txt').read().strip()
REF='https://agatha.arch.be/'
URL='http://host.docker.internal:8008/ocr-path'
v=sys.argv[1]
pages=[int(x) for x in sys.argv[2:]]
idx=json.load(open(f'{VOL}/{v}/index.json'))
def dl(p):
    dst=f'{VOL}/{v}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst)>10000: return
    r=subprocess.run(['curl','-sS','-f','-o',dst+'.part','-H',f'Referer: {REF}','-H',f'Cookie: {COOKIE}','-w','%{http_code}',idx[p-1]['full_res_url']],capture_output=True,text=True)
    if r.returncode==0 and r.stdout.strip()=='200': os.rename(dst+'.part',dst)
def ocr(p):
    img=f'{VOL}/{v}/pages/{p:03d}.jpg'; out=f'{VOL}/{v}/pages/{p:03d}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out)>0: return
    subprocess.run(['curl','-sS','-X','POST',URL,'-H','Content-Type: application/json','-d',json.dumps({'path':img,'model':'small.safetensors'}),'-o',out],capture_output=True,text=True,timeout=300)
for p in pages: dl(p)
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(ocr,pages))
print('done',v,pages[0],'-',pages[-1])
