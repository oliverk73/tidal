#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Neufit von IOC-Saetzen nur aus Jahren mit voller Tide (py/ioc_tote_jahre.py, 1.11.2026).

Stundenmedian mit Stempel auf der Stundenmitte. Name, Position und Z0 bleiben.

Usage: venv/bin/python py/ioc_gute_jahre.py [--schreiben]
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qld_msq_fit as Q                                             # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import seine_haropa_fit as S                                        # noqa: E402
import xtide_modell as X                                            # noqa: E402

P = 'harmonics/utide/harmonics_utide_observations.txt'
# Bocas del Toro nicht: der Bestandssatz passt zu den robusten Jahreswerten, die Rohreihe hat Spruenge (Rest 0,85 m)
FAELLE = [('water_levels/Colombia_IOC/buve2_ioc.csv', 'Buenaventura, Colombia', (2021, 2022, 2024))]


def main():
    kopf = X.kopf_lesen(P)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    for pfad, name, jahre in FAELLE:
        d = pd.read_csv(pfad, usecols=['time', 'waterlevel_m'])
        s = pd.Series(d['waterlevel_m'].values, index=pd.to_datetime(d['time'], errors='coerce')).dropna().sort_index()
        s = s[~s.index.duplicated()]
        s = s[s.index.year.isin(jahre)]
        s = s[(s - s.median()).abs() < 6 * s.std()]
        h = s.resample('1h').median().dropna()
        h.index = h.index + pd.Timedelta(minutes=30)
        tage = (h.index[-1] - h.index[0]).days
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        sx, t, z0, w, hh, _a = Q.fit(h, nutz, kopf, speeds, arg, fak)
        z, alt, _e, m = X.satz_lesen(P, name)
        print(name[:34], len(sx), 'rms', round(float(np.sqrt(np.mean((sx.values - hh) ** 2))), 3), 'M2', [round(x, 3) for x in w['M2']], 'alt', alt['M2'], 'K1', [round(x, 3) for x in w['K1']], 'alt', alt['K1'], 'S2', [round(x, 3) for x in w['S2']], 'alt', alt['S2'], 'mer', m)
        if '--schreiben' in sys.argv:
            SF.satz_schreiben(P, name, z, w, namen, [f"20261101 Neu nur aus {min(jahre)}-{max(jahre)}, Jahre ohne volle Tide weggelassen (py/ioc_tote_jahre.py)."])


if __name__ == '__main__':
    main()
