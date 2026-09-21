#!/usr/bin/env python3
import json, subprocess
files = [
 '018_L_zorckens_v4.jpg','018_L_hdr.jpg',
 '128_R_zorokens_v1.jpg','128_R_hdr.jpg']
base='/workspace/agatha/cache/volumes/6290/crops/'
for f in files:
    r=subprocess.run(['curl','-s','-X','POST','http://host.docker.internal:8008/ocr-path',
        '-H','Content-Type: application/json',
        '-d',json.dumps({'path':base+f,'model':'small.safetensors'})],
        capture_output=True,text=True)
    print(f"===== {f} =====")
    print(r.stdout.strip() or '(empty)')
    print()
