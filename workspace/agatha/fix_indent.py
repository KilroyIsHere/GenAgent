#!/usr/bin/env python3
"""Normalize continuation indent of SKILL.md section 5 to exactly 3 spaces."""
import re
p = '/opt/data/skills/agatha-genealogy/SKILL.md'
lines = open(p).read().split('\n')
for i in range(173, 197):
    ln = lines[i]
    if ln:
        lines[i] = '   ' + re.sub(r'^\s+', '', ln)
open(p, 'w').write('\n'.join(lines))
print('normalized to 3-space indent')
