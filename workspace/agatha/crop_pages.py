import os
from PIL import Image

pages = "/workspace/agatha/cache/volumes/6571/pages"
os.makedirs("/workspace/agatha/crops", exist_ok=True)

for p in ["168", "171", "172", "173"]:
    im = Image.open(f"{pages}/{p}.jpg")
    w, h = im.size
    # downscale to max width 1400, split into two leaves
    scale = min(1.0, 1400 / w)
    im2 = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    w2, h2 = im2.size
    im2.crop((0, 0, w2 // 2, h2)).save(f"/workspace/agatha/crops/{p}_L.jpg", quality=72)
    im2.crop((w2 // 2, 0, w2, h2)).save(f"/workspace/agatha/crops/{p}_R.jpg", quality=72)
    for f in ["L", "R"]:
        fp = f"/workspace/agatha/crops/{p}_{f}.jpg"
        print(fp, os.path.getsize(fp))
