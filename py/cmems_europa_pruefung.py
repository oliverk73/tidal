#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alle Gezeitensaetze in Europa gegen die CMEMS-Pegelreihen am selben Ort (Oliver 28.10.2026: "mach das").

Anlass: Die krummen TICON-Saetze aus WSV/BfG, SMHI und RWS-hist (20-40 min bzw. 2 h daneben) fielen nur beim gezielten Vergleich mit
Messreihen auf. CMEMS INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053 (oeffentlicher S3, water_levels/cmems_tg_files.txt) hat ~925 Pegel.
Fallen der CMEMS-Reihen (28.10.): Goeteborg Klippan/Hisingsbron +1 h, Bagenkop driftet ab 2022, Imperia ab 2020 -> je Reihe nur ein
stabiler Abschnitt: die juengsten >= 3 Jahre (je >= 4000 h), deren M2-Phase je Jahr hoechstens 6 min vom Median abweicht.
Verglichen werden alle Saetze (ohne Stroeme) bis 2 km, Phasen als Zeit (min, Satz minus Messung: + = Satz zu spaet).

Ergebnis: harmonics/help/cmems_europa_pruefung_<datum>.csv (eine Zeile je Paar Reihe/Satz).
Usage: venv/bin/python py/cmems_europa_pruefung.py
"""
import cmath
import csv
import datetime as dt
import glob
import math
import os
import sys
import warnings

import netCDF4
import numpy as np
import utide

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402

warnings.filterwarnings('ignore')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REIHEN = os.path.join(ROOT, 'water_levels/CMEMS_tg_pruefung')
SP = dict(M2=28.984104, S2=30.0, K1=15.041069, O1=13.943035)
KONST = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4', 'M6']


def lesen(f):
    d = netCDF4.Dataset(f)
    la, lo = float(np.ravel(d['LATITUDE'][:])[0]), float(np.ravel(d['LONGITUDE'][:])[0])
    t = np.array(netCDF4.num2date(d['TIME'][:], d['TIME'].units, only_use_cftime_datetimes=False))
    s, q = d['SLEV'][:], d['SLEV_QC'][:]
    if s.ndim > 1:
        s, q = s[:, 0], q[:, 0]
    ok = (~np.ma.getmaskarray(s)) & np.isin(np.asarray(q), [1, 2])
    return la, lo, t[ok], np.asarray(s)[ok].astype(float)


def stabil(t, v, la):
    """-> (Maske des stabilen juengsten Abschnitts, Text) oder (None, Grund)."""
    jahre = np.array([x.year for x in t])
    ph = {}
    for j in sorted(set(jahre))[-8:]:
        m = jahre == j
        if m.sum() < 4000:
            continue
        c = utide.solve(t[m], v[m], lat=la, constit=['M2', 'S2', 'N2', 'K1', 'O1'], method='ols', conf_int='none', verbose=False, trend=False)
        i = list(c.name).index('M2')
        if c.A[i] < 0.01:
            return None, 'M2 < 1 cm'
        ph[j] = c.g[i] / SP['M2'] * 60
    js = sorted(ph, reverse=True)
    for n in range(len(js), 2, -1):                                  # laengste stabile Folge ab dem juengsten Jahr
        teil = js[:n]
        if teil[0] - teil[-1] != n - 1:
            continue
        med = np.median([ph[j] for j in teil])
        if all(abs((ph[j] - med + 372.6) % 745.2 - 372.6) <= 6 for j in teil):
            return np.isin(jahre, teil), '%d-%d' % (teil[-1], teil[0])
    return None, 'instabil ' + ' '.join('%d:%.0f' % (j, ph[j]) for j in sorted(ph))


def main(argv):
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] is not None and 25 < r['lat'] < 75 and -35 < r['lon'] < 45]
    heute = dt.date.today().strftime('%Y%m%d')
    aus = os.path.join(ROOT, 'harmonics/help/cmems_europa_pruefung_%s.csv' % heute)
    zeilen = []
    for f in sorted(glob.glob(os.path.join(REIHEN, '*_60minute.nc'))):
        try:
            la, lo, t, v = lesen(f)
        except Exception as e:                                       # noqa: BLE001
            print('%s: %s' % (os.path.basename(f), e))
            continue
        if not (25 < la < 75 and -35 < lo < 45):
            continue
        nb = [r for r in recs if H.km({'lat': la, 'lon': lo}, r) < 2]
        if not nb or len(t) < 3 * 4000:
            continue
        m, abschnitt = stabil(t, v, la)
        name = os.path.basename(f).replace('_60minute.nc', '')
        if m is None:
            print('%-40s %s' % (name, abschnitt))
            continue
        c = utide.solve(t[m], v[m], lat=la, constit=KONST, method='ols', conf_int='none', verbose=False, trend=False)
        mess = {x: cmath.rect(c.A[list(c.name).index(x)], -math.radians(c.g[list(c.name).index(x)])) for x in SP}
        for r in nb:
            dtm = {x: (math.degrees(cmath.phase(r['z'][x] / mess[x])) / SP[x] * 60 if abs(r['z'][x]) and abs(mess[x]) else float('nan')) for x in SP}
            zeilen.append(dict(reihe=name, abschnitt=abschnitt, name=r['name'], datei=r['file'], km='%.2f' % H.km({'lat': la, 'lon': lo}, r),
                               m2_satz='%.3f' % abs(r['z']['M2']), m2_mess='%.3f' % abs(mess['M2']),
                               **{'dt_' + x: '%.0f' % dtm[x] for x in SP}))
            print('%-40s %-34s %-28s %4s km  M2 %s/%s  dt %s' % (name[:40], r['name'][:34], r['file'].split('/')[-1][:28], zeilen[-1]['km'],
                  zeilen[-1]['m2_satz'], zeilen[-1]['m2_mess'], ' '.join('%s %+.0f' % (x, dtm[x]) for x in SP)), flush=True)
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print('->', os.path.relpath(aus, ROOT), len(zeilen), 'Paare')


if __name__ == '__main__':
    main(sys.argv[1:])
