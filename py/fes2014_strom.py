#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FES2014a-Gezeitenstroeme (AVISO, 1/16 Grad, tiefengemittelt) als Zweitmeinung zu TPXO10 (15.11.2026).

Dateien: tide_models/fes2014a_currents/{eastward,northward}_velocity/<k>.nc, Variablen Ua/Va (cm/s) und Ug/Vg (Grad,
Greenwich-Phasennacheilung), Gitter lat -90..90, lon 0..359.9375 (Schritt 0.0625), Land = Fuellwert.
Komplex wie TPXO: c = a*e^{-ig}; Projektion auf theta (rechtweisend): P = U*sin(theta) + V*cos(theta).

  pruefen: venv/bin/python py/fes2014_strom.py pruefen
      dieselben Messsaetze wie py/tpxo_strom.py pruefen (Hauptachse im Kopf), Kurvenfehler ueber M2 S2 N2 K1 O1
      (Vorzeichen frei), dazu TPXO10 an derselben Stelle und der Abstand FES2014<->TPXO10 als Fehlerwarnung.
      -> harmonics/help/fes2014_strom_pruefung.csv
"""
import cmath
import csv
import math
import os
import re
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tpxo_strom as T                                               # noqa: E402

ROOT = T.ROOT
D = os.path.join(ROOT, 'tide_models/fes2014a_currents')
KS = T.KS
AUS = os.path.join(ROOT, 'harmonics/help/fes2014_strom_pruefung.csv')
DLL = 0.0625


def _lesen(richtung, k):
    d = nc.Dataset(os.path.join(D, '%s_velocity' % richtung, '%s.nc' % k.lower()))
    x = 'U' if richtung == 'eastward' else 'V'
    a = np.ma.filled(d[x + 'a'][:].astype(np.float32), np.nan)
    g = np.ma.filled(d[x + 'g'][:].astype(np.float32), np.nan)
    return a * np.exp(-1j * np.radians(g)).astype(np.complex64) / 100.0     # m/s, c = a*e^{-ig}


def zellen(punkte, rad=4):
    """Naechste Wasserzelle (gueltiges U und V) je Punkt, Suche bis rad Zellen (~25 km) -> [(i, j, km) | None]."""
    U = _lesen('eastward', 'M2')
    ok = np.isfinite(U)
    out = []
    for la, lo in punkte:
        i0, j0 = int(round((la + 90) / DLL)), int(round((lo % 360) / DLL)) % 5760
        best = None
        for di in range(-rad, rad + 1):
            for dj in range(-rad, rad + 1):
                i, j = i0 + di, (j0 + dj) % 5760
                if not (0 <= i < 2881) or not ok[i, j]:
                    continue
                dk = 6371 * math.hypot(math.radians(-90 + i * DLL - la), math.radians(((j * DLL - lo + 180) % 360) - 180) * math.cos(math.radians(la)))
                if best is None or dk < best[2]:
                    best = (i, j, dk)
        out.append(best)
    return out


def stroeme(zl, ks=KS):
    """{k: [(U, V) komplex m/s | None je Zelle]} -- je Konstituente einmal ganz gelesen."""
    out = {}
    for k in ks:
        U, V = _lesen('eastward', k), _lesen('northward', k)
        out[k] = [None if z is None else (complex(U[z[0], z[1]]), complex(V[z[0], z[1]])) for z in zl]
        del U, V
    return out


def proj(UV, theta):
    s, c = math.sin(math.radians(theta)), math.cos(math.radians(theta))
    return (UV[0] * s + UV[1] * c) / 0.514444


def kurve(p, s):
    """Kurvenfehler % wie tpxo_strom.pruefen (Vorzeichen frei) -> (fehler, vorzeichen)."""
    tot = sum(abs(v) for v in s.values())
    f = [100 * math.sqrt(sum(abs(p[k] - vz * s[k]) ** 2 for k in s) / 2) / max(0.1, tot) for vz in (1, -1)]
    return (f[0], 1) if f[0] <= f[1] else (f[1], -1)


def pruefen(argv):
    import health_check as H
    import xtide_modell as X
    _n, speeds, _a, _f = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None and 'current_observations' in r['file']]
    texte, saetze = {}, []
    for r in R:
        if r['file'] not in texte:
            texte[r['file']] = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
        L = texte[r['file']]
        i = L.index(r['name'])
        m = re.findall(r'major_axis_deg_true: ([\d.]+)', '\n'.join(L[max(0, i - 40):i]))
        if not m:
            continue
        _z0, w, _e, mer = X.satz_lesen(os.path.join(ROOT, r['file']), r['name'])
        s = {k: cmath.rect(w[k][0], -math.radians(X.greenwich(w[k][1], speeds[k], mer))) for k in KS if k in w and w[k][0] > 0}
        if 'M2' in s:
            saetze.append((r, float(m[-1]), s))
    zl = zellen([(r['lat'], r['lon']) for r, _a, _s in saetze])
    F = stroeme(zl)
    zeilen = []
    for n, ((r, ax, s), z) in enumerate(zip(saetze, zl)):
        tz = T.wasserzelle(r['lat'], r['lon'])
        if z is None or tz is None or F['M2'][n] is None:
            continue
        pf = {k: proj(F[k][n], ax) for k in s}
        pt = T.projektion(tz[0], tz[1], ax, list(s))
        ef, vz = kurve(pf, s)
        et, _ = kurve(pt, s)
        em, _ = kurve({k: (pf[k] + pt[k]) / 2 for k in s}, s)
        ab, _ = kurve(pf, pt)                       # FES2014 gegen TPXO10 (wie gegen eine Messung)
        dphi = math.degrees(cmath.phase((vz * s['M2']) / pf['M2'])) if abs(pf['M2']) > 0 else 0.0
        zeilen.append(dict(name=r['name'], lat=r['lat'], lon=r['lon'], m2_mess=round(abs(s['M2']), 3),
                           fes_kurve_pct=round(ef, 1), tpxo_kurve_pct=round(et, 1), mittel_kurve_pct=round(em, 1), fes_tpxo_pct=round(ab, 1),
                           fes_m2_faktor=round(abs(pf['M2']) / abs(s['M2']), 2), fes_zeit_min=round(dphi / 28.9841042 * 60),
                           fes_zelle_km=round(z[2], 1), tpxo_gradient_pct=round(T.gradient(tz[0], tz[1]), 0)))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)
    ef = np.array([z['fes_kurve_pct'] for z in zeilen])
    et = np.array([z['tpxo_kurve_pct'] for z in zeilen])
    ab = np.array([z['fes_tpxo_pct'] for z in zeilen])
    g = np.array([z['tpxo_gradient_pct'] for z in zeilen])
    print('%d Saetze: FES2014 Median %.1f %% (P75 %.1f), TPXO10 Median %.1f %% (P75 %.1f); FES2014 besser an %d %%'
          % (len(ef), np.median(ef), np.percentile(ef, 75), np.median(et), np.percentile(et, 75), round(100 * np.mean(ef < et))))
    gut = g < 12
    print('  TPXO-Nachbarzellen < 12 %%: n=%d  FES2014 %.1f %%  TPXO10 %.1f %%' % (gut.sum(), np.median(ef[gut]), np.median(et[gut])))
    em = np.array([z['mittel_kurve_pct'] for z in zeilen])
    print('  Mittel beider Modelle: Median %.1f %% (P75 %.1f), Nachbarzellen < 12 %%: %.1f %%' % (np.median(em), np.percentile(em, 75), np.median(em[gut])))
    print('  Abstand FES2014<->TPXO10 als Fehlerwarnung fuer TPXO10:')
    for lo_, hi_ in ((0, 5), (5, 10), (10, 20), (20, 40), (40, 1000)):
        m = (ab >= lo_) & (ab < hi_)
        if m.any():
            print('    Abstand %3d-%3d %%: n=%4d  TPXO10-Fehler Median %5.1f %%  FES2014 %5.1f %%' % (lo_, hi_, m.sum(), np.median(et[m]), np.median(ef[m])))
    for lo_, hi_ in ((0, 12), (12, 1000)):
        m = (g >= lo_) & (g < hi_) & (ab < 10)
        if m.any():
            print('    Nachbarzellen %d-%d %% UND Abstand < 10 %%: n=%d  TPXO10 %.1f %%' % (lo_, hi_, m.sum(), np.median(et[m])))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    if sys.argv[1:2] == ['pruefen']:
        pruefen(sys.argv[2:])
    else:
        print(__doc__)
