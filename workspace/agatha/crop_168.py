import sys
try:
    from PIL import Image
except ImportError:
    print("NOPIL")
    sys.exit(0)
src = "/workspace/agatha/cache/volumes/6571/pages/168.jpg"
im = Image.open(src)
w, h = im.size
print("size", w, h)
# Crop left leaf (top half) and right leaf (top half) as two smaller images
left = im.crop((0, 0, w // 2, h))
right = im.crop((w // 2, 0, w, h))
left.save("/workspace/agatha/tmp168_left.jpg", quality=85)
right.save("/workspace/agatha/tmp168_right.jpg", quality=85)
print("saved", left.size, right.size)
