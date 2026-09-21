import struct, os

def jpeg_dims(path):
    f = open(path, 'rb').read()
    i = f.find(b'\xff\xc0')
    if i < 0:
        for marker in (b'\xff\xc2', b'\xff\xc1', b'\xff\xc3'):
            i = f.find(marker)
            if i >= 0:
                break
    h, w = struct.unpack('>HH', f[i+5:i+9])
    return w, h

for p in [180, 181, 182, 183, 184, 185]:
    path = f'/workspace/agatha/cache/volumes/6571/pages/{p}.jpg'
    w, h = jpeg_dims(path)
    print(p, w, 'x', h, os.path.getsize(path), 'bytes')
