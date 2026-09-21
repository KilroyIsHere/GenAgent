#!/usr/bin/env python3
"""Fire parallel Kraken OCR jobs (10-slot pattern)."""
import sys, os, json, time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ENDPOINT = "http://host.docker.internal:8008/ocr"
CROPS = sys.argv[1:]

def ocr(path):
    name = os.path.basename(path).rsplit(".", 1)[0]
    import uuid
    boundary = uuid.uuid4().hex
    body = []
    def add(name_, content, ctype):
        body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name_}\"\r\n\r\n{content}\r\n".encode())
    add("model", "small", "text/plain")
    add("device", "cpu", "text/plain")
    with open(path, "rb") as f:
        img = f.read()
    body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}.png\"\r\nContent-Type: image/png\r\n\r\n".encode())
    body.append(img)
    body.append(f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(ENDPOINT, b"".join(body),
                                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        out = json.loads(r.read().decode())
    text = out.get("text", "") if isinstance(out, dict) else str(out)
    dst = f"/workspace/agatha/cache/volumes/6260/{name}.ocr.txt"
    with open(dst, "w") as f:
        f.write(text)
    return name, len(text), round(time.time() - t0, 1), dst

with ThreadPoolExecutor(max_workers=10) as ex:
    for name, nchars, secs, dst in ex.map(ocr, CROPS):
        print(f"{name}: {nchars} chars in {secs}s -> {dst}")
