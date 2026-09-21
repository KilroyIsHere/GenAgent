import urllib.request, sys

def ocr(path):
    data = open(path, 'rb').read()
    body = (b'--X\r\nContent-Disposition: form-data; name="file"; filename="x.png"\r\n\r\n'
            + data + b'\r\n--X\r\nContent-Disposition: form-data; name="model"\r\n\r\n'
            b'small.safetensors\r\n--X--\r\n')
    req = urllib.request.Request('http://host.docker.internal:8008/ocr', data=body,
                                 headers={'Content-Type': 'multipart/form-data; boundary=X'})
    return urllib.request.urlopen(req, timeout=600).read().decode()

for t in ["row18L", "sur18L", "day18L", "row128R", "sur128R", "day128R"]:
    print(f"=== {t} ===", flush=True)
    print(ocr(f"/tmp/{t}.png").strip()[:1500], flush=True)
print("DONE")
