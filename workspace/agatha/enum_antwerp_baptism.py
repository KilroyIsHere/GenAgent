#!/usr/bin/env python3
"""Enumerate agatha results (baptism indexes TYPEINDEX_PR=1 and registers
TYPEACTES_PR=1) for every Antwerp parish. Saves JSON to
/workspace/agatha/lookup/antwerp_baptism_enumeration.json"""
import sys, os, re, json, time, urllib.request, urllib.parse

sys.path.insert(0, '/workspace/agatha')
import agatha_cache as ac

OUT = '/workspace/agatha/lookup/antwerp_baptism_enumeration.json'
ROSTER = {
    "9": "Begijnhof van Sint-Catharina",
    "10": "Gasthuis Sint-Elisabeth",
    "11": "Christelijke Gereformeerde Kerk",
    "12": "Klooster van de Karmelieten",
    "13": "Onze-Lieve-Vrouw",
    "14": "Onze-Lieve-Vrouw-Noord",
    "15": "Onze-Lieve-Vrouw-Zuid",
    "16": "San Felipe del Castilla",
    "17": "Sint-Andries",
    "18": "Sint-Catharina-op-het-Kiel",
    "19": "Sint-Jacobus",
    "20": "Sint-Joris",
    "21": "Sint-Laurentius",
    "22": "Sint-Michielsabdij",
    "23": "Sint-Philippus en Sint-Jacobus",
    "24": "Sint-Walburga",
    "25": "Sint-Willibrordus",
}

def fetch(url, referer, cookie, data=None):
    if data is None:
        body = None
    else:
        body = data.encode()
    req = urllib.request.Request(url, data=body, method='POST' if body else 'GET')
    req.add_header('Referer', referer)
    req.add_header('User-Agent', 'Mozilla/5.0')
    if cookie:
        req.add_header('Cookie', cookie)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:
            if attempt == 2:
                raise
            print(f"  retry {attempt+1} after {e}", flush=True)
            time.sleep(5)
            # cookie may be stale
            try:
                cookie = ac.cmd_ensure()
            except Exception:
                pass

def parse_results(html):
    """Return (total_count, rows). Each row: {label, bookpart, url}."""
    m = re.search(r'(\d+)\s*of\s*(\d+)\s*results', html)
    total = int(m.group(2)) if m else None
    rows = []
    # rows: <tr class="row-results"> ... gotoClick(BOOKPART_ID) or /genealogie/<id>
    for tr in re.findall(r'<tr[^>]*row-results[^>]*>(.*?)</tr>', html, re.S):
        idm = re.search(r'gotoClick\((\d+)\)', tr) or re.search(r'/genealogie/(\d+)', tr)
        label = re.sub(r'<[^>]+>', ' ', tr)
        label = re.sub(r'\s+', ' ', label).strip()
        rows.append({'bookpart': idm.group(1) if idm else None, 'label': label[:200]})
    return total, rows

def search(parish_id, kind):
    """kind: 'index' -> TYPEINDEX_PR only; 'register' -> TYPEACTES_PR only."""
    if kind == 'index':
        data = ('PLACEPOINT_ID_PR=12&CURRENT_NAME_PR=Antwerpen&PARISH_ID%5B%5D=' + parish_id +
                '&TYPEINDEX_PR%5B%5D=1&PER_PAGE=50')
    else:
        data = ('PLACEPOINT_ID_PR=12&CURRENT_NAME_PR=Antwerpen&PARISH_ID%5B%5D=' + parish_id +
                '&TYPEACTES_PR%5B%5D=1&PER_PAGE=50')
    return fetch('https://agatha.arch.be/en/search/genealogie/results/',
                 'https://agatha.arch.be/en/search/genealogie/',
                 ac.get_cookie(), data)

def main():
    cookie = ac.cmd_ensure()
    result = {'searched_at': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()),
              'note': 'PER_PAGE=50 requested; pagination fallback not yet implemented — verify total vs rows per parish'}
    for pid, name in ROSTER.items():
        entry = {'name': name, 'parish_id': pid}
        for kind in ('index', 'register'):
            try:
                html = search(pid, kind)
                total, rows = parse_results(html)
                entry[kind] = {'total': total, 'rows': rows}
                print(f"{pid} {name}: {kind} total={total} rows={len(rows)}", flush=True)
                # save raw for inspection if anything looks odd
                with open(f"/workspace/agatha/lookup/_enum_{pid}_{kind}.html", 'w') as f:
                    f.write(html)
            except Exception as e:
                entry[kind] = {'error': str(e)}
                print(f"{pid} {name}: {kind} ERROR {e}", flush=True)
            time.sleep(1)
        result[pid] = entry
        with open(OUT, 'w') as f:
            json.dump(result, f, indent=1)
    print("DONE", OUT)

if __name__ == '__main__':
    main()
