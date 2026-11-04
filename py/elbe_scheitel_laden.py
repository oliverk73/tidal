#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HW/NW aus einer langen Pegelonline-Minutenreihe (JSON-Export) -> CSV (Oliver 4.11.2026, Stufe 4).

Scheitel wie py/bsh_hddu_test.scheitel, jahresweise mit 1 Tag Ueberlappung. Luecken bis 10 min
interpoliert; Scheitel, in deren +-2 h mehr als 10 min fehlen, entfallen.
HPA-Export (hydroonline.hpanet.de, water_levels/Germany/HH/Pegel_<KZ>_*.csv): cm Seekartennull, MEZ
ganzjaehrig; --hpa KZ SKN_UEBER_PNP_M rechnet auf Pegelnull um (St. Pauli: SKN = PNP + 3,10 m, BSH D03).
Usage: venv/bin/python py/elbe_scheitel_laden.py EXPORT.json ZIEL.csv
       venv/bin/python py/elbe_scheitel_laden.py --hpa STP 3.10 ZIEL.csv
"""
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsh_hddu_test as B                                           # noqa: E402


def lesen(pfad):
    t, v = [], []
    if pfad.endswith('.zip'):          # Pegelonline-Zip direkt lesen (die JSON darin ist ~800 MB)
        import io
        import zipfile
        z = zipfile.ZipFile(pfad)
        fh = io.TextIOWrapper(z.open([n for n in z.namelist() if n.endswith('.json')][0]), encoding='utf-8')
    else:
        fh = open(pfad, encoding='utf-8')
    with fh:
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


def lesen_hpa(kz, skn_pnp):
    import glob
    teile = []
    for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                           'water_levels/Germany/HH', f'Pegel_{kz}_*.csv'))):
        x = pd.read_csv(f, sep=';', skiprows=18, usecols=[0, 1], names=['t', 'w'], encoding='utf-8-sig',
                        dtype=str, on_bad_lines='skip')
        x['w'] = pd.to_numeric(x.w, errors='coerce')
        x['t'] = pd.to_datetime(x.t, errors='coerce', format='%Y-%m-%d %H:%M:%S')
        teile.append(x.dropna())
    d = pd.concat(teile).drop_duplicates('t')
    s = pd.Series(d.w.values / 100.0 + skn_pnp, index=(d.t - pd.Timedelta(hours=1)).dt.tz_localize('UTC'))
    return s.sort_index()


def main(quelle, ziel, s=None):
    s = lesen(quelle) if s is None else s
    print(len(s), s.index[0], s.index[-1], flush=True)
    takt = max(1, int(round(np.median(np.diff(s.index.values[:5000]).astype('timedelta64[s]').astype(float)) / 60)))
    voll = s.resample('1min').mean()
    if takt == 1:
        fehlt = voll.isna()
        voll = voll.interpolate(limit=10)
    else:                   # 10-/15-min-Reihen (waterinfo.be, SHOM, BODC): zeitlich auf 1 min, Luecke = > 2 Takte
        voll = voll.interpolate(method='time', limit=2 * takt, limit_area='inside')
        fehlt = voll.isna()
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
    if sys.argv[1] == '--hpa':
        main(None, sys.argv[4], lesen_hpa(sys.argv[2], float(sys.argv[3])))
    else:
        main(sys.argv[1], sys.argv[2])
