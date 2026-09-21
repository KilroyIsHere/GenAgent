#!/usr/bin/env python3
import sys, os
sys.path.insert(0,'/workspace/agatha'); sys.path.insert(0,'/workspace/agatha/runs/frederic_zorokens')
import importlib, p5_run; importlib.reload(p5_run)

os.makedirs('/tmp/p5t/6999/pages', exist_ok=True)
grid=list(range(1,71,4))   # 1,5,9,...,69

def set_years(pages):
    for p in grid:
        for s in ('L','R'):
            open(f'/tmp/p5t/6999/pages/{p:03d}_{s}.ocr.txt','w').write('')
    for p,y in pages:
        for s in ('L','R'):
            open(f'/tmp/p5t/6999/pages/{p:03d}_{s}.ocr.txt','w').write(f'{y}\n{y}\n')

old=p5_run.PAGE_DIR; p5_run.PAGE_DIR='/tmp/p5t'

# Case A: chronological, years straddle the window, in-window confirmed on grid
# grid pages: p1=1650 p5=1655 p9=1660 p13=1665 p17=1670 p21=1675 ... p69=1720
set_years([(1,1650),(5,1655),(9,1660),(13,1665),(17,1670),(21,1675),(25,1680),
           (29,1685),(33,1690),(37,1695),(41,1700),(45,1705),(49,1710),(53,1715),
           (57,1718),(61,1720),(65,1722),(69,1724)])
b,fb=p5_run.estimate_band('6999',grid,70,1667,1712)
print("A chronological straddle:", b, "fb", fb, "-> expect band ~[11,55], fb False")
assert fb is False and b[0]>=1 and b[1]<=70 and b[0]<b[1]

# Case B: no years at all
for p in grid:
    for s in ('L','R'):
        open(f'/tmp/p5t/6999/pages/{p:03d}_{s}.ocr.txt','w').write('x y z\n')
b,fb=p5_run.estimate_band('6999',grid,70,1667,1712)
print("B no-years:", b, "fb", fb, "-> expect [1,70] fb True")
assert b==[1,70] and fb is True

# Case C: whole volume in-window
set_years([(1,1690),(5,1690),(9,1695),(13,1695),(17,1700),(21,1700),(25,1705),
           (29,1705),(33,1708),(37,1708),(41,1710),(45,1710),(49,1712),
           (53,1712),(57,1692),(61,1692),(65,1701),(69,1701)])
b,fb=p5_run.estimate_band('6999',grid,70,1667,1712)
print("C whole-in-window:", b, "fb", fb, "-> expect [1,70] fb False")
assert b==[1,70] and fb is False

# Case D: only one in-window grid sample (thin) -> whole volume
set_years([(1,1650),(5,1655),(9,1660),(13,1690),(17,1655),(21,1655),(25,1660),
           (29,1660),(33,1655),(37,1660),(41,1655),(45,1660),(49,1655),
           (53,1650),(57,1650),(61,1650),(65,1650),(69,1650)])
# only p13 (1690) is in-window
b,fb=p5_run.estimate_band('6999',grid,70,1667,1712)
print("D thin single-in-window:", b, "fb", fb, "-> expect [1,70] fb True")
assert b==[1,70] and fb is True
p5_run.PAGE_DIR=old
print("ALL estimate_band TESTS PASSED")
