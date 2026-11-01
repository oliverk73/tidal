#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Stromsaetze aus den HK-TSPS-Vorhersagen 2026 (py/hk_tsps_laden.py).

Stunde fuer Stunde: Zerlegung auf die Hauptachse (groesste Varianz), Fit im XTide-Modell mit
der 67er-Liste. Zeiten der Quelle in HKT (UTC+8). Das Vorzeichen (Flut positiv) richtet
py/flutrichtung_pruefen.py nach dem Eintragen.

Usage: als Modul -- punkte(), fit(pfad)
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheitelfit as SF                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORD = os.path.join(ROOT, 'tide_tables/hongkong_tsps')
KOPF = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt'))
HKT = 8 * 3600


def lesen(pfad):
    t, kn, gr = [], [], []
    with open(pfad, encoding='utf-8') as fh:
        r = csv.reader(fh)
        kopf = next(r)
        sp = [(i, kopf[i][:4]) for i in range(4, len(kopf), 2)]
        for z in r:
            d0 = dt.datetime.strptime(z[3], '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() - HKT
            la, lo = float(z[0]), float(z[1])
            for i, hhmm in sp:
                if hhmm[2:] != '00' or z[i] == '':
                    continue
                t.append(d0 + int(hhmm[:2]) * 3600)
                kn.append(float(z[i]))
                gr.append(float(z[i + 1]))
    return la, lo, np.array(t), np.array(kn), np.array(gr)


def fit(pfad):
    la, lo, t, kn, gr = lesen(pfad)
    o, n = kn * np.sin(np.radians(gr)), kn * np.cos(np.radians(gr))
    o0, n0 = o - o.mean(), n - n.mean()
    w, v = np.linalg.eigh(np.cov(o0, n0))
    achse = math.degrees(math.atan2(v[0, 1], v[1, 1])) % 180
    u = o * math.sin(math.radians(achse)) + n * math.cos(math.radians(achse))
    namen, speeds, arg, fak = KOPF
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    C, S, _w = X.matrix(t, nutz, speeds, arg, fak)
    A = np.hstack([np.ones((len(t), 1)), C, S])
    s, *_ = np.linalg.lstsq(A, u, rcond=None)
    k = len(nutz)
    c, d = s[1:1 + k], s[1 + k:]
    werte = {q: (float(np.hypot(c[j], d[j])), float(np.degrees(np.arctan2(d[j], c[j])) % 360)) for j, q in enumerate(nutz)}
    rest = float(np.std(A @ s - u))
    return dict(lat=la, lon=lo, achse=achse, z0=float(s[0]), werte=werte, rest=rest, spitze=float(kn.max()),
                quer=float(math.sqrt(max(w[0], 0) / w[1])), n=len(t))


def punkte():
    return sorted(glob.glob(os.path.join(ORD, 'p*.csv')))
