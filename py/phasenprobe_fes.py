#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zweiter Zeuge fuer py/phasenprobe.py: FES2022b direkt am Ort, fuer jede gemeldete Tide.

Eine Ziffer aendern trifft bei rund 20 Varianten und +-5 Grad oft zufaellig. Sicher ist nur, was
Altersprobe UND FES zugleich treffen, waehrend der alte Wert beide verfehlt.

Usage: venv/bin/python py/phasenprobe_fes.py   -> schreibt die Spalten fes, urteil in die CSV
"""
import csv
import os
import sys

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_ersatz_inseln as F                                       # noqa: E402
import phasenprobe as P                                             # noqa: E402
import xtide_modell as X                                            # noqa: E402

KOPF = X.kopf_lesen(os.path.join(P.ROOT, 'harmonics/classic/harmonics-2004-06-14_mod.txt'))
d = P.d


def main():
    z = list(csv.DictReader(open(P.AUS, encoding='utf-8')))
    ds = {}
    for r in z:
        t = r['tide']
        if t not in ds:
            ds[t] = nc.Dataset(os.path.join(F.FES_DIR, f'{F.stem(t)}_fes2022.nc'))
        pfad = os.path.join(P.ROOT, 'harmonics/classic', r['datei'])
        _z0, _w, _e, m = X.satz_lesen(pfad, r['name'])
        a, g = F.sample(ds[t], float(r['lat']), float(r['lon']))
        if a is None or a != a:
            r['fes'], r['fes_amp'], r['urteil'] = '', '', 'kein FES'
            continue
        lok = (g + KOPF[1][t] * m) % 360
        p = float(r['phase'])
        erw = [float(x) for x in r['erwartet'].split()]
        r['fes'] = f'{lok:.1f}'
        r['fes_amp'] = f'{a:.3f}'
        var = [v for v in P.varianten(p) if abs(d(v, lok)) < 8 and abs(d(v, erw[0])) < 8]
        alt_weg = abs(d(p, lok)) > 25
        r['aenderung'] = ' '.join(f'{v:.2f}' for v in var)
        r['urteil'] = ('Tippfehler' if var and alt_weg else
                       'falsch ohne Ziffer' if alt_weg and abs(d(lok, erw[0])) < 15 else
                       'FES stuetzt Bestand' if not alt_weg else 'unklar')
    felder = list(z[0]) + [k for k in ('fes_amp', 'urteil') if k not in z[0]]
    with open(P.AUS, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(z)
    import collections
    print(collections.Counter(r['urteil'] for r in z))
    for r in z:
        if r['urteil'] in ('Tippfehler', 'falsch ohne Ziffer'):
            print(f"{r['urteil'][:10]:10s} {r['name'][:40]:40s} {r['datei'][10:14]} {r['tide']:3s} a {r['amp_m']:>6s}/{r['fes_amp']:<6s} {r['phase']:>7s} erw {r['erwartet']:12s} fes {r['fes']:>6s} -> {r['aenderung']}")


if __name__ == '__main__':
    main()
