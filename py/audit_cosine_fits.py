#!/usr/bin/env python3
"""Audit every record in harmonics_utide_tidetables.txt that was fitted with
plain cosine interpolation, by refitting it from its own source table.

For each station the source HW/LW table is loaded once and fitted twice: with
0 shape rounds (exactly the old method) and with shape_interp.SHAPE_ROUNDS.
Reported per station: M4/M2 and M6/M2 both ways, and the round-trip error
against the printed table both ways.

The round-trip is the honest measure. r2 against the interpolated series only
says how well the constants describe the filler that was invented for them --
a cosine fit scores beautifully on its own cosine.

Usage:
  venv/bin/python py/audit_cosine_fits.py <source> [--json OUT]
  <source> = argentina | chile | semar | cicese | morocco | all
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
sys.path.insert(0, '/home/oliver/weather/py')
sys.path.insert(0, '/home/oliver/weather/batch')

import shape_interp as S

HARM = ('/home/oliver/weather/harmonics/utide/'
        'harmonics_utide_tidetables.txt')
TT = Path('/home/oliver/weather/tide_tables')


# ---------------------------------------------------------------- the targets

def cosine_records():
    """Name, lat, lon and published M2/M4 of every cosine-fitted record."""
    L = open(HARM, encoding='iso-8859-1').read().split('\n')
    out = []
    for k, line in enumerate(L):
        if not line.startswith('# !latitude'):
            continue
        j = k
        while j > 0 and L[j - 1].startswith('#'):
            j -= 1
        e = k
        while e < len(L) and L[e].startswith('#'):
            e += 1
        hdr = '\n'.join(L[j:e])
        if 'cosine-interpolated' not in hdr:
            continue
        c = {}
        for l in L[e + 3:e + 3 + 180]:
            p = l.split()
            if len(p) == 3 and p[0] != 'x':
                try:
                    c[p[0]] = (float(p[1]), float(p[2]))
                except ValueError:
                    pass
        g = lambda pat: (re.search(pat, hdr).group(1).strip()
                         if re.search(pat, hdr) else '')
        out.append(dict(
            name=L[e].strip(), src=g(r'# source: (.*)'),
            country=g(r'# country: (.*)'),
            lat=float(g(r'# !latitude:\s*(-?[\d.]+)')),
            lon=float(g(r'# !longitude:\s*(-?[\d.]+)')),
            m2=c.get('M2', (0, 0))[0], m4=c.get('M4', (0, 0))[0],
            m6=c.get('M6', (0, 0))[0]))
    return out


# ---------------------------------------------------------------- the loaders
# each yields (label, lat, [(datetime_utc, height)])

def _dedupe(pts):
    pts = sorted(pts)
    out = [pts[0]]
    for p in pts[1:]:
        if p[0] > out[-1][0]:
            out.append(p)
    return out


def load_argentina():
    for f in sorted((TT / 'argentina/shn/parsed').glob('*.json')):
        d = json.loads(f.read_text())
        off = d['meta'].get('tz_offset_h', -3)
        pts = [(datetime.fromisoformat(t) - timedelta(hours=off), h)
               for t, h in d['entries']]
        if len(pts) < 200:
            continue
        yield d['name'], d['meta']['lat'], _dedupe(pts)


def load_chile():
    import batch_utide_shoa_chile as B
    for code, meta in B.STATIONS.items():
        d = TT / 'chile' / code
        files = sorted(d.glob('*.html')) if d.is_dir() else []
        if not files:
            continue
        ent = []
        for f in files:
            try:
                ent += B.parse_shoa_html(str(f))
            except Exception:
                pass
        if len(ent) < 200:
            continue
        pts = [(B.local_to_utc(dt), h) for dt, h in ent]
        yield meta[0], meta[1], _dedupe(pts)


def _pdf_group(subdir, parser, tz_h):
    for d in sorted((TT / subdir).iterdir()):
        pdfs = sorted(d.glob('*.pdf')) if d.is_dir() else []
        if not pdfs:
            continue
        ent, lat = [], None
        for p in pdfs:
            try:
                r = parser(str(p))
            except Exception:
                continue
            if isinstance(r, dict):
                lat = r.get('lat', lat)
                ent += r.get('entries', [])
            else:
                ent += r
        if len(ent) < 200 or lat is None:
            continue
        pts = [(dt - timedelta(hours=tz_h), h) for dt, h in ent]
        yield d.name, lat, _dedupe(pts)


def load_semar():
    from parse_semar_pdf import parse_pdf
    return _pdf_group('mexico_semar', parse_pdf, -6)


def load_cicese():
    from parse_cicese_pdf import parse_pdf
    return _pdf_group('mexico_cicese', parse_pdf, -6)


def load_morocco():
    from parse_anp_morocco_pdf import parse_pdf
    return _pdf_group('morocco_anp', parse_pdf, 1)


LOADERS = {'argentina': load_argentina, 'chile': load_chile,
           'semar': load_semar, 'cicese': load_cicese,
           'morocco': load_morocco}


# ------------------------------------------------------------------- the work

def compare(label, lat, pts):
    row = {'name': label, 'lat': lat, 'n': len(pts)}
    for tag, rounds in (('alt', 0), ('neu', S.SHAPE_ROUNDS)):
        coef, _, _, _, r2, rms = S.fit(pts, lat, rounds=rounds)
        dt, dh, n = S.roundtrip(coef, pts)
        row[tag] = dict(m2=S.amp(coef, 'M2')[0], g2=S.amp(coef, 'M2')[1],
                        m4=S.amp(coef, 'M4')[0], g4=S.amp(coef, 'M4')[1],
                        m6=S.amp(coef, 'M6')[0], r2=r2, rms=rms,
                        dt=dt, dh=dh, n=n)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source')
    ap.add_argument('--json')
    a = ap.parse_args()
    names = list(LOADERS) if a.source == 'all' else [a.source]

    rows = []
    for src in names:
        for label, lat, pts in LOADERS[src]():
            try:
                r = compare(label, lat, pts)
            except Exception as exc:
                print(f'  {label}: {exc}', file=sys.stderr)
                continue
            r['source'] = src
            rows.append(r)
            print('.', end='', flush=True)
    print()

    hdr = (f"{'Pegel':32s} {'n':>5s} | {'M4/M2 alt':>9s} {'neu':>7s} {'Fkt':>5s}"
           f" | {'Buch alt':>13s} | {'Buch neu':>13s}")
    print(hdr)
    print('-' * len(hdr))
    for r in sorted(rows, key=lambda x: -(x['neu']['m4'] / (x['neu']['m2'] or 1))):
        p, q = r['alt'], r['neu']
        ra = p['m4'] / p['m2'] if p['m2'] else 0
        rb = q['m4'] / q['m2'] if q['m2'] else 0
        print(f"{r['name'][:32]:32s} {r['n']:5d} | {ra:9.4f} {rb:7.4f} "
              f"{(rb / ra if ra else 0):5.2f} | {p['dt']:5.1f}min {p['dh']:5.3f}m"
              f" | {q['dt']:5.1f}min {q['dh']:5.3f}m")

    if rows:
        import statistics as st
        for tag in ('alt', 'neu'):
            v = [r[tag]['m4'] / r[tag]['m2'] for r in rows if r[tag]['m2'] > 0.05]
            d = [r[tag]['dh'] for r in rows]
            print(f"\n{tag}: Median M4/M2 = {st.median(v):.4f}   "
                  f"Median Buch-Hoehenfehler = {st.median(d):.3f} m")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))


if __name__ == '__main__':
    main()
