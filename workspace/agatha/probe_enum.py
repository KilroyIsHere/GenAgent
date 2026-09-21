#!/usr/bin/env python3
"""Probe one parish's results page and dump parsed rows + raw HTML for inspection."""
import importlib.util, sys, agatha_cache as ac
spec = importlib.util.spec_from_file_location('e', '/workspace/agatha/enum_antwerp_baptism.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
pid, kind = sys.argv[1], sys.argv[2]
html = m.search(pid, kind)
open(f'/workspace/agatha/lookup/_probe_{pid}_{kind}.html', 'w').write(html)
tot, rows = m.parse_results(html)
print(f'saved {len(html)} bytes; total={tot} rows={len(rows)}')
for r in rows:
    print(' ', r['bookpart'], '|', r['label'][:110])
