#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht IOC-Reihen mit Jahren ohne Tide (Pegel steht, Cartagena 2021-22): Summe M2+S2+K1+O1 je Jahr.

Usage: venv/bin/python py/ioc_tote_jahre.py -> harmonics/help/ioc_tote_jahre_20261101.csv
"""
import csv
import glob
import os

import numpy as np
import pandas as pd

SP = {'M2': 28.9841042, 'K1': 15.0410686, 'S2': 30.0, 'O1': 13.9430356}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    aus = []
    for p in sorted(glob.glob(os.path.join(ROOT, 'water_levels/*IOC*/*.csv'))):
        try:
            d = pd.read_csv(p, usecols=['time', 'waterlevel_m'])
        except Exception:
            continue
        s = pd.Series(d['waterlevel_m'].values, index=pd.to_datetime(d['time'], errors='coerce', utc=True)).dropna().sort_index()
        s = s[~s.index.duplicated()]
        if len(s) < 5000:
            continue
        h = s.resample('1h').median().dropna()
        z = {}
        for y, g in h.groupby(h.index.year):
            if len(g) < 2000:
                continue
            r = (g - g.rolling(49, center=True, min_periods=25).median()).dropna()
            r = r[np.abs(r) < 5 * r.std()]
            t = np.asarray((r.index - pd.Timestamp('2000-01-01', tz='UTC')).total_seconds() / 3600, dtype=float)
            A = np.ones((len(t), 1))
            for k in SP:
                A = np.hstack([A, np.cos(np.radians(SP[k] * t))[:, None], np.sin(np.radians(SP[k] * t))[:, None]])
            x = np.linalg.lstsq(A, r.values, rcond=None)[0]
            z[int(y)] = float(sum(np.hypot(x[1 + 2 * i], x[2 + 2 * i]) for i in range(4)))
        if len(z) < 2:
            continue
        v = sorted(z.values())
        med = v[len(v) // 2]
        tot = [y for y, a in z.items() if a < 0.4 * med]
        hoch = [y for y, a in z.items() if a > 1.8 * med]
        aus.append(dict(datei=os.path.relpath(p, ROOT), median=round(med, 3), tot=' '.join(map(str, tot)), hoch=' '.join(map(str, hoch)),
                        jahre=' '.join(f'{y}:{a:.2f}' for y, a in z.items())))
    with open(os.path.join(ROOT, 'harmonics/help/ioc_tote_jahre_20261101.csv'), 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(aus[0]))
        w.writeheader()
        w.writerows(aus)
    print(len(aus), 'Reihen')
    for x in aus:
        if x['tot'] or x['hoch']:
            print(x['datei'][13:44].ljust(32), 'tot', x['tot'], 'hoch', x['hoch'], '|', x['jahre'][:100])


if __name__ == '__main__':
    main()
