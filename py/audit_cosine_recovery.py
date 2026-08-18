#!/usr/bin/env python3
"""Controlled test: how much of a known M4/M6 does a HW/LW fit get back?

Takes stations whose harmonic constants come from real gauge records, has
XTide print a year of HW/LW from them -- rounded to the minute and the
centimetre, exactly as a printed table would be -- then fits those extremes
back with cosine interpolation and with shape-corrected interpolation. The
true answer is known, so the recovery rate is measured, not guessed.

Usage: venv/bin/python py/audit_cosine_recovery.py [tcd] [n_stations]
"""
import os
import re
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, '/home/oliver/weather/py')

import numpy as np
import shape_interp as S

TCD = sys.argv[1] if len(sys.argv) > 1 else \
    '/usr/share/xtide/harmonics_utide_observations.tcd'
TXT = ('/home/oliver/weather/harmonics/utide/'
       'harmonics_utide_observations.txt')
BEG, END = '2026-01-01 00:00', '2026-12-31 00:00'


def truth(path):
    """Station name -> (lat, constituent amplitudes) from the harmonics file."""
    L = open(path, encoding='iso-8859-1').read().split('\n')
    out = {}
    for k, line in enumerate(L):
        if not line.startswith('# !latitude'):
            continue
        j = k
        while j > 0 and L[j - 1].startswith('#'):
            j -= 1
        e = k
        while e < len(L) and L[e].startswith('#'):
            e += 1
        lat = float(re.search(r'-?\d+\.?\d*', line).group())
        c = {}
        for x in L[e + 3:e + 3 + 180]:
            p = x.split()
            if len(p) == 3 and p[0] != 'x':
                try:
                    c[p[0]] = float(p[1])
                except ValueError:
                    pass
        if c.get('M2', 0) > 0.05:
            out[L[e].strip()] = (lat, c)
    return out


def hwlw(name):
    """A year of HW/LW as XTide prints it: UTC, minute and centimetre."""
    env = dict(os.environ, HFILE_PATH=TCD)
    r = subprocess.run(['tide', '-l', name, '-b', BEG, '-e', END, '-m', 'p',
                        '-u', 'm', '-z', '-f', 'c'], capture_output=True,
                       text=True, env=env, timeout=300)
    pts = []
    for ln in r.stdout.splitlines():
        f = ln.split(',')
        if len(f) < 5 or f[-1] not in ('High Tide', 'Low Tide'):
            continue
        m = re.match(r'(\d+):(\d+) (AM|PM)', f[2])
        h = re.match(r'(-?[\d.]+) m', f[3])
        if not m or not h:
            continue
        hh = int(m.group(1)) % 12 + (12 if m.group(3) == 'PM' else 0)
        d = datetime.strptime(f[1], '%Y-%m-%d').replace(hour=hh,
                                                        minute=int(m.group(2)))
        pts.append((d, float(h.group(1))))
    return sorted(set(pts))


def main():
    n_want = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    t = truth(TXT)
    # spread over the range of shallow-water content, skip the flat ones
    cand = [(c.get('M4', 0) / c['M2'], n, lat, c) for n, (lat, c) in t.items()
            if c.get('M4', 0) / c['M2'] > 0.01]
    cand.sort(reverse=True)
    pick = [cand[int(i * (len(cand) - 1) / (n_want - 1))] for i in range(n_want)]

    hdr = (f"{'Station':34s} {'M4/M2 wahr':>10s} {'kosinus':>8s} {'shape':>8s} |"
           f" {'Ausbeute kos':>12s} {'shape':>7s} | {'M6 kos':>7s} {'shape':>7s}")
    print(hdr)
    print('-' * len(hdr))
    rk, rs, r6k, r6s = [], [], [], []
    for ratio, name, lat, c in pick:
        try:
            pts = hwlw(name)
        except Exception as exc:
            print(f'{name[:34]:34s} {exc}')
            continue
        if len(pts) < 400:
            print(f'{name[:34]:34s} nur {len(pts)} Extrema - uebersprungen')
            continue
        row = {}
        for tag, rounds in (('kos', 0), ('shp', S.SHAPE_ROUNDS)):
            coef, *_ = S.fit(pts, lat, rounds=rounds)
            row[tag] = (S.amp(coef, 'M2')[0], S.amp(coef, 'M4')[0],
                        S.amp(coef, 'M6')[0])
        t4 = c.get('M4', 0) / c['M2']
        t6 = c.get('M6', 0) / c['M2']
        f4k = row['kos'][1] / row['kos'][0]
        f4s = row['shp'][1] / row['shp'][0]
        f6k = row['kos'][2] / row['kos'][0]
        f6s = row['shp'][2] / row['shp'][0]
        rk.append(f4k / t4)
        rs.append(f4s / t4)
        if t6 > 0.002:
            r6k.append(f6k / t6)
            r6s.append(f6s / t6)
        print(f"{name[:34]:34s} {t4:10.4f} {f4k:8.4f} {f4s:8.4f} | "
              f"{f4k / t4:11.0%} {f4s / t4:6.0%} | "
              f"{(f6k / t6 if t6 > 0.002 else float('nan')):6.0%} "
              f"{(f6s / t6 if t6 > 0.002 else float('nan')):6.0%}")
    if rk:
        print(f"\nMedian Ausbeute M4: kosinus {np.median(rk):.0%}  "
              f"shape-korrigiert {np.median(rs):.0%}")
    if r6k:
        print(f"Median Ausbeute M6: kosinus {np.median(r6k):.0%}  "
              f"shape-korrigiert {np.median(r6s):.0%}")


if __name__ == '__main__':
    main()
