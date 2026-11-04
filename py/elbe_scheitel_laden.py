#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HW/NW aus einer langen Pegelonline-Minutenreihe (JSON-Export) -> CSV (Oliver 4.11.2026, Stufe 4).

Scheitel wie py/bsh_hddu_test.scheitel, jahresweise mit 1 Tag Ueberlappung. Luecken bis 10 min
interpoliert; Scheitel, in deren +-2 h mehr als 10 min fehlen, entfallen.
Usage: venv/bin/python py/elbe_scheitel_laden.py EXPORT.json ZIEL.csv
"""
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsh_hddu_test as B                                           # noqa: E402


def lesen(pfad):
    t, v = [], []
    with open(pfad, encoding='utf-8') as fh:
        for z in fh:
            i = z.find('"timestamp":"')
            if i < 0:
                continue
            t.append(z[i + 13:i + 38])
            j = z.find('"value":', i)
            v.append(z[j + 8:z.find('}', j)])
    s = pd.Series(pd.to_numeric(v, errors='coerce') / 100.0,
                  index=pd.to_datetime(t, utc=True, format='%Y-%m-%dT%H:%M:%S%z'))
    return s[~s.index.duplicated()].sort_index()


def main(quelle, ziel):
    s = lesen(quelle)
    print(len(s), s.index[0], s.index[-1], flush=True)
    voll = s.resample('1min').mean()
    fehlt = voll.isna()
    voll = voll.interpolate(limit=10)
    zeilen = []
    for jahr in range(s.index[0].year, s.index[-1].year + 1):
        a, b = pd.Timestamp(f'{jahr}-01-01', tz='UTC'), pd.Timestamp(f'{jahr + 1}-01-01', tz='UTC')
        teil = voll[a - pd.Timedelta(days=1):b + pd.Timedelta(days=1)]
        if teil.notna().sum() < 1000:
            continue
        for t, h, art in B.scheitel(teil):
            ts = pd.Timestamp(t, unit='s', tz='UTC')
            if not (a <= ts < b) or fehlt[ts - pd.Timedelta(hours=2):ts + pd.Timedelta(hours=2)].sum() > 10:
                continue
            zeilen.append((ts.strftime('%Y-%m-%d %H:%M'), round(h, 3), art))
        print(jahr, len(zeilen), flush=True)
    pd.DataFrame(zeilen, columns=['utc', 'hoehe_m', 'art']).to_csv(ziel, index=False)
    print('->', ziel, len(zeilen))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
