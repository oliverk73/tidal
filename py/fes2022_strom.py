#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FES2022b-Gezeitenstroeme (AVISO, 1/30 Grad, tiefengemittelt) gegen Messsaetze, FES2014a und TPXO10 (24.11.2026).

Dateien: tide_models/fes2022b_currents/{eastward,northward}_velocity/<k>_fes2022.nc, Variablen Ua/Va (cm/s) und
Ug/Vg (Grad, Greenwich-Nacheilung), Gitter lat -90..90 (5401), lon 0..360 (10801, 360 = 0), Land = Fuellwert.
Komplex wie TPXO/FES2014: c = a*e^{-ig}.

  pruefen: venv/bin/python py/fes2022_strom.py pruefen
      dieselben Messsaetze wie py/fes2014_strom.py (Hauptachse im Kopf), Kurvenfehler ueber M2 S2 N2 K1 O1
      -> harmonics/help/fes2022_strom_pruefung.csv
"""
import math
import os
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes2014_strom as F14                                          # noqa: E402
import tpxo_strom as T                                               # noqa: E402

ROOT = T.ROOT
D = os.path.join(ROOT, 'tide_models/fes2022b_currents')
KS = T.KS
AUS = os.path.join(ROOT, 'harmonics/help/fes2022_strom_pruefung.csv')
DLL = 1 / 30.0
NLA, NLO = 5401, 10800                                               # Spalte 10800 (= 360 Grad) doppelt, nicht benutzt


def _lesen(richtung, k):
    d = nc.Dataset(os.path.join(D, '%s_velocity' % richtung, '%s_fes2022.nc' % k.lower()))
    x = 'U' if richtung == 'eastward' else 'V'
    a = np.ma.filled(d[x + 'a'][:, :NLO].astype(np.float32), np.nan)
    g = np.ma.filled(d[x + 'g'][:, :NLO].astype(np.float32), np.nan)
    a[a > 1e6] = np.nan
    return a * np.exp(-1j * np.radians(g)).astype(np.complex64) / 100.0     # m/s


def zellen(punkte, rad=8):
    """Naechste Wasserzelle je Punkt, Suche bis rad Zellen (~25 km) -> [(i, j, km) | None]."""
    ok = np.isfinite(_lesen('eastward', 'M2'))
    out = []
    for la, lo in punkte:
        i0, j0 = int(round((la + 90) / DLL)), int(round((lo % 360) / DLL)) % NLO
        best = None
        for di in range(-rad, rad + 1):
            for dj in range(-rad, rad + 1):
                i, j = i0 + di, (j0 + dj) % NLO
                if not (0 <= i < NLA) or not ok[i, j]:
                    continue
                dk = 6371 * math.hypot(math.radians(-90 + i * DLL - la),
                                       math.radians(((j * DLL - lo + 180) % 360) - 180) * math.cos(math.radians(la)))
                if best is None or dk < best[2]:
                    best = (i, j, dk)
        out.append(best)
    return out


def stroeme(zl, ks=KS):
    out = {}
    for k in ks:
        U, V = _lesen('eastward', k), _lesen('northward', k)
        out[k] = [None if z is None else (complex(U[z[0], z[1]]), complex(V[z[0], z[1]])) for z in zl]
        del U, V
    return out


def pruefen(argv):
    import csv
    saetze = F14.messsaetze()
    pkt = [(r['lat'], r['lon']) for r, _a, _s in saetze]
    z22, z14 = zellen(pkt), F14.zellen(pkt)
    S22, S14 = stroeme(z22), F14.stroeme(z14)
    kurve, proj = F14.kurve, F14.proj
    zeilen = []
    for n, (r, ax, s) in enumerate(saetze):
        tz = T.wasserzelle(r['lat'], r['lon'])
        if z22[n] is None or z14[n] is None or tz is None or S22['M2'][n] is None or S14['M2'][n] is None:
            continue
        p22 = {k: proj(S22[k][n], ax) for k in s}
        p14 = {k: proj(S14[k][n], ax) for k in s}
        pt = T.projektion(tz[0], tz[1], ax, list(s))
        if not all(np.isfinite(abs(v)) for v in list(p22.values()) + list(p14.values())):
            continue
        e22, vz = kurve(p22, s)
        zeilen.append(dict(
            name=r['name'], lat=r['lat'], lon=r['lon'], m2_mess=round(abs(s['M2']), 3),
            fes22_pct=round(e22, 1), fes14_pct=round(kurve(p14, s)[0], 1), tpxo_pct=round(kurve(pt, s)[0], 1),
            mittel22_tpxo_pct=round(kurve({k: (p22[k] + pt[k]) / 2 for k in s}, s)[0], 1),
            mittel_alle_pct=round(kurve({k: (p22[k] + p14[k] + pt[k]) / 3 for k in s}, s)[0], 1),
            fes22_fes14_pct=round(kurve(p22, p14)[0], 1), fes22_tpxo_pct=round(kurve(p22, pt)[0], 1),
            fes22_m2_faktor=round(abs(p22['M2']) / abs(s['M2']), 2),
            fes22_zeit_min=round(math.degrees(np.angle(vz * s['M2'] / p22['M2'])) / 28.9841042 * 60) if abs(p22['M2']) else 0,
            fes22_zelle_km=round(z22[n][2], 1), fes14_zelle_km=round(z14[n][2], 1),
            tpxo_gradient_pct=round(T.gradient(tz[0], tz[1]), 0)))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)
    A = {k: np.array([z[k] for z in zeilen]) for k in zeilen[0] if k.endswith('_pct') or k.endswith('_km')}
    g = A['tpxo_gradient_pct'] if 'tpxo_gradient_pct' in A else np.array([z['tpxo_gradient_pct'] for z in zeilen])
    print('%d Saetze (Kurvenfehler Median / P75):' % len(zeilen))
    for k, t in (('fes22_pct', 'FES2022'), ('fes14_pct', 'FES2014'), ('tpxo_pct', 'TPXO10'),
                 ('mittel22_tpxo_pct', 'Mittel FES2022+TPXO10'), ('mittel_alle_pct', 'Mittel aller drei')):
        print('  %-22s %5.1f %%  %5.1f %%   ruhig (Nachbarzellen < 12 %%): %5.1f %%'
              % (t, np.median(A[k]), np.percentile(A[k], 75), np.median(A[k][g < 12])))
    print('  FES2022 besser als FES2014 an %d %%, besser als TPXO10 an %d %%'
          % (round(100 * np.mean(A['fes22_pct'] < A['fes14_pct'])), round(100 * np.mean(A['fes22_pct'] < A['tpxo_pct']))))
    nah = A['fes14_zelle_km'] > 3
    if nah.any():
        print('  FES2014-Zelle > 3 km vom Messort (Kueste, n=%d): FES2022 %.1f %%, FES2014 %.1f %%, TPXO10 %.1f %%'
              % (nah.sum(), np.median(A['fes22_pct'][nah]), np.median(A['fes14_pct'][nah]), np.median(A['tpxo_pct'][nah])))
    print('  Abstand FES2022<->TPXO10 als Fehlerwarnung:')
    ab = A['fes22_tpxo_pct']
    for lo_, hi_ in ((0, 5), (5, 10), (10, 20), (20, 40), (40, 1000)):
        m = (ab >= lo_) & (ab < hi_)
        if m.any():
            print('    %3d-%3d %%: n=%4d  FES2022 %5.1f %%  TPXO10 %5.1f %%  Mittel %5.1f %%'
                  % (lo_, hi_, m.sum(), np.median(A['fes22_pct'][m]), np.median(A['tpxo_pct'][m]), np.median(A['mittel22_tpxo_pct'][m])))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    if sys.argv[1:2] == ['pruefen']:
        pruefen(sys.argv[2:])
    else:
        print(__doc__)
