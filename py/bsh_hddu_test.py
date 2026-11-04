#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stufe 4 der eigenen Tidenrechnung (Oliver 4.11.2026): BSH-Vorausberechnung (HDdU) gegen unseren
harmonischen Satz, beide gegen die Pegelonline-Messung.

  Messung : water_levels/pegelonline_bsh_test/<kurz>.json (1-min-Rohdaten W, cm PNP)
  BSH     : tide_tables/germany_bsh/DE__<nr>P2026.txt (E-Format, HW/NW in MEZ, m PNP)
  unser   : py/tiden_rechnung.py, Satz aus harmonics_utide_observations.txt

Scheitel der Messung: 31-min-Mittel, Extrema mindestens 4 h auseinander. Zuordnung: naechstes
Ereignis gleicher Art innerhalb 3 h. Hoehen: Mittelwert der Differenz (Bezug) getrennt von der Streuung.

Usage: venv/bin/python py/bsh_hddu_test.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiden_rechnung as TR                                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORTE = [('cuxhaven', '506', 'Cuxhaven-Steubenh\xf6ft (Elbe), Germany'),
        ('stpauli', '508', 'Hamburg (St. Pauli), Germany')]
OBS = 'harmonics/utide/harmonics_utide_observations.txt'


def messung(kurz):
    d = json.load(open(os.path.join(ROOT, 'water_levels/pegelonline_bsh_test', kurz + '.json')))
    s = pd.Series([x['value'] / 100 for x in d], index=pd.to_datetime([x['timestamp'] for x in d], utc=True))
    s = s[~s.index.duplicated()].resample('1min').mean().interpolate(limit=10)
    g = s.rolling(31, center=True).mean()
    ev = []
    for hoch in (True, False):
        x = g if hoch else -g
        kand = x[(x == x.rolling(4 * 60 + 1, center=True).max())].dropna()
        gruppe = []
        for t, v in list(kand.items()) + [(None, None)]:       # flache Kuppen: Mitte der gleichen Werte
            if gruppe and (t is None or (t - gruppe[-1][0]).total_seconds() > 4 * 3600):
                tm = gruppe[0][0] + (gruppe[-1][0] - gruppe[0][0]) / 2
                ev.append((tm.timestamp(), (gruppe[0][1] if hoch else -gruppe[0][1]), 'H' if hoch else 'N'))
                gruppe = []
            if t is not None:
                gruppe.append((t, v))
    ev.sort()
    return s, ev


def bsh(nr, t0, t1):
    ev = []
    for z in open(os.path.join(ROOT, f'tide_tables/germany_bsh/DE__{nr}P2026.txt'), encoding='latin-1'):
        if not z.startswith('VB2#'):
            continue
        f = z.split('#')
        tag = dt.datetime.strptime(f[5].replace(' ', ''), '%d.%m.%Y')
        hh, mm = f[6].strip().split(':')
        t = tag.replace(hour=int(hh), minute=int(mm), tzinfo=dt.timezone(dt.timedelta(hours=1))).timestamp()
        if t0 <= t <= t1:
            ev.append((t, float(f[7]), f[3]))
    return ev


def unser(name, t0, t1):
    D = TR.datei(OBS)
    return [(t, h, 'H' if 'High' in art else 'N') for t, h, art in D.ereignisse(name, t0, t1)
            if 'High' in art or 'Low' in art]


def vergleich(ref, pred):
    """-> {'H'/'N': (n, mittel_min, sd_min, p90_abs_min, bias_m, sd_m)}"""
    out = {}
    for art in 'HN':
        p = [(t, h) for t, h, a in pred if a == art]
        pt = np.array([t for t, _ in p])
        dz, dh = [], []
        for t, h, a in ref:
            if a != art or not len(pt):
                continue
            j = int(np.argmin(np.abs(pt - t)))
            if abs(pt[j] - t) <= 3 * 3600:
                dz.append((pt[j] - t) / 60)
                dh.append(p[j][1] - h)
        dz, dh = np.array(dz), np.array(dh)
        out[art] = (len(dz), dz.mean(), dz.std(), np.percentile(np.abs(dz), 90), dh.mean(), dh.std())
    return out


def zeile(titel, v):
    for art, (n, m, sd, p90, b, sh) in v.items():
        print(f'  {titel:24} {"HW" if art == "H" else "NW"}  n={n:3d}  Zeit {m:+5.1f} min  sd {sd:4.1f}  '
              f'|90%| {p90:4.0f} min   Hoehe Bezug {b:+.2f} m  sd {100 * sh:4.0f} cm')


def main():
    for kurz, nr, name in ORTE:
        s, mess = messung(kurz)
        t0, t1 = s.index[0].timestamp() + 3600, s.index[-1].timestamp() - 3600
        mess = [e for e in mess if t0 <= e[0] <= t1]
        b, u = bsh(nr, t0 - 6 * 3600, t1 + 6 * 3600), unser(name, t0 - 6 * 3600, t1 + 6 * 3600)
        print(f'{name}  Messung {s.index[0]:%d.%m.}-{s.index[-1]:%d.%m.%Y}, {len(mess)} Scheitel')
        zeile('BSH (HDdU) - Messung', vergleich(mess, b))
        zeile('unser Satz - Messung', vergleich(mess, u))
        j0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
        j1 = dt.datetime(2026, 12, 31, tzinfo=dt.timezone.utc).timestamp()
        zeile('unser Satz - BSH 2026', vergleich(bsh(nr, j0, j1), unser(name, j0 - 86400, j1 + 86400)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
