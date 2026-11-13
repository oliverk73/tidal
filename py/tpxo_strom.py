#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gezeitenstrom aus TPXO10-atlas-v2 (u-Dateien) und Pruefung gegen unsere gemessenen Stromsaetze (13.11.2026).

Format (OTIS-Atlas, big-endian Fortran-Records):
  u_<k>_tpxo10_atlas_30_v2: Kopf wie h, dann ein Record (ny, nx, 4) float32 = U_re, U_im, V_re, V_im,
      Volumentransporte in m^2/s (Probe Dover Strait M2 ~57 m^2/s bei 48 m -> 1,2 m/s). U an der West-, V an der
      Suedkante der Zelle (C-Gitter) -> fuer die Zellmitte Mittel der beiden Kanten.
  grid_tpxo10_atlas_30_v2: Record 3 (Offset 56) = Tiefe hz an der Zellmitte (m).
  Phase wie h: Komplexzahl c = re + i*im = a*e^{-ig}, g Greenwich-Phasennacheilung.
Projektion auf eine Richtung theta (rechtweisend): P = U*sin(theta) + V*cos(theta) (komplex), dann a=|P|, g=-arg(P).

  pruefen: venv/bin/python py/tpxo_strom.py pruefen
      alle Saetze in harmonics_utide_current_observations.txt mit Hauptachse im Kopf; Kurvenfehler wie FES-Pruefung
      ueber M2 S2 N2 K1 O1 (Vorzeichen frei, da die Flutrichtung mancher Saetze gedreht ist), M2-Staerkefaktor,
      M2-Zeitversatz, Tiefe, Abstand zur naechsten Modellzelle und Unterschied der Nachbarzellen (wie nws_strom.py).
      -> harmonics/help/tpxo_strom_pruefung.csv
