#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cape Terawhiti (Cook Strait): NIWA-RDCP 2010, SEANOE 10.17882/76439 -> Stromsatz (1.11.2026).

5-min-Werte, Betrag cm/s und Richtung true, Zeit UTC, Hoehen ueber Grund. Genommen wird das Mittel
ueber alle Hoehen mit Daten bis 3 m unter der Oberflaeche, Stundenmittel mit Stempel auf der Stundenmitte
(vgl. stroemung-stundenmittel-stempel). 35 Tage (24.8.-28.9.2010): K2 und P1 an S2 und K1 gekoppelt (py/stroemung_kopplung.py).

Usage: venv/bin/python py/terawhiti_fit.py [--schreiben]
"""
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stroemung_kopplung as K                                      # noqa: E402

ROOT = K.ROOT
PFAD = os.path.join(ROOT, 'currents/newzealand_terawhiti/CapeTerawhiti_RDCP_2010.dat')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')
LAT, LON = -(41 + 16.689 / 60), 174 + 35.857 / 60
NAME = 'Cape Terawhiti (Cook Strait), Wellington, New Zealand Current'
FREI = ['M2', 'S2', 'N2', 'K1', 'O1', 'Q1', 'L2', 'NU2', 'MU2', 'M4', 'MS4', 'MN4', 'M6', 'MK3', '2MS6']


def lesen():
    z = open(PFAD, encoding='latin-1').read().split('\n')
    h = next(i for i, l in enumerate(z) if l.startswith('yyyy'))
    zeilen = {}
    for l in z[h + 1:]:
        f = l.split()
        if len(f) < 7:
            continue
        zeilen.setdefault(tuple(f[:5]), {})[f[5]] = np.array([float(x) for x in f[6:]])
    t, u, v = [], [], []
    for k, r in zeilen.items():
        if 'mag' not in r or 'dir' not in r:
            continue
        m = np.where((r['mag'] > 500) | (r['mag'] < 0), np.nan, r['mag'][:len(r['dir'])]) / 100
        d = np.where((r['dir'] < 0) | (r['dir'] > 360), np.nan, r['dir'])
        if np.isfinite(m).sum() < 8:
            continue
        t.append(pd.Timestamp(int(k[0]), int(k[1]), int(k[2]), int(k[3]), int(k[4])))
        u.append(np.nanmean(m * np.sin(np.radians(d))))
        v.append(np.nanmean(m * np.cos(np.radians(d))))
    df = pd.DataFrame({'u': u, 'v': v}, index=pd.DatetimeIndex(t))
    return df


def main():
    df = lesen()
    print(len(df), df.index[0], df.index[-1], 'Spitze m/s', round(float(np.hypot(df.u, df.v).max()), 2))
    h = df.resample('1h').mean().dropna()
    h.index = h.index + pd.Timedelta(minutes=30)
    verh, pegel, km = K.verhaeltnisse(LAT, LON)
    print('Kopplung', pegel, round(km, 1), verh)
    kop = {'K2': ('S2', *verh['K2']), 'P1': ('K1', *verh['P1'])}
    frei = [k for k in FREI]
    r = K.fit(h, frei, kop)
    print('Achse', round(r['achse'], 1), 'Mittel kn', round(r['mean'], 3), 'r2', round(r['r2'], 3), 'rms kn', round(r['rms'], 3), 'n', r['n'])
    print({k: (round(a, 2), round(g, 1)) for k, (a, g) in r['konst'].items()})
    teil = K.fit(h.iloc[:len(h) // 2], ['M2', 'S2', 'N2', 'K1', 'O1'], {})
    print('erste Haelfte M2/S2', {k: (round(a, 2), round(g, 1)) for k, (a, g) in teil['konst'].items()})
    if '--schreiben' not in sys.argv:
        return r
    namen = K.KOPF[0]
    z = ['# BEGIN HOT COMMENTS', '# country: New Zealand', '# source: NIWA RDCP Cape Terawhiti 2010 (SEANOE 10.17882/76439), harmonic fit',
         '# station_id_context: SEANOE-76439', '# institution: NIWA', '# datum: n/a', '# station_type: current',
         f"# major_axis_deg_true: {r['achse']:.1f}", '# confidence: 7', '# date_imported: 20261101',
         f"# utide: period=2010-08-24..2010-09-28 r2={r['r2']:.3f} rms={r['rms']:.3f}kn const={len(r['konst'])}",
         '# !units: knots', f'# !longitude: {LON:.4f}', f'# !latitude: {LAT:.4f}',
         f"# note: 20261101 Tiefenmittel 34 m Wassertiefe; K2/P1 an S2/K1 gekoppelt (Verhaeltnis {pegel}).", NAME, '+00:00 :UTC', f"{r['mean']:.4f} knots"]
    for q in namen:
        if q in r['konst'] and r['konst'][q][0] >= 0.0005:
            z.append(f"{q:<16}{r['konst'][q][0]:.4f}  {r['konst'][q][1] % 360:.2f}")
        else:
            z.append('x 0 0')
    t = open(ZIEL, encoding='iso-8859-1').read()
    if NAME in t:
        raise SystemExit('schon da')
    open(ZIEL, 'w', encoding='iso-8859-1').write(t.rstrip('\n') + '\n' + '\n'.join(z) + '\n')
    return r


if __name__ == '__main__':
    main()
