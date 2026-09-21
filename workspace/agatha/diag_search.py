#!/usr/bin/env python3
"""Diagnose the agatha search-form POST: fresh cookie jar, GET main page,
POST #PR_FORM fields, inspect what comes back (dump body + look for
results markers)."""
import sys, re, urllib.request, urllib.parse, http.cookiejar

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

def make_client():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def main():
    op = make_client()
    def get(url, referer=None):
        req = urllib.request.Request(url)
        req.add_header('User-Agent', UA)
        if referer: req.add_header('Referer', referer)
        return op.open(req, timeout=60).read().decode('utf-8','replace')
    def post(url, data, referer):
        body = data.encode()
        req = urllib.request.Request(url, data=body)
        req.add_header('User-Agent', UA)
        req.add_header('Referer', referer)
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        req.add_header('Origin', 'https://agatha.arch.be')
        return op.open(req, timeout=60).read().decode('utf-8','replace')

    # 1. GET main search page (seeds session)
    home = get('https://agatha.arch.be/en/search/genealogie/')
    print('main page bytes:', len(home), 'PR_FORM:', 'PR_FORM' in home)
    open('/workspace/agatha/lookup/_diag_home.html','w').write(home)

    # 2. POST the form as the browser would (full field set incl. empty ones)
    fields = [
        ('PLACEPOINT_ID_PR', '12'),
        ('CURRENT_NAME_PR', 'Antwerpen'),
        ('PLACE_PR', ''),
        ('PARISH_ID[]', '13'),
        ('TYPEACTES_PR[]', '1'),
        ('TYPEINDEX_PR[]', '1'),
        ('CHOOSE_DATE_PERIODE_PR', ''),
        ('SHOW_PERIODE_PR', ''),
        ('exactYear_PR', ''),
        ('EDITORIALFORM_PR', ''),
    ]
    data = urllib.parse.urlencode(fields)
    print('POSTing:', data)
    res = post('https://agatha.arch.be/en/search/genealogie/results/', data,
               'https://agatha.arch.be/en/search/genealogie/')
    print('results bytes:', len(res))
    open('/workspace/agatha/lookup/_diag_results.html','w').write(res)
    m = re.search(r'(\d+)\s*of\s*(\d+)\s*results', res)
    print('results line:', m.group(0) if m else None)
    ids = re.findall(r'gotoClick\((\d+)\)', res)
    print('gotoClick ids:', ids[:20])
    txt = re.sub(r'<script.*?</script>', '', res, flags=re.S)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt)
    print('text:', txt[:1500])

if __name__ == '__main__':
    main()
