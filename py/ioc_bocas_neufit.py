#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bocas del Toro (IOC bdto) neu fitten (Oliver 26.10.2026).

Der Satz vom 20.05.2026 hatte R2 0.03 bei RMS 0.89 m: die Minutenreihe ist zu 26 % 0.0, zu 2 %
+-7.999 (Platzhalter), dazu kaputte Abschnitte 10-12/2019 und 10/2024-01/2025. Hier: nur Werte im
Band Median +-0.9 m, Spitzen gegen den gleitenden 31-min-Median (> 0.15 m) raus, Monate mit
Streuung > 0.2 m raus; Stundenwert = 7-min-Median MITTIG um die volle Stunde (kein Stempelversatz).
Danach die Monatspruefung und der Fit aus py/ioc_russland_fit.py.

Pegel: Steg der Smithsonian-Station (STRI) auf Isla Colon, IOC 9.350921/-82.257703.

Usage: venv/bin/python py/ioc_bocas_neufit.py [--schreiben]
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ioc_russland_fit as R                                       # noqa: E402

ROH = os.path.join(R.ROOT, 'water_levels/Panama_IOC/bdto_ioc.csv')
NAME = 'Bocas del Toro (STRI), Panama'


def stunden(_datei):
    d = pd.read_csv(ROH)
    s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors='coerce').values,
                  index=pd.to_datetime(d.iloc[:, 0], utc=True)).dropna()
    s = s[~s.index.duplicated()].sort_index()
    s = s[(s != 0) & (s.abs() < 7.9)]
    s = s[(s - s.median()).abs() < 0.9]
    s = s[(s - s.rolling('31min', center=True).median()).abs() < 0.15]
    streu = s.groupby(s.index.to_period('M')).transform('std')
    s = s[streu < 0.2]
    m = s.rolling('7min', center=True).median()
    return m[(m.index.minute == 0) & (m.index.second == 0)]


def main(argv):
    R.reihe = stunden
    R.PEGEL[:] = [('bdto', 'bdto_ioc.csv', NAME, 9.3509, -82.2577,
                   'IOC 9.350921/-82.257703 = STRI-Steg; ersetzt den Fit vom 20.05. (R2 0.03, Platzhalterwerte)')]
    R.REGION['bdto'] = 'Bocas del Toro'
    R.TZ['bdto'] = 'America/Panama'
    R.main(['bdto'] + (['--schreiben'] if '--schreiben' in argv else []))


if __name__ == '__main__':
    main(sys.argv[1:])
