#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repariert NOAA-Buchsaetze mit verdrehter Tagestide (29.10.2026).

Anlass: Old Tracadie Gully (Uebertragung von Pictou, dt=+390 min). Table 2 legt
EINEN Zeitversatz auf beide Baender; bei grossem dt liegt die Halbtagestide fast
richtig (6,5 h ~ halbe Periode), die Tagestide aber um eine Vierteldrehung daneben
(Memory noaa-uebertragung-ein-zeitversatz).

Erkennung je NOAA-Buchsatz gegen den naechsten Nicht-NOAA-Satz bis 40 km:
  |dM2| < 30 Grad, |dK1| und |dO1| > 40 Grad mit gleichem Vorzeichen.
Repariert wird nur, wenn
  - FES2022 dem Nachbarn recht gibt (NOAA-FES mehr als doppelt so weit weg wie Nachbar-FES, +30 Grad),
  - K1 und O1 denselben Zeitfehler ergeben (Unterschied < 1,5 h).
Dann werden alle Tagestiden (Speed 12-17 Grad/h) um diesen Zeitfehler verschoben;
Amplituden, Halbtagestide und Rest bleiben. Saetze mit Notiz 'Tagestide repariert' bleiben aussen vor.

Usage: venv/bin/python py/noaa_tagestide_reparieren.py [--schreiben]
"""
from __future__ import annotations

import bisect
import cmath
import math
import os
import sys
from datetime import date

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402
from noaa_nachbar_abgleich import ist_noaa_buch                    # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR                      # noqa: E402
import xtide_modell as X                                           # noqa: E402

SP = {'K1': 15.0410686, 'O1': 13.9430356}


def ph(a, b):
    return ((math.degrees(cmath.phase(a / b)) + 180) % 360) - 180 if a and b else float('nan')


def main(argv):
    schreiben = '--schreiben' in argv
    R = [r for r in load_records() if not r['current'] and r['lat'] is not None]
    ds = {c: nc.Dataset(os.path.join(FES_DIR, f'{c}_fes2022.nc')) for c in ('k1', 'o1')}

    def fz(c, la, lo):
        a, g = sample(ds[c], la, lo)
        return a * cmath.exp(-1j * math.radians(g)) if a else None

    ref = sorted([r for r in R if not ist_noaa_buch(r['file'])], key=lambda r: r['lat'])
    lats = [r['lat'] for r in ref]
    plan = {}
    for r in R:
        if not ist_noaa_buch(r['file']):
            continue
        z = r['z']
        if abs(z.get('K1', 0)) < 0.04 or abs(z.get('O1', 0)) < 0.03 or abs(z.get('M2', 0)) < 0.05:
            continue
        i, j = bisect.bisect_left(lats, r['lat'] - 0.4), bisect.bisect_right(lats, r['lat'] + 0.4)
        k = [(d, g) for d, g in sorted(((km(r, g), g) for g in ref[i:j]), key=lambda x: x[0])
             if d <= 40 and abs(g['z'].get('K1', 0)) > 0.03 and abs(g['z'].get('O1', 0)) > 0.02 and abs(g['z'].get('M2', 0)) > 0.04]
        if not k:
            continue
        d, g = k[0]
        dm, dk, do = ph(z['M2'], g['z']['M2']), ph(z['K1'], g['z']['K1']), ph(z['O1'], g['z']['O1'])
        if not (abs(dk) > 40 and abs(do) > 40 and dk * do > 0 and abs(dm) < 30):
            continue
        fk, fo = fz('k1', r['lat'], r['lon']), fz('o1', r['lat'], r['lon'])
        nk, no, gk, go = ph(z['K1'], fk), ph(z['O1'], fo), ph(g['z']['K1'], fk), ph(g['z']['O1'], fo)
        hk, ho = dk / SP['K1'], do / SP['O1']
        grund = None
        if math.isnan(nk):
            grund = 'ohne FES'
        elif not abs(nk) + abs(no) > 2 * (abs(gk) + abs(go)) + 30:
            grund = 'FES gibt dem Nachbarn nicht recht'
        elif abs(hk - ho) >= 1.5:
            grund = 'K1/O1 uneinig (%.1f / %.1f h)' % (hk, ho)
        if grund:
            print('  bleibt  %-50s %s' % (r['name'][:50], grund))
            continue
        plan.setdefault(r['file'], []).append((r, g, d, (hk + ho) / 2))
    n = 0
    for f, liste in plan.items():
        speed = X.kopf_lesen(f)[1]
        T = open(f, encoding='latin-1').read().split('\n')
        for r, g, d, h in liste:
            name = r['name']
            assert T.count(name) == 1, name
            i = T.index(name)
            if any('Tagestide repariert' in T[q] for q in range(max(0, i - 40), i)):
                continue
            k, geaendert = i + 3, []
            while k < len(T) and T[k].strip() and not T[k].startswith('#'):
                p = T[k].split()
                if len(p) == 3 and p[0] in speed and 12 < speed[p[0]] < 17:
                    alt = float(p[2])
                    T[k] = '%-15s %s  %.2f' % (p[0], p[1], (alt + h * speed[p[0]]) % 360)
                    geaendert.append(p[0])
                k += 1
            note = ('# note: %s Tagestide repariert: %+.1f h gegen %s (%.0f km, FES bestaetigt), '
                    'Uebertragung mit einem dt fuer beide Baender.' % (date.today().isoformat(), h, g['name'].split(',')[0], d))
            T.insert(i, note[:195])
            n += 1
            print('  %-50s %+5.1f h  %-30s %4.1f km  %s' % (name[:50], h, g['name'][:30], d, ' '.join(geaendert)))
        if schreiben:
            open(f, 'w', encoding='latin-1', newline='').write('\n'.join(T))
    print('%d Saetze %s' % (n, 'repariert' if schreiben else 'waeren zu reparieren'))


if __name__ == '__main__':
    main(sys.argv[1:])