"""
import cmath
import csv
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'tide_models/TPXO10_atlas_v2')
NX, NY = 10800, 5401
KS = ('M2', 'S2', 'N2', 'K1', 'O1')
AUS = os.path.join(ROOT, 'harmonics/help/tpxo_strom_pruefung.csv')
_u, _hz = {}, []


def u_feld(k):
    if k not in _u:
        _u[k] = np.memmap(os.path.join(D, 'u_%s_tpxo10_atlas_30_v2' % k.lower()), dtype='>f4', mode='r', offset=44, shape=(NY, NX, 4))
    return _u[k]


def hz():
    if not _hz:
        _hz.append(np.memmap(os.path.join(D, 'grid_tpxo10_atlas_30_v2'), dtype='>f4', mode='r', offset=56, shape=(NY, NX)))
    return _hz[0]


def zelle(lat, lon):
    return int(round((lat + 90.0) * 30)), int(round((lon % 360.0) * 30 - 1)) % NX


def wasserzelle(lat, lon, rad=15, min_tiefe=2.0):
    i0, j0 = zelle(lat, lon)
    H = hz()
    best = None
    for di in range(-rad, rad + 1):
        for dj in range(-rad, rad + 1):
            i, j = i0 + di, (j0 + dj) % NX
            if not (0 < i < NY - 1) or H[i, j] < min_tiefe or H[i + 1, j] < min_tiefe or H[i, (j + 1) % NX] < min_tiefe:
                continue
            la, lo = -90 + i / 30.0, (j + 1) / 30.0
            dk = 6371 * math.hypot(math.radians(la - lat), math.radians(((lo - lon + 180) % 360) - 180) * math.cos(math.radians(lat)))
            if best is None or dk < best[2]:
                best = (i, j, dk)
    return best


def strom(i, j, k):
    """(Ue, Vn) komplex in m/s an der Zellmitte (i, j)."""
    F = u_feld(k)
    h = float(hz()[i, j])
    a, b = F[i, j], F[i, (j + 1) % NX]
    c = F[i + 1, j]
    U = (complex(a[0], a[1]) + complex(b[0], b[1])) / 2
    V = (complex(a[2], a[3]) + complex(c[2], c[3])) / 2
    return U / h, V / h


def projektion(i, j, theta, ks=KS):
    s, c = math.sin(math.radians(theta)), math.cos(math.radians(theta))
    out = {}
    for k in ks:
        U, V = strom(i, j, k)
        out[k] = (U * s + V * c) / 0.514444          # Knoten, c = a*e^{-ig}
    return out


def gradient(i, j, k='M2'):
    U0, V0 = strom(i, j, k)
    n = math.hypot(abs(U0), abs(V0))
    g = []
    for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        ii, jj = i + di, (j + dj) % NX
        if hz()[ii, jj] < 2:
            return 999.0
        U, V = strom(ii, jj, k)
        g.append(math.hypot(abs(U - U0), abs(V - V0)) / max(n, 1e-6))
    return 100 * max(g)


def pruefen(argv):
    import health_check as H
    import xtide_modell as X
    namen, speeds, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and 'current_observations' in r['file']]
    texte, zeilen = {}, []
    for r in R:
        if r['file'] not in texte:
            texte[r['file']] = open(r['file'], encoding='iso-8859-1').read().split('\n')
        T = texte[r['file']]
        i = T.index(r['name'])
        kopf = '\n'.join(T[max(0, i - 40):i])
        m = re.findall(r'major_axis_deg_true: ([\d.]+)', kopf) or re.findall(r'Major axis: ([\d.]+)', kopf)
        if not m:
            continue
        ax = float(m[-1])
        tiefe = re.findall(r'depth (-?[\d.]+) m', kopf)
        z = wasserzelle(r['lat'], r['lon'])
        if not z:
            continue
        ii, jj, dk = z
        _z0, w, _e, mer = X.satz_lesen(r['file'], r['name'])
        s = {k: cmath.rect(w[k][0], -math.radians(X.greenwich(w[k][1], speeds[k], mer))) for k in KS if k in w and w[k][0] > 0}
        if 'M2' not in s:
            continue
        p = projektion(ii, jj, ax, [k for k in s])
        tot = sum(abs(v) for v in s.values())
        f = [100 * math.sqrt(sum(abs(p[k] - vz * s[k]) ** 2 for k in s) / 2) / max(0.1, tot) for vz in (1, -1)]
        vz = 1 if f[0] <= f[1] else -1
        dphi = math.degrees(cmath.phase((vz * s['M2']) / p['M2'])) if abs(p['M2']) > 0 else 0.0   # >0: Modell spaeter
        zeilen.append(dict(name=r['name'], lat=r['lat'], lon=r['lon'], kurve_pct=round(min(f), 1),
                           m2_mess=round(abs(s['M2']), 3), m2_faktor=round(abs(p['M2']) / abs(s['M2']), 2),
                           zeit_min=round(dphi / 28.9841042 * 60, 0), zelle_km=round(dk, 1),
                           tiefe_modell=round(float(hz()[ii, jj]), 1), tiefe_mess=tiefe[-1] if tiefe else '',
                           gradient_pct=round(gradient(ii, jj), 0)))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)
    e = np.array([z['kurve_pct'] for z in zeilen])
    g = np.array([z['gradient_pct'] for z in zeilen])
    m2 = np.array([z['m2_mess'] for z in zeilen])
    print('%d Saetze: Kurvenfehler Median %.1f %%, P75 %.1f %%' % (len(e), np.median(e), np.percentile(e, 75)))
    for lo_, hi_ in ((0, 12), (12, 25), (25, 50), (50, 1000)):
        m = (g >= lo_) & (g < hi_)
        if m.any():
            print('  Nachbarzellen %3d-%3d %%: n=%4d  Median %5.1f %%  P75 %5.1f %%' % (lo_, hi_, m.sum(), np.median(e[m]), np.percentile(e[m], 75)))
    for lo_, hi_ in ((0, 0.3), (0.3, 1), (1, 9)):
        m = (m2 >= lo_) & (m2 < hi_)
        if m.any():
            print('  M2-Strom %.1f-%.1f kn: n=%4d  Median %5.1f %%' % (lo_, hi_, m.sum(), np.median(e[m])))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    if sys.argv[1:2] == ['pruefen']:
        pruefen(sys.argv[2:])
    else:
        print(__doc__)
