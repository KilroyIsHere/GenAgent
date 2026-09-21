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

# 018_L: entry lines (Octobrs block, child + father + mother) ~ y 0.86-0.99
crop("018_L", 0.0, 1.0, 0.86, 0.99, "e18", 3)
# 128_R: entry lines (April block, around "hard zorokens") ~ y 0.26-0.38
crop("128_R", 0.0, 1.0, 0.26, 0.38, "e128", 3)
print("OK")
