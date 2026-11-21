#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WebTide-Gebiete gegen den Bestand pruefen (21.11.2026): M2 Wasserstand (s2c) und Strom (v2c, Hauptachse) am
naechsten Modellknoten (<= 1 km, nass) gegen unsere Saetze. Usage: venv/bin/python py/webtide_pruefen.py gebiet ..."""
import cmath
import glob
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, 'quellen/tidal_streams/Canada_WebTide')


def zeilen(p, n):
    out = []
    for z in open(p, encoding='latin-1'):
        t = z.split()
        if len(t) == n:
            try:
                out.append([float(x) for x in t])
            except ValueError:
                pass
    return np.array(out)


def gebiet(g):
    d = os.path.join(W, g)
    nod = [p for p in glob.glob(d + '/*.nod') if 'boundary' not in p][0]
    n = zeilen(nod, 3)
    bat = zeilen(glob.glob(d + '/*.bat')[0], 2)
    tief = np.full(len(n), np.nan)
    tief[(bat[:, 0] - 1).astype(int)] = bat[:, 1]
    out = dict(lat=n[:, 2], lon=n[:, 1], tief=tief, s={}, v={})
    for p in glob.glob(d + '/*.barotropic.s2c'):
        k = os.path.basename(p).split('.')[0]
        s = zeilen(p, 3)
        if s.ndim != 2:
            continue
        a = np.full(len(n), np.nan, complex)
        a[(s[:, 0] - 1).astype(int)] = s[:, 1] * np.exp(-1j * np.radians(s[:, 2]))
        out['s'][k] = a
    for p in glob.glob(d + '/*.barotropic.v2c'):
        k = os.path.basename(p).split('.')[0]
        v = zeilen(p, 5)
        if v.ndim != 2:
            continue
        U = np.full(len(n), np.nan, complex)
        V = np.full(len(n), np.nan, complex)
        i = (v[:, 0] - 1).astype(int)
        U[i] = v[:, 1] * np.exp(-1j * np.radians(v[:, 2]))
        V[i] = v[:, 3] * np.exp(-1j * np.radians(v[:, 4]))
        out['v'][k] = (U, V)
    return out


def main(argv):
    import health_check as H
    import xtide_modell as X
    from scipy.spatial import cKDTree
    R = [r for r in H.load_records() if r['lat'] is not None]
    for g in argv:
        G = gebiet(g)
        nass = np.isfinite(G['tief']) & (G['tief'] > 0)
        x = lambda a, b: np.c_[a * 111.2, b * 111.2 * np.cos(np.radians(a))]   # noqa: E731
        T = cKDTree(x(G['lat'][nass], G['lon'][nass]))
        idx = np.where(nass)[0]
        print('== %s: %d Knoten (%d nass), Tiden %s, Abstand Median %.2f km' % (
            g, len(G['lat']), nass.sum(), ','.join(sorted(G['s'])),
            np.median(T.query(x(G['lat'][nass], G['lon'][nass]), k=2)[0][:, 1])))
        wl, st = [], []
        for r in R:
            if not (G['lat'].min() < r['lat'] < G['lat'].max() and G['lon'].min() < r['lon'] < G['lon'].max()):
                continue
            d, j = T.query(x(np.array([r['lat']]), np.array([r['lon']])))
            if d[0] > 1.0:
                continue
            i = idx[j[0]]
            try:
                z, w, e, mer = X.satz_lesen(r['file'], r['name'])
            except Exception:
                continue
            if 'M2' not in w:
                continue
            kap = X.greenwich(w['M2'][1], 28.9841042, mer)
            if not r['current'] and 'M2' in G['s'] and np.isfinite(G['s']['M2'][i]):
                f = 0.3048 if str(e).startswith('f') else 1
                m = G['s']['M2'][i]
                wl.append((abs(m) / (w['M2'][0] * f), (-math.degrees(cmath.phase(m)) - kap + 180) % 360 - 180, r['name'], r['file']))
            elif r['current'] and 'M2' in G['v'] and np.isfinite(G['v']['M2'][0][i]):
                U, V = G['v']['M2'][0][i], G['v']['M2'][1][i]
                best = max((abs(U * math.sin(math.radians(t)) + V * math.cos(math.radians(t))), t) for t in range(0, 180, 2))
                c = U * math.sin(math.radians(best[1])) + V * math.cos(math.radians(best[1]))
                dg = (-math.degrees(cmath.phase(c)) - kap + 180) % 360 - 180
                dg = dg if abs(dg) <= 90 else (dg + 360) % 360 - 180 - math.copysign(180, dg) + (0)
                dg = (dg + 180) % 360 - 180 if abs(dg) <= 90 else ((dg + 360) % 360 - 180 + 180) % 360 - 180
                st.append((best[0] * 1.943844 / w['M2'][0], dg, r['name'], r['file']))
        for titel, L in (('Wasserstand', wl), ('Strom', st)):
            if not L:
                print('  %s: keine Vergleichssaetze' % titel)
                continue
            q = np.array([a for a, *_ in L])
            p = np.array([abs(b) for _a, b, *_ in L])
            print('  %-11s n=%3d  Faktor Median %.2f (IQR %.2f-%.2f)  |Phase| Median %3.0f Grad, 80 %% %3.0f' % (
                titel, len(L), np.median(q), *np.percentile(q, [25, 75]), np.median(p), np.percentile(p, 80)))
            for a, b, n, f in sorted(L, key=lambda t: -abs(math.log(max(t[0], 1e-3))))[:4]:
                print('      %5.2f %+4.0f  %s  [%s]' % (a, b, n[:55], f.split('/')[-1][:28]))


if __name__ == '__main__':
    main(sys.argv[1:])
