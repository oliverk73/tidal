#!/usr/bin/env python3
"""Audit the Bangladesh records that were fitted with cosine interpolation.

Refits Payra (5 gauges) and Mongla (2 gauges) twice from the same source
tables -- once the old way (half cosine only) and once with shape-corrected
interpolation -- and reports both the overtide content and the round-trip
error against the printed table.

Usage: venv/bin/python py/audit_cosine_bangladesh.py
"""
import sys

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
sys.path.insert(0, '/home/oliver/weather/py')
sys.path.insert(0, '/home/oliver/weather/batch')

from datetime import timedelta

import shape_interp as S

PAYRA_PDF = '/home/oliver/weather/tide_tables/bangladesh/payra/ppa_10.pdf'
PAYRA_BASE = '/home/oliver/weather/tide_tables/bangladesh/payra'
MONGLA_PDF = ('/home/oliver/weather/tide_tables/bangladesh/'
              'tide_Table_pussur_river_mongla.pdf')
TZ_OFFSET_H = 6  # Bangladesh Standard Time (UTC+6, no DST)

# code -> (display name, lat, group-specific loader argument)
PAYRA = {
    'charipara':  ('Charipara (Rabnabad Channel)', 21.951389, 2025),
    'kaurchar':   ('Kauar Char (Rabnabad Channel)', 21.832778, 2025),
    'monopile-1': ('Monopile-1 (Rabnabad Channel)', 21.621389, 2025),
    'monopile-2': ('Monopile-2 (Rabnabad Channel)', 21.457778, 2025),
    'andermanik': ('Andharmanik (Rabnabad Channel)', 21.941111, 2023),
}
MONGLA = {
    'mongla':      ('Mongla', 22.533280, [0, 1, 2]),
    'sundarikota': ('Sundarikota', 22.126667, [6, 7, 8]),
}


def load_payra(code, year):
    from parse_payra_pdf import parse_station, parse_andermanik
    if code == 'andermanik':
        return parse_andermanik(PAYRA_BASE)
    return parse_station(PAYRA_PDF, code, year)


def load_mongla(pages):
    from parse_mpa_tide_pdf import parse_station
    return parse_station(MONGLA_PDF, pages)


def to_utc(hwlw):
    pts = sorted((dt - timedelta(hours=TZ_OFFSET_H), h) for dt, h in hwlw)
    out = [pts[0]]
    for p in pts[1:]:
        if p[0] > out[-1][0]:
            out.append(p)
    return out


def one(label, lat, pts):
    """Fit with 0 rounds (old) and SHAPE_ROUNDS (new); print the comparison."""
    row = {'name': label, 'n': len(pts)}
    for tag, rounds in (('alt', 0), ('neu', S.SHAPE_ROUNDS)):
        coef, _, _, _, r2, rms = S.fit(pts, lat, rounds=rounds)
        m2 = S.amp(coef, 'M2')
        m4 = S.amp(coef, 'M4')
        m6 = S.amp(coef, 'M6')
        dt, dh, n = S.roundtrip(coef, pts)
        row[tag] = dict(m2=m2[0], g2=m2[1], m4=m4[0], g4=m4[1], m6=m6[0],
                        r2=r2, rms=rms, dt=dt, dh=dh, n=n)
    return row


def main():
    rows = []
    for code, (name, lat, year) in PAYRA.items():
        pts = to_utc(load_payra(code, year))
        rows.append(one(name, lat, pts))
        print('.', end='', flush=True)
    for code, (name, lat, pages) in MONGLA.items():
        pts = to_utc(load_mongla(pages))
        rows.append(one(name, lat, pts))
        print('.', end='', flush=True)
    print()

    hdr = (f"{'Pegel':34s} {'n':>5s} | {'M4/M2 alt':>9s} {'neu':>7s} "
           f"{'Fkt':>5s} | {'M6/M2 alt':>9s} {'neu':>7s} | "
           f"{'Buch alt':>14s} {'Buch neu':>14s}")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        a, b = r['alt'], r['neu']
        ra = a['m4'] / a['m2'] if a['m2'] else 0
        rb = b['m4'] / b['m2'] if b['m2'] else 0
        s6a = a['m6'] / a['m2'] if a['m2'] else 0
        s6b = b['m6'] / b['m2'] if b['m2'] else 0
        print(f"{r['name']:34s} {r['n']:5d} | {ra:9.4f} {rb:7.4f} "
              f"{(rb / ra if ra else 0):5.2f} | {s6a:9.4f} {s6b:7.4f} | "
              f"{a['dt']:5.1f}min {a['dh']:5.3f}m {b['dt']:5.1f}min "
              f"{b['dh']:5.3f}m")
    print()
    for r in rows:
        a, b = r['alt'], r['neu']
        print(f"{r['name']:34s} M2 {a['m2']:.3f}->{b['m2']:.3f} m  "
              f"g(M2) {a['g2']:6.1f}->{b['g2']:6.1f}  "
              f"M4 {a['m4']:.4f}->{b['m4']:.4f} m  "
              f"g(M4) {a['g4']:6.1f}->{b['g4']:6.1f}")


if __name__ == '__main__':
    main()
