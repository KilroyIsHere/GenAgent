#!/workspace/agatha/.venv_pil/bin/python
from PIL import Image
img = Image.open('/workspace/agatha/cache/volumes/6290/pages/018_L.jpg')
w, h = img.size
# Zorckens line near ~0.88-0.92h of full leaf
c = img.crop((0, int(h*0.82), w, int(h*0.96)))
c.resize((c.width*3, c.height*3), Image.LANCZOS).save(
    '/workspace/agatha/cache/volumes/6290/crops/018_L_zorckens_line_v3.jpg')
print('ok', c.size)
