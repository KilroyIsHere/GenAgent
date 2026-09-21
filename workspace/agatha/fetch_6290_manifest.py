#!/usr/bin/env python3
"""Fetch + register 6290 (St-Joris baptisms 1712-1720) manifest."""
import sys, json
sys.path.insert(0, '/workspace/agatha')
import agatha_cache as ac

cookie = ac.cmd_ensure()
mu = ('https://agatha.arch.be/en//data/json/511/511_9000_000/'
      '511_9000_000_00148_000/511_9000_000_00148_000.json')
code, body = ac._curl_http(mu, cookie, 'https://agatha.arch.be/')
m = json.loads(body)
print('http', code)
print('label:', m.get('label'))
for s in m.get('seeAlso', []):
    print('date:', s.get('date'))
cv = m['sequences'][0]['canvases']
print('canvases:', len(cv))
ac.cmd_init('6290', mu, cookie,
            'Antwerpen Sint-Joris baptism register 1712-1720',
            '1712 - 1720', '20')
print('INIT DONE')
