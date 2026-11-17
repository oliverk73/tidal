#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Neue Atlas-Saetze (harmonics/help/vmh_<atlas>_punkte.csv) gegen gemessene Stromsaetze <= 5 km pruefen.

Je Paar: Kurven 30 Tage entlang der eigenen Achse (Flut positiv), M2-Phasendifferenz (+ = Atlas spaeter),
Kurvenfehler = RMS(Differenz) / RMS(Messung), Staerkeverhaeltnis Spring-Maximum.

  venv/bin/python py/vmh_pruefen.py east_solent [--alle]   (--alle: auch Atlas-/Modellsaetze als Vergleich)
"""
import csv
import datetime as dt
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NICHT_MESSUNG = ('VISITMYHARBOUR', 'Admiralty', 'BOOK', 'FES', 'TPXO', 'NorKyst', 'AMM15', 'atlas', 'Atlas')


def satz(r):
    p = os.path.join(ROOT, r['file'])
    kopf = X.kopf_lesen(p)
    z0, w, _e, mer = X.satz_lesen(p, r['name'])
    g = {k: (a, X.greenwich(c, kopf[1][k], mer)) for k, (a, c) in w.items() if k in kopf[1] and a > 0}
    return z0, g, kopf


def kopfzeilen(r):
    """Quelle + Achse aus den Hot Comments des Satzes."""
    p = os.path.join(ROOT, r['file'])
    t = open(p, encoding='iso-8859-1').read()
    i = t.find('\n' + r['name'] + '\n')
    blk = t[max(0, t.rfind('# BEGIN HOT COMMENTS', 0, i)):i]
    q = ' '.join(z for z in blk.split('\n') if z.startswith('# source') or z.startswith('# note'))
    a = next((float(z.split(':')[1]) for z in blk.split('\n') if z.startswith('# major_axis_deg_true')), None)
    return q, a


def main(name):
    neu = {r['name'] for r in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/vmh_%s_punkte.csv' % name), encoding='utf-8'))}
    R = [r for r in H.load_records() if r['current'] and r['lat'] is not None]
    mine = [r for r in R if r['name'] in neu]
    t0 = dt.datetime(2027, 3, 1, tzinfo=dt.timezone.utc).timestamp()
    t = np.arange(t0, t0 + 30 * 86400, 600.0)
    for a in mine:
        for b in R:
            if b['name'] in neu or H.km(a, b) > 5:
                continue
            qb, axb = kopfzeilen(b)
            if '--alle' not in sys.argv and any(s in qb for s in NICHT_MESSUNG):
                continue
            _qa, axa = kopfzeilen(a)
            za, ga, ka = satz(a)
            zb, gb, kb = satz(b)
            ua = X.kurve(t, za, ga, list(ga), ka[1], ka[2], ka[3])
            ub = X.kurve(t, zb, gb, list(gb), kb[1], kb[2], kb[3])
            if axa is not None and axb is not None and math.cos(math.radians(axa - axb)) < 0:
                ub = -ub                                            # Flutachsen gegenlaeufig notiert
            f = np.sqrt(np.mean((ua - ub) ** 2)) / max(1e-6, np.sqrt(np.mean(ub ** 2)))
            dp = ((ga['M2'][1] - gb['M2'][1] + 180) % 360 - 180) if 'M2' in ga and 'M2' in gb else float('nan')
            if axa is not None and axb is not None and math.cos(math.radians(axa - axb)) < 0:
                dp = (dp + 360) % 360 - 180
            print('%-45s %-45s %4.1f km  Achse %3.0f/%3.0f  M2 %+4.0f Grad  Max %.1f/%.1f kn  Kurve %3.0f %%' % (
                a['name'][:45], b['name'][:45], H.km(a, b), axa or -1, axb or -1, dp,
                np.max(np.abs(ua)), np.max(np.abs(ub)), 100 * f))


if __name__ == '__main__':
    main(sys.argv[1])
