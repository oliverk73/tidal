#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersetzt Buchuebertragungen an offener Kueste durch FES2022b, geeicht an nahen Amtspegeln.

Anlass 15.10.2026 (Oliver): Malinao Inlet und Gaas Bay (Dinagat) tragen im NOAA-Buch dieselben
Differenzen (+0:40, x0.88 auf Legaspi) -> identische Saetze, beide ~37 min spaeter als FES; FES
trifft an dieser Pazifikkueste den NAMRIA-Pegel Santa Monica auf 2 Grad.

Eichung wie Fogo (13.10.2026): je Tide Median von Hubfaktor und Phasendifferenz Amtspegel/FES
ueber die Referenzpegel; Tiden ohne eigene Eichung bekommen die ihrer Gruppe (M2/S2/K1/O1).
Name, Position, Zeitzone und Z0 kommen vom ersetzten Satz.

Usage: venv/bin/python py/fes_ersatz_geeicht.py [--schreiben]          (Dinagat, Voreinstellung)
       venv/bin/python py/fes_ersatz_geeicht.py --land Indonesia --ersetzen "A, ..., Indonesia" [--ersetzen ...]
                       --referenz "B, ..., Indonesia" [--referenz ...] --anlass "Text" [--schreiben]
"""
import cmath
import datetime as dt
import math
import os
import re
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_kurven as D                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, stem, FES_DIR, ZIEL, ROOT    # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

LAND = 'Philippines'
ERSETZEN = ['Malinao Inlet, Dinagat Islands, Philippines', 'Gaas Bay (Valencia), Dinagat Islands, Philippines']
REFERENZ = ['Santa Monica (Siargao Island), Surigao del Norte, Philippines', 'Tandag, Surigao del Sur, Philippines',
            'Lawigan (Bislig Bay), Surigao del Sur, Philippines', 'Guiuan, Eastern Samar, Philippines']
ANLASS = 'NOAA-Buch gibt beiden Orten dieselben Differenzen (+0:40, x0.88 auf Legaspi), Satz ~37 min hinter FES'


def gruppe(c, speeds):
    w = speeds[c]
    if w < 5:
        return None
    if w < 20:
        return 'K1' if w >= 14.5 else 'O1'
    if w < 35:
        return 'S2' if c in ('S2', 'K2', 'T2', 'R2') else 'M2'
    return 'M2'


def _liste(argv, k):
    return [argv[i + 1] for i, a in enumerate(argv) if a == k and i + 1 < len(argv)]


def main(argv):
    global LAND, ERSETZEN, REFERENZ, ANLASS
    if '--land' in argv:
        LAND = argv[argv.index('--land') + 1]
        ERSETZEN, REFERENZ = _liste(argv, '--ersetzen'), _liste(argv, '--referenz')
        ANLASS = argv[argv.index('--anlass') + 1] if '--anlass' in argv else 'Buchsatz gegen FES und Amtspegel daneben'
    namen, speeds, _, _ = X.kopf_lesen(ZIEL)
    fs = sorted({os.path.relpath(p, ROOT) for p in __import__('glob').glob(ROOT + '/harmonics/*/*.txt')})
    S = {s['name']: s for s in D.saetze(LAND, fs)}
    ds = {}

    def fes(c, lat, lon):
        p = os.path.join(FES_DIR, f'{stem(c)}_fes2022.nc')
        if not os.path.exists(p):
            return None
        if c not in ds:
            ds[c] = nc.Dataset(p)
        a, g = sample(ds[c], lat, lon)
        return (a, g) if a else None

    # Eichung: Amtspegel gegen FES am Pegelort (Greenwich-Phasen)
    eich = {}
    for c in ('M2', 'S2', 'K1', 'O1', 'N2', 'K2', 'P1', 'Q1'):
        f, d = [], []
        for n in REFERENZ:
            r = S[n]
            v = D.vek(r).get(c) if c in D.SP else None
            m = fes(c, r['lat'], r['lon'])
            if v is None or not m or abs(v) == 0:
                continue
            f.append(abs(v) / m[0])
            d.append((math.degrees(cmath.phase(v)) - m[1] + 180) % 360 - 180)
        if len(f) >= min(2, len(REFERENZ)):
            eich[c] = (float(np.median(f)), float(np.median(d)))
            print('Eichung %-3s Hub x%.3f  Phase %+5.1f Grad  (n=%d: %s)' % (c, eich[c][0], eich[c][1], len(f),
                  ', '.join('%.2f/%+.0f' % x for x in zip(f, d))))
    heute = dt.date.today().strftime('%Y%m%d')
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    for n in ERSETZEN:
        s = S[n]
        V = open(os.path.join(ROOT, s['file']), encoding='iso-8859-1').read().split('\n')
        i = V.index(n)
        tz = V[i + 1].split(' :', 1)[1] if ' :' in V[i + 1] else 'UTC'
        mer = s['meridian']
        z0 = V[i + 2]
        prov = re.findall(r'# (province|state|region): (.*)', s['kopf'])
        blk = ['#', f'# {n}', '# BEGIN HOT COMMENTS', f'# country: {LAND}',
               '# source: FES2022b global ocean tide model (extrapolated), sampled at station location',
               '# note: MODEL-DERIVED (not observations). Ersetzt %s-Satz (archiviert):' % (
                   'NOAA-Table-2' if '/noaa/' in s['file'] else 'Admiralty' if '/att/' in s['file'] else os.path.basename(s['file'])),
               f'# note: {ANLASS}.',
               '# note: FES geeicht an %s (Median je Tide), M2 x%.3f %+.1f Grad (%s, Oliver).' % (
                   '/'.join(n.split(',')[0].split(' (')[0] for n in REFERENZ)[:60], eich['M2'][0], eich['M2'][1], heute),
               f'# date_imported: {heute}', '# datum: Chart Datum (Z0 = mean tide level above CD, vom ersetzten Satz)',
               '# confidence: 5', '# !units: meters', f"# !longitude: {s['lon']:.4f}", f"# !latitude: {s['lat']:.4f}"]
        blk += [f'# {k}: {v}' for k, v in prov[-1:]]
        blk += [n, V[i + 1], z0]
        neu = {}
        for c in namen:
            m = fes(c, s['lat'], s['lon'])
            if not m or m[0] < 0.00005:
                continue
            e = eich.get(c) or eich.get(gruppe(c, speeds) or '', (1.0, 0.0))
            a, g = m[0] * e[0], m[1] + e[1]
            neu[c] = (a, (g + speeds[c] * mer) % 360)          # Greenwich -> Zonenphase des Satzes
        for c in namen:
            blk.append('%-15s %.4f  %.2f' % (c, neu[c][0], neu[c][1]) if c in neu else 'x 0 0')
        print('%-48s %d Tiden  M2 %.3f@%.0f  K1 %.3f@%.0f  Z0 %s  tz %s' % (n, len(neu), *neu['M2'], *neu['K1'], z0, tz))
        if n in L:
            print('   existiert schon in harmonics_fes2022'); continue
        L += blk
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
