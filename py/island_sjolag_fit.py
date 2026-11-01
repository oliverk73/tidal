#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Saetze aus den sjolag.is-Reihen und den LHG-Jahrestafeln 2026.

sjolag.is-Reihen: stuendlich, ~44 Tage (16.9.-30.10.2026, Luecke 6.-9.10.), kein
Messrauschen. Der Satz FUENFZEHN+5 hat sich in der Probe bewaehrt: Vorhersage
der letzten 18 Tage aus den ersten 26 auf 2-7 cm; J1/M1/OO1/MU2/2N2 sprengen
dieselbe Probe (bis 44 cm), T2/LDA2/EPS2 erst recht. K2 trennt sich von S2 schon
in 44 Tagen, weil die Reihe rauschfrei ist. P1 faellt auf 0: das Modell von
sjolag.is hat keins.

Gegen Tafla I (ganzes Jahr) ist sjolag.is keine Abschrift der Tafel: 6-14 min und
7-8 cm, N2 10-35 % zu klein, K1 8-17 Grad spaeter, kein SA.

Usage: als Modul -- reihe(id), sjolag_fit(id), tafel_fit(hafen), KOPF
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import island_lhg_tafel as L                                        # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'tide_tables/iceland_sjolag')
KOPF = X.kopf_lesen(SF.KOPFQUELLE)
SATZ = ['M2', 'S2', 'N2', 'K1', 'O1', 'K2', 'Q1', 'L2', 'NU2', 'M4', 'MS4', 'MN4', 'M6', '2MS6', 'MK3',
        '2MN6', 'MSN6', 'M8', '2MK3', 'M3']
TAFELSATZ = SATZ + ['P1', 'J1', 'M1', 'OO1', 'MU2', '2N2', 'T2', 'LDA2', 'EPS2', 'SA', 'SSA']


def stationen():
    return json.load(open(os.path.join(ORDNER, 'stationen.json'), encoding='utf-8'))


def reihe(i):
    r = list(csv.DictReader(open(os.path.join(ORDNER, f'{i}.csv'), encoding='utf-8')))
    t = np.array([dt.datetime.fromisoformat(x['dags']).replace(tzinfo=dt.timezone.utc).timestamp() for x in r])
    return t, np.array([float(x['sjavarfoll']) for x in r])


def sjolag_fit(i, satz=SATZ):
    """-> (Z0, {tide: (Amplitude, Greenwich-Phase)}, Rest in m)."""
    namen, speeds, arg, fak = KOPF
    t, h = reihe(i)
    nutz = SF.konstituenten(namen, satz)
    C, S, _w = X.matrix(t, nutz, speeds, arg, fak)
    A = np.hstack([np.ones((len(t), 1)), C, S])
    s, *_ = np.linalg.lstsq(A, h, rcond=None)
    n = len(nutz)
    c, d = s[1:1 + n], s[1 + n:]
    w = {k: (float(np.hypot(c[j], d[j])), float(np.degrees(np.arctan2(d[j], c[j])) % 360.0))
         for j, k in enumerate(nutz)}
    return float(s[0]), w, float(np.std(A @ s - h))


def tafel_fit(hafen, satz=TAFELSATZ):
    """Scheitelfit auf das ganze Jahr von Tafla I -> (Z0, werte, (rms, min, off))."""
    namen, speeds, arg, fak = KOPF
    tt = L.tafel(hafen)
    z = np.array([x[0] for x in tt])
    h = np.array([x[1] for x in tt])
    z0, w = SF.fit(z, h, SF.konstituenten(namen, satz), speeds, arg, fak)
    return z0, w, SF.guete(z, h, z0, w, KOPF)
