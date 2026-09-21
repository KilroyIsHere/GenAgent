#!/workspace/agatha/.venv_pil/bin/python
from PIL import Image

PD='/workspace/agatha/cache/volumes/6290/pages'
OUT='/workspace/agatha/cache/volumes/6290/crops'

img = Image.open(f'{PD}/018_L.jpg'); w,h = img.size
# left margin day numbers, rows around Zorckens (0.55-0.95h)
c = img.crop((0, int(h*0.55), 300, int(h*0.95)))
c.resize((c.width*5, c.height*5), Image.LANCZOS).save(f'{OUT}/018_L_margin5x.jpg')
# the Zorckens row band, 4x, full width
c = img.crop((0, int(h*0.70), w, int(h*0.84)))
c.resize((c.width*4, c.height*4), Image.LANCZOS).save(f'{OUT}/018_L_row4x.jpg')

img = Image.open(f'{PD}/128_R.jpg'); w,h = img.size
# zorokens row region 0.05-0.28h full width 4x
c = img.crop((0, int(h*0.05), w, int(h*0.28)))
c.resize((c.width*4, c.height*4), Image.LANCZOS).save(f'{OUT}/128_R_row4x.jpg')
# left margin of same region 5x
c = img.crop((0, int(h*0.05), 300, int(h*0.28)))
c.resize((c.width*5, c.height*5), Image.LANCZOS).save(f'{OUT}/128_R_margin5x.jpg')
# top header band of 128_R
c = img.crop((0, 0, w, int(h*0.06)))
c.resize((c.width*4, c.height*4), Image.LANCZOS).save(f'{OUT}/128_R_top4x.jpg')
print('ok')
