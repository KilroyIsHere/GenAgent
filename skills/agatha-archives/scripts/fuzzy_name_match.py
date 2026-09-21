#!/usr/bin/env python3
"""Fuzzy surname/first-name matcher for an already-OCR'd register corpus.

Re-scans the same .ocr.txt files a fixed-pattern sweep already produced (no new
OCR) and finds surname-slot tokens a prefix-anchored regex could not: wrong
leading letter, inserted/dropped letters, scribe-attached particles.

Usage:
  python3 fuzzy_name_match.py \
      --surnames zorokens,zorrokens \
      --firstnames joannes,petri,petrus \
      --window 1715 1741 \
      --ocr-glob '/workspace/agatha/cache/volumes/*/pages/*.ocr.txt' \
      --out /workspace/agatha/lookup/fuzzy_results.json

Match key = first-name + fuzzy-surname + date; never surname alone.
Every hit is DOUBTFUL until a crop-verify of the line agrees.
"""
import argparse, glob, json, os, re, sys


def levenshtein(a, b):
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j-1] + 1,
                           prev[j-1] + (ca != cb)))
        prev = cur
    return prev[-1]


def clean(tok):
    t = re.sub(r'[^a-zA-Z]', '', tok).lower()
    for pre in ('vd', 'van', 'den', 'de'):
        if t.startswith(pre) and len(t) > len(pre) + 2:
            t = t[len(pre):]
            break
    return t


def score_surname(tok, targets):
    """Best (dist, kind, ref) vs target surnames, else None.
    Whole-token Levenshtein <= 3, plus a distinctive-stem CONTAINS pass so
    'van Zorokens'/'vzorokens'/'Zoorekens' still fire."""
    t = clean(tok)
    if len(t) < 5:
        return None
    best = None
    for ref in targets:
        d = levenshtein(t, ref)
        if d <= 3 and (best is None or d < best[0]):
            best = (d, 'edit', ref)
    for ref in targets:
        stem = ref[:5]            # 'zorok' / 'zorro'… keep >=5 chars
        if stem in t and (best is None or best[0] > 1):
            cand = (1, 'stem', ref)   # stem hit = distance-1 equivalent
            if best is None or cand[0] < best[0]:
                best = cand
    return best


def year_of(text, lo, hi):
    m = re.findall(r'\b(1[5-8]\d\d)\b', text)
    return [int(y) for y in m if lo <= int(y) <= hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--surnames', required=True, help='comma list of target surnames')
    ap.add_argument('--firstnames', default='', help='comma list of target given names (confirmation signal)')
    ap.add_argument('--window', nargs=2, type=int, required=True, help='YYYY lo hi')
    ap.add_argument('--ocr-glob', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    surn = [s.strip().lower() for s in args.surnames.split(',') if s.strip()]
    firsts = [f.strip().lower() for f in args.firstnames.split(',') if f.strip()]
    lo, hi = args.window
    files = sorted(glob.glob(args.ocr_glob))
    print(f'{len(files)} OCR files, surnames={surn}', file=sys.stderr)

    hits = []
    for fp in files:
        try:
            text = open(fp, errors='ignore').read()
        except OSError:
            continue
        yrs = year_of(text, lo, hi)
        for m in re.finditer(r'\b([A-Z][a-zA-Z.\'’-]{2,40})\b', text):
            tok = m.group(1)
            s = score_surname(tok, surn)
            if not s:
                continue
            line = text[m.start(): m.start()+120].split('\n')[0].strip()
            first_match = any(levenshtein(clean(x), fn) <= 3
                              for x in re.findall(r"\b([A-Za-z.']+?)\b", line)
                              for fn in firsts) if firsts else None
            hits.append({
                'file': fp,
                'token': tok, 'dist': s[0], 'kind': s[1], 'ref': s[2],
                'line': line, 'years': yrs, 'first_match': first_match,
            })
    json.dump({'surnames': surn, 'firstnames': firsts,
               'window': [lo, hi], 'files': len(files), 'hits': hits},
              open(args.out, 'w'), indent=1)
    print(f'{len(hits)} fuzzy hits -> {args.out}', file=sys.stderr)
    print(f'{len(hits)} hits (DOUBTFUL until crop-verify)', file=sys.stdout)


if __name__ == '__main__':
    main()
