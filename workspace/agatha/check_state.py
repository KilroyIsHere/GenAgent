import json, os, glob

base = 'cache/ocr'
# find orchestrator state file wherever it lives
for cand in [
    'cache/runs/frederic_zorokens/mon_state.json',
    'cache/runs/frederic_zorokens/ocr_progress.json',
    'runs/frederic_zorokens/mon_state.json',
]:
    if os.path.exists(cand):
        print('state file:', cand)
        try:
            st = json.load(open(cand))
            for k, v in st.items():
                if isinstance(v, dict):
                    print(f'  {k}: dl={v.get("pages_dl","?")}/{v.get("pages_total","?")} ocr={v.get("leaves_ocr","?")}/{v.get("leaves_total","?")} fail={v.get("fail",0)}')
                else:
                    print(f'  {k}: {v}')
        except Exception as e:
            print('  parse err', e)

# on-disk OCR coverage for the target page ranges
def count(vol, pages):
    done = 0; tot = 0
    for p in pages:
        for side in ['R', 'L']:
            f = f'{base}/{vol}/{p:04d}_{side}.ocr.txt'
            tot += 1
            if os.path.exists(f) and os.path.getsize(f) > 0:
                done += 1
    return done, tot

d6245, t6245 = count('6245', range(1, 234))
d6246, t6246 = count('6246', range(1, 101))
print(f'6245 on-disk OCR: {d6245}/{t6245}')
print(f'6246 on-disk OCR: {d6246}/{t6246}')
