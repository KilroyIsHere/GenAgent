#!/workspace/agatha/.venv_pil/bin/python
from PIL import Image

def crop(volpage, leaf, y0, y1, tag, scale=4):
    p = f'/workspace/agatha/cache/volumes/6290/pages/{volpage}_{leaf}.jpg'
    img = Image.open(p)
    w, h = img.size
    c = img.crop((0, int(h*y0), w, int(h*y1)))
    c.resize((c.width*scale, c.height*scale), Image.LANCZOS).save(
        f'/workspace/agatha/cache/volumes/6290/crops/{tag}.jpg')
    print(tag, c.size, 'src', img.size)

# 018_L Zorckens line ~0.85h (raw line 33/40). Band 0.78-0.93h to catch it + day margin
crop('018','L', 0.78, 0.93, '018_L_zorckens_v4', 4)
# month header + day margin just above it 0.55-0.80h
crop('018','L', 0.55, 0.80, '018_L_hdr', 3)
# 128_R zorokens line ~0.40h (raw line 18/~45). Band 0.33-0.50h
crop('128','R', 0.33, 0.50, '128_R_zorokens_v1', 4)
# month header above 128_R 0.0-0.35h
crop('128','R', 0.0, 0.33, '128_R_hdr', 3)
print('done')
