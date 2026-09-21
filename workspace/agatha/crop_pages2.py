import os
from PIL import Image

pages = "/workspace/agatha/cache/volumes/6571/pages"
os.makedirs("/workspace/agatha/crops2", exist_ok=True)

for p in ["168", "171", "172", "173"]:
    im = Image.open(f"{pages}/{p}.jpg")
    w, h = im.size
    scale = min(1.0, 1100 / w)
    im2 = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    w2, h2 = im2.size
    # each leaf split into top and bottom halves
    for lf, (x0, x1) in {"L": (0, w2//2), "R": (w2//2, w2)}.items():
        for half, (y0, y1) in {"T": (0, h2//2), "B": (h2//2, h2)}.items():
            im2.crop((x0, y0, x1, y1)).save(f"/workspace/agatha/crops2/{p}_{lf}{half}.jpg", quality=68)
for f in sorted(os.listdir("/workspace/agatha/crops2")):
    print(f, os.path.getsize(f"/workspace/agatha/crops2/{f}"))
