#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wie py/ioc_tote_jahre.py, fuer UHSLC-Reihen (mm, zweite Kopfzeile, Fehlwert <0 oder >1e5).

Usage: venv/bin/python py/uhslc_tote_jahre.py -> harmonics/help/uhslc_tote_jahre_20261101.csv
"""
import csv
import glob
import os
import re

import numpy as np
import pandas as pd

SP = {'M2': 28.9841042, 'K1': 15.0410686, 'S2': 30.0, 'O1': 13.9430356}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    aus = []
    for p in sorted(glob.glob(os.path.join(ROOT, 'water_levels/*UHSLC*/*.csv')) + glob.glob(os.path.join(ROOT, 'water_levels/UHSLC_*/*.csv'))):
        try:
            d = pd.read_csv(p, skiprows=[1], usecols=[0, 1], names=['t', 'h'], header=0)
        except Exception:
            continue
        v = pd.to_numeric(d['h'], errors='coerce').values
        s = pd.Series(v, index=pd.to_datetime(d['t'], errors='coerce', utc=True)).dropna()
        s = s[(s.abs() < 20000)].sort_index() / 1000
        s = s[~s.index.duplicated()]
        if len(s) < 8000:
            continue
        z = {}
        for y, g in s.groupby(s.index.year):
            if len(g) < 3000:
                continue
            g = g.resample('1h').median().dropna()
            r = (g - g.rolling(49, center=True, min_periods=25).median()).dropna()
            r = r[np.abs(r) < 5 * r.std()]
            t = np.asarray((r.index - pd.Timestamp('2000-01-01', tz='UTC')).total_seconds() / 3600, dtype=float)
            A = np.ones((len(t), 1))
            for k in SP:
                A = np.hstack([A, np.cos(np.radians(SP[k] * t))[:, None], np.sin(np.radians(SP[k] * t))[:, None]])
            x = np.linalg.lstsq(A, r.values, rcond=None)[0]
            z[int(y)] = float(sum(np.hypot(x[1 + 2 * i], x[2 + 2 * i]) for i in range(4)))
        if len(z) < 3:
            continue
        w = sorted(z.values())
        med = w[len(w) // 2]
        tot = [y for y, a in z.items() if a < 0.6 * med]
        hoch = [y for y, a in z.items() if a > 1.5 * med]
        aus.append(dict(datei=os.path.relpath(p, ROOT), median=round(med, 3), tot=' '.join(map(str, tot)), hoch=' '.join(map(str, hoch)),
                        jahre=' '.join(f'{y}:{a:.2f}' for y, a in z.items())))
    with open(os.path.join(ROOT, 'harmonics/help/uhslc_tote_jahre_20261101.csv'), 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(aus[0]))
        w.writeheader()
        w.writerows(aus)
    print(len(aus), 'Reihen')
    for x in aus:
        if x['tot'] or x['hoch']:
            print(x['datei'][13:50].ljust(38), 'med', x['median'], 'tot', x['tot'], 'hoch', x['hoch'])


if __name__ == '__main__':
    main()
