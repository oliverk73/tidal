#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Einzelne Phasen der ATT-Haupthaefen (Part III) richten (1.11.2026).

harmonics/help/phasenprobe_att_20261101.csv nennt Tiden, die neben der Altersprobe liegen. Geaendert wird nur,
wenn FES die Altersprobe auf 15 Grad bestaetigt, die alte Phase ueber 25 Grad neben FES liegt, die Amplitude
mindestens 5 cm betraegt und nur EINE Tide des Satzes betroffen ist (sonst eher Ortseigenheit oder Satzfehler).
Neue Phase: Mittel aus Altersprobe und FES, bei passender Ziffer diese.
"""
import collections
import csv
import os
import sys

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_ersatz_inseln as F                                       # noqa: E402
import phasenprobe as P                                             # noqa: E402
import xtide_modell as X                                            # noqa: E402

d = P.d
AUS = os.path.join(P.ROOT, 'harmonics/help/phasenprobe_att_20261101.csv')


def main():
    z = list(csv.DictReader(open(AUS, encoding='utf-8')))
    ds, kopf, tref = {}, {}, []
    for r in z:
        t, p = r['tide'], os.path.join(P.ROOT, 'harmonics/att', r['datei'])
        ds.setdefault(t, nc.Dataset(os.path.join(F.FES_DIR, f'{F.stem(t)}_fes2022.nc')))
        kopf.setdefault(p, X.kopf_lesen(p))
        m = X.satz_lesen(p, r['name'])[3]
        a, g = F.sample(ds[t], float(r['lat']), float(r['lon']))
        lok = (g + kopf[p][1][t] * m) % 360
        ph, erw = float(r['phase']), float(r['erwartet'].split()[0])
        if abs(d(ph, lok)) > 25 and abs(d(lok, erw)) <= 15 and float(r['amp_m']) >= 0.05:
            var = [v for v in P.varianten(ph) if abs(d(v, lok)) < 8 and abs(d(v, erw)) < 8]
            mitte = (lok + d(erw, lok) / 2) % 360
            tref.append((p, r['name'], t, ph, min(var, key=lambda v: abs(d(v, mitte))) if var else round(mitte), erw, lok))
    n = collections.Counter((x[0], x[1]) for x in tref)
    tref = [x for x in tref if n[(x[0], x[1])] == 1]
    print(len(tref), 'Phasen;', sum(1 for v in n.values() if v > 1), 'Saetze mit mehreren Tiden uebersprungen')
    for p in sorted({x[0] for x in tref}):
        t = open(p, encoding='iso-8859-1').read().split('\n')
        for _p, name, tide, alt, neu, erw, lok in (x for x in tref if x[0] == p):
            k = t.index(name)
            for j in range(k + 3, k + 178):
                f = t[j].split()
                if len(f) == 3 and f[0] == tide:
                    t[j] = f'{tide:<15s} {f[1]:>7s} {neu:7.2f}'
                    break
            i = k
            while not t[i].startswith('# !units'):
                i -= 1
            t[i:i] = [f'# note: 20261101 {tide}-Phase {alt:.0f} -> {neu:.0f}: Altersprobe {erw:.0f}, FES {lok:.0f} (py/att_phasen_zeugen.py).']
            print(f'{name[:42]:42s} {tide} {alt:.0f} -> {neu:.0f}')
        open(p, 'w', encoding='iso-8859-1').write('\n'.join(t))


if __name__ == '__main__':
    main()
