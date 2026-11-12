#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TPXO9-atlas-v3, TPXO10-atlas-v2 und FES2022 gegen gemessene Bestandssaetze (Oliver 12.11.2026: neue Tidenmodelle).

Vergleichssaetze: Messfits (harmonics_utide_observations) und TICON. Mass wie py/fes_kuestentyp.py: Kurvenabstand
health_check.curve_diff ueber M2/S2/K1/O1/N2 (relativ zur Tide, %), dazu M2-Phase in Minuten. Modellwert = naechste
Wasserzelle (TPXO: py/tpxo.py, 1/30 Grad; FES: fes_kuestentyp.fes_dazu, 1/30 Grad extrapoliert).
Gruppen: Kuestentyp (fes_kuestentyp.typ), Abstand zur Modell-Wasserzelle, Grossregion.
Schreibt harmonics/help/tpxo_vergleich.csv.
Usage: venv/bin/python py/tpxo_vergleich.py [--max N]
"""
import cmath
import csv
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_kuestentyp as F                                         # noqa: E402
import health_check as H                                           # noqa: E402
import tpxo as T                                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/tpxo_vergleich.csv')
REF = ('utide_observations', '/ticon/')


def rec(w):
    z = {c: cmath.rect(w[c][0], -math.radians(w[c][1])) for c in H.MAIN}
    return dict(z=z, tot=sum(abs(z[c]) for c in H.MAIN))


def m2min(a, b):
    if abs(a['z']['M2']) < 0.05 or abs(b['z']['M2']) < 0.05:
        return None
    return math.degrees(cmath.phase(b['z']['M2'] / a['z']['M2'])) / H.SPEED['M2'] * 60   # + = Modell spaeter


def region(r):
    la, lo = r['lat'], ((r['lon'] + 180) % 360) - 180
    if 30 < la < 72 and -30 < lo < 45:
        return 'Europa'
    if la > 15 and -170 < lo < -50:
        return 'Nordamerika'
    if la <= 15 and -120 < lo < -30:
        return 'Mittel-/Suedamerika'
    if -40 < la < 37 and -20 < lo < 60:
        return 'Afrika/Nahost'
    if la > -12 and 60 <= lo < 150:
        return 'Asien'
    if la <= -12 and 100 < lo < 180:
        return 'Australien/NZ'
    return 'Pazifik/Sonst'


def main(argv):
    R = [r for r in H.load_records() if not r['current'] and r['lat'] is not None and any(k in r['file'] for k in REF)
         and r.get('tot', 0) >= 0.1]
    if '--max' in argv:
        R = R[::max(1, len(R) // int(argv[argv.index('--max') + 1]))]
    F.fes_dazu(R)
    zeilen = []
    for n, r in enumerate(R):
        e = dict(datei=os.path.basename(r['file']), name=r['name'], lat='%.4f' % r['lat'], lon='%.4f' % r['lon'],
                 typ=F.typ(r), region=region(r), fes_km='%.1f' % max(r['fes_wasser_km'], r['fes_ersatz_km']))
        e['fes_pct'] = 100 * H.curve_diff(r, r['fes_rec'])[1]
        e['fes_min'] = m2min(r, r['fes_rec'])
        for m in ('9', '10'):
            w, dk = T.konstanten(m, r['lat'], r['lon'])
            if not w:
                e['tpxo%s_pct' % m], e['tpxo%s_min' % m], e['tpxo%s_km' % m] = None, None, None
                continue
            tr = rec(w)
            e['tpxo%s_pct' % m] = 100 * H.curve_diff(r, tr)[1]
            e['tpxo%s_min' % m] = m2min(r, tr)
            e['tpxo%s_km' % m] = '%.1f' % dk
        zeilen.append(e)
        if n % 500 == 0:
            print('  %d/%d' % (n, len(R)), flush=True)

    def tab(titel, schl):
        print('\n%s\n%-22s %5s | %-17s | %-17s | %-17s | %s' % (titel, '', 'n', 'FES  Med  P90 min', 'TPXO9 Med P90 min', 'TPXO10 Med P90 min', 'bester'))
        G = {}
        for z in zeilen:
            if z['tpxo9_pct'] is not None and z['tpxo10_pct'] is not None:
                G.setdefault(schl(z), []).append(z)
        for g in sorted(G, key=lambda g: -len(G[g])):
            zs = G[g]
            s = []
            for m in ('fes', 'tpxo9', 'tpxo10'):
                v = np.array([z[m + '_pct'] for z in zs])
                mi = [abs(z[m + '_min']) for z in zs if z[m + '_min'] is not None]
                s.append('%4.1f %5.1f %4.0f' % (np.median(v), np.percentile(v, 90), np.median(mi) if mi else float('nan')))
            best = [min(('fes', 'tpxo9', 'tpxo10'), key=lambda m: z[m + '_pct']) for z in zs]
            print('%-22s %5d | %s | %s | %s | F%3.0f%% T9%3.0f%% T10%3.0f%%' % (g[:22], len(zs), *s,
                  *(100 * best.count(m) / len(best) for m in ('fes', 'tpxo9', 'tpxo10'))))
    tab('Alle', lambda z: 'alle')
    tab('Kuestentyp', lambda z: z['typ'])
    tab('Region', lambda z: z['region'])
    tab('Abstand Messpunkt-Wasserzelle (max FES/TPXO10)', lambda z: '<2 km' if max(float(z['fes_km']), float(z['tpxo10_km'])) < 2 else ('2-5 km' if max(float(z['fes_km']), float(z['tpxo10_km'])) < 5 else '>=5 km'))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        for z in zeilen:
            w.writerow({k: ('%.1f' % v if isinstance(v, float) else ('' if v is None else v)) for k, v in z.items()})
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
