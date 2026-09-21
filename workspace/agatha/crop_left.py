from PIL import Image
import os

BASE = "/workspace/agatha/cache/volumes/6290"

def crop(leaf, x0, x1, y0, y1, tag, scale):
    im = Image.open(os.path.join(BASE, "pages", leaf + ".jpg")).convert("L")
    W, H = im.size
    c = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
    c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
    c.save(f"/tmp/{tag}.png")
    print(tag, c.size)

# 018_L: left name field, lines 31-35 (Octobrs block entries)
crop("018_L", 0.02, 0.50, 0.80, 0.99, "lf18", 2)
# 128_R: left name field, lines 17-22
crop("128_R", 0.02, 0.50, 0.24, 0.40, "lf128", 2)
print("OK")
