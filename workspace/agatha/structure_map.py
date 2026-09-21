#!/usr/bin/env python3
"""Structure mapper: OCR a page grid across a volume, record per page the
dominant surname letter + min/max year present. The (page->letter) and
(page->years) pattern reveals whether the index is a single A->Z run or
year-banded A->Z cycles.

Usage: structure_map.py VOL [grid_stride]   (default stride=10)
"""
import sys, os, re, json, subprocess, concurrent.futures as cf
from collections import Counter

VOL_DIR = '/workspace/agatha/cache/volumes'
COOKIE = open('/workspace/agatha/cache/session_cookie.txt').read().strip()
REF = 'https://agatha.arch.be/'
URL = 'http://host.docker.internal:8008/ocr-path'

v = sys.argv[1]
stride = int(sys.argv[2]) if len(sys.argv) > 2 else 10
idx = json.load(open(f'{VOL_DIR}/{v}/index.json'))
n = len(idx)

FIRST = set(['Maria','Iabella','Anna','Janna','Joannes','soannes','Jacobul','JacoVIul','Iacobul',
 'Catharina','Elisabeth','Gerardul','Petrul','Petrus','Lucia','Philippul','Clara','Joannel','Joanna',
 'Constantia','Habella','Barbara','Susanna','Melchior','Carolus','Rumoldul','Anua','Helena','Cornelia',
 'Thomal','Gulielmill','Henricus','Paulul','David','Philippl','Sufanna','Adrianul','Ignatiul','Corneliul',
 'Ludovicul','Gaspar','Arnoldus','Josephul','Nicolaus','Andreas','Antonius','Emmanuël','Emmanuel','Dominicul',
 'Bavo','Balthazar','Albertus','Johannes','Guilielmus','Willem','Pieter','Joseph','Sebastianus','Stephanus',
 'Vincentius','Theresia','Carolina','Margareta','Isabella','Elisobetha','Cathavina','JaAnna','Sofia','Bavo'])
MONTH_RE = re.compile(r'(Januarij|Ianuari|Februari|Martii|Aprilis|Maii|Junii|Julii|Augusti|Septembril|Octobris|Novembris|Decembr)', re.I)
YEAR_RE = re.compile(r'\b1[67][0-9][0-9]\b')

def dl(p):
    dst=f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'
    if os.path.exists(dst) and os.path.getsize(dst)>10000: return
    r=subprocess.run(['curl','-sS','-f','-o',dst+'.part','-H',f'Referer: {REF}','-H',f'Cookie: {COOKIE}','-w','%{http_code}',idx[p-1]['full_res_url']],capture_output=True,text=True)
    if r.returncode==0 and r.stdout.strip()=='200': os.rename(dst+'.part',dst)

def ocr(p):
    img=f'{VOL_DIR}/{v}/pages/{p:03d}.jpg'; out=f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if os.path.exists(out) and os.path.getsize(out)>0: return
    subprocess.run(['curl','-sS','-X','POST',URL,'-H','Content-Type: application/json','-d',json.dumps({'path':img,'model':'small.safetensors'}),'-o',out],capture_output=True,text=True,timeout=300)

pages=[p for p in range(2, n, stride)]
if pages[-1] != n-1 and n-1 > 2: pages.append(n-1)
pages=[2]+pages
pages=sorted(set(pages))
for p in pages: dl(p)
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(ocr, pages))

# Analyze
out=[]
for p in pages:
    f=f'{VOL_DIR}/{v}/pages/{p:03d}.ocr.txt'
    if not os.path.exists(f): 
        out.append({'page':p,'letter':'?','ymin':None,'ymax':None}); continue
    txt=open(f,errors='ignore').read()
    initials=[]
    for line in txt.split('\n'):
        s=line.strip()
        if not s or re.match(r'^\d',s): continue
        core=s.rstrip('.')
        if MONTH_RE.search(core) or YEAR_RE.match(core): continue
        if not re.match(r'^[A-Z][a-z]{2,}',core) or core in FIRST: continue
        m=re.match(r'^(?:van |vanden |van den |de |den |du )?([A-Za-z])',core)
        if m: initials.append(m.group(1).upper())
    letter=Counter(initials).most_common(1)[0][0] if initials else '?'
    years=sorted(int(y) for y in YEAR_RE.findall(txt))
    ymin=min(years) if years else None
    ymax=max(years) if years else None
    out.append({'page':p,'letter':letter,'ymin':ymin,'ymax':ymax})
    print(f'p{p:>3}: letter={letter}  years={ymin}-{ymax}', flush=True)

json.dump({'volume':v,'n_pages':n,'grid':out}, open(f'{VOL_DIR}/structure_{v}.json','w'), indent=1)
print('SAVED structure', v, len(out), 'grid points')
