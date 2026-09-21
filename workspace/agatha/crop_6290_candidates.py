#!/workspace/agatha/.venv_pil/bin/python
"""Wider crops for 6290 p18_L Zorckens line and p17_R andor lines."""
from PIL import Image

PD = '/workspace/agatha/cache/volumes/6290/pages'
OUT = '/workspace/agatha/cache/volumes/6290/crops'

img = Image.open(f'{PD}/018_L.jpg')
w, h = img.size  # 1272 x 3000
# bottom 45%: should contain the October entries incl. 'sus z Michaet Zorckens'
img.crop((0, int(h*0.55), w, h)).save(f'{OUT}/018_L_bot.jpg')
img.crop((0, 0, w, int(h*0.15))).save(f'{OUT}/018_L_top.jpg')

img = Image.open(f'{PD}/017_R.jpg')
w, h = img.size
img.crop((0, int(h*0.55), w, h)).save(f'{OUT}/017_R_bot.jpg')
img.crop((0, 0, w, int(h*0.15))).save(f'{OUT}/017_R_top.jpg')
print('ok')
