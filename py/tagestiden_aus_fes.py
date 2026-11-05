#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersetzt nur die Tagestiden (K1, O1, P1, Q1) einzelner Saetze durch FES2022b, geeicht an nahen Amtspegeln.

Anlass (Oliver 5.11.2026): NP208-Part-II-Uebertragungen skalieren K1/O1 mit dem Halbtagsfaktor des
Bezugshafens. Liberia (von Freetown, f 0,39): K1 0,038 statt FES 0,094 und Monrovia 0,091. Wie die Reparatur
vom 2.11.2026 (84bfbe6): Halbtagestide und Flachwassertiden bleiben Buch, nur das Tagestidenband kommt aus FES.
Eichung je Tide wie py/fes_ersatz_geeicht.py: Median von Hubfaktor und Phasendifferenz Referenz/FES;
P1/Q1 bekommen die Eichung von K1/O1.

Usage: venv/bin/python py/tagestiden_aus_fes.py --land Liberia --reparieren "A, Liberia" [--reparieren ...]
           --referenz "B, Liberia" [--referenz ...] --anlass "Text" [--schreiben]
"""
import cmath
import datetime as dt
import glob
import math
import os
import re
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_kurven as D                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, stem, FES_DIR, ROOT         # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

TAG = ('K1', 'O1', 'P1', 'Q1')
GRUPPE = {'K1': 'K1', 'P1': 'K1', 'O1': 'O1', 'Q1': 'O1'}


def _liste(argv, k):
    return [argv[i + 1] for i, a in enumerate(argv) if a == k]


def main(argv):
    land = argv[argv.index('--land') + 1]
    rep, ref = _liste(argv, '--reparieren'), _liste(argv, '--referenz')
    anlass = argv[argv.index('--anlass') + 1] if '--anlass' in argv else 'Tagestiden vom fernen Bezugshafen'
    fs = sorted({os.path.relpath(p, ROOT) for p in glob.glob(ROOT + '/harmonics/*/*.txt')
                 if not re.search(r'/(backup|help)/|classic_original', p)})
    S = {s['name']: s for s in D.saetze(land, fs)}
    for n in rep + ref:
        if n not in S:
            sys.exit(f'Satz nicht gefunden: {n}')
    ds = {}

    def fes(c, lat, lon):
        if c not in ds:
            ds[c] = nc.Dataset(os.path.join(FES_DIR, f'{stem(c)}_fes2022.nc'))
        a, g = sample(ds[c], lat, lon)
        return (a, g) if a else None

    eich = {}
    for c in ('K1', 'O1'):
        f, d = [], []
        for n in ref:
            v, m = D.vek(S[n]).get(c), fes(c, S[n]['lat'], S[n]['lon'])
            if v is None or not m or abs(v) == 0:
                continue
            f.append(abs(v) / m[0])
            d.append((math.degrees(cmath.phase(v)) - m[1] + 180) % 360 - 180)
        eich[c] = (float(np.median(f)), float(np.median(d))) if f else (1.0, 0.0)
        print('Eichung %s Hub x%.3f Phase %+5.1f Grad (n=%d)' % (c, *eich[c], len(f)))

    heute = dt.date.today().strftime('%Y%m%d')
    dateien = {}
    for n in rep:
        s = S[n]
        p = os.path.join(ROOT, s['file'])
        if p not in dateien:
            dateien[p] = open(p, encoding='iso-8859-1').read().split('\n')
        V = dateien[p]
        _, speeds, _, _ = X.kopf_lesen(p)
        i = V.index(n)
        alt, neu = {}, {}
        for j in range(i + 3, len(V)):
            t = V[j].split()
            if not t or V[j].startswith('#') or (len(t) != 3):
                break
            if t[0] in TAG:
                m = fes(t[0], s['lat'], s['lon'])
                e = eich[GRUPPE[t[0]]]
                if not m:
                    continue
                a, g = m[0] * e[0], (m[1] + e[1] + speeds[t[0]] * s['meridian']) % 360
                alt[t[0]] = V[j]
                V[j] = '%-15s %.4f  %.2f' % (t[0], a, g)
                neu[t[0]] = (a, g)
        V.insert(i, '# note: %s Tagestiden (%s) aus FES2022b, geeicht an %s, statt vom Bezugshafen: %s.' % (
            heute, ', '.join(sorted(neu)), '/'.join(r.split(',')[0].split(' (')[0] for r in ref)[:50], anlass[:80]))
        print('%-45s ' % n[:45] + '  '.join('%s %s -> %.3f@%.0f' % (c, ' '.join(alt[c].split()[1:]), *neu[c])
                                             for c in ('K1', 'O1') if c in neu))
    if '--schreiben' in argv:
        for p, V in dateien.items():
            schreiben(p, '\n'.join(V))
            print('->', os.path.relpath(p, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
