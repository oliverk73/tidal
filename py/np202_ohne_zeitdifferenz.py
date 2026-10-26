#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP202-Sekundaerhaefen ohne Zeitdifferenz im Buch ("-") reparieren (Oliver 26.10.2026).

rebuild_np202_transfer.py hat "-" als 0 gelesen und die Phasen des Gruppen-Bezugshafens
unveraendert uebernommen -- Port of Spain fuer Mariel, Bergen fuer den Oslofjord, Reykjavik
fuer die Faeroeer. 20 von 22 Saetzen lagen damit 70-180 Grad neben FES und den Nachbarn.

Das Buch sagt ueber diese Haefen nur etwas zum Hub. Daher:
  Phasen und Konstituentenverhaeltnisse vom naechsten unabhaengigen Satz (nicht NP202 Part II)
  bis 70 km mit M2, S2, N2, K1, O1 (notfalls ohne K1/O1), dessen M2-Phase am Zielort hoechstens 30 Grad von FES2022 abweicht;
  Halbtaegige mit f = Springhub laut Buch / Springhub des Nachbarn, Flachwasser mit f^2,
  eintaegige und langperiodische unveraendert. Unter 0,5 m Springhub ist f = 1: die Buchhoehen
  haben 0,1 m Aufloesung und zerlegten im Oslofjord S2 zu fast nichts.
Passt die alte Phase ohnehin (|FES| <= 30 Grad), bleibt der Satz stehen. Ohne Nachbarn: Liste
zum Archivieren.

Usage: venv/bin/python py/np202_ohne_zeitdifferenz.py [--schreiben]
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import shutil
import sys

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                         # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR                      # noqa: E402
from rebuild_np202_transfer import SEMI_M, SHALLOW, DIURNAL, LANGZEIT, ordnung  # noqa: E402

TXT = os.path.join(ROOT, 'harmonics/att/harmonics_att_np202_secondary.txt')
BUCH = os.path.join(ROOT, 'harmonics/help/np202_part2_stationen.tsv')
BIS_KM = 70.0
FES_TOL = 30.0


def km(a, b, c, d):
    return 6371 * math.hypot(math.radians(a - c), math.radians(b - d) * math.cos(math.radians(a)))


def wrap(x):
    return (x + 180) % 360 - 180


def spender(r, R, speeds, gf, pflicht):
    """Naechster unabhaengiger Satz bis BIS_KM mit den Pflichtkonstituenten, M2 nahe FES."""
    for s in sorted(R, key=lambda s: km(r['lat'], r['lon'], s['lat'], s['lon'])):
        d = km(r['lat'], r['lon'], s['lat'], s['lon'])
        if d > BIS_KM:
            return None
        if s is r or 'np202_secondary' in s['file']:
            continue
        try:
            _z2, w2, e2, m2 = X.satz_lesen(s['file'], s['name'])
        except KeyError:
            continue
        if any(w2.get(c, (0,))[0] <= 0 for c in pflicht):
            continue
        g2 = X.greenwich(w2['M2'][1], speeds['M2'], m2) % 360
        if gf is not None and abs(wrap(g2 - gf)) > FES_TOL:
            continue
        return (s, d, w2, m2, 0.3048 if e2.startswith('f') else 1.0)
    return None


def main(argv):
    schreiben = '--schreiben' in argv
    ohne = set()
    for l in open(BUCH, encoding='utf-8'):
        f = l.rstrip('\n').split('\t')
        if len(f) > 7 and not l.startswith('#') and all(x == '-' for x in f[4:8]):
            ohne.add(f[0])
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    namen_k, speeds, _arg, _fak = X.kopf_lesen(TXT)
    att = {}
    for i, l in enumerate(L):
        m = re.match(r'# att_number: (\S+)', l)
        if m:
            k = i
            while not (L[k] and not L[k].startswith('#')):
                k += 1
            att[L[k]] = m.group(1)
    fes = nc.Dataset(os.path.join(FES_DIR, 'm2_fes2022.nc'))
    R = [r for r in load_records() if r['lat'] is not None and not r['current']]
    neu, archiv = {}, []
    for r in R:
        if r['file'] != TXT and not r['file'].endswith('harmonics_att_np202_secondary.txt'):
            continue
        a = att.get(r['name'])
        if a not in ohne:
            continue
        z0, w, _e, mer = X.satz_lesen(r['file'], r['name'])
        g_alt = X.greenwich(w['M2'][1], speeds['M2'], mer) % 360
        _amp, gf = sample(fes, r['lat'], r['lon'])
        if gf is not None and abs(wrap(g_alt - gf)) <= FES_TOL:
            print('%-6s %-36s bleibt (M2 %+.0f Grad gegen FES)' % (a, r['name'][:36], wrap(g_alt - gf)))
            continue
        # Gota (Faeroeer) hat nur M2/S2 -- als Spender untauglich. Ohne vollstaendigen Satz
        # in Reichweite (Grimstad: nur Arendal, ohne K1) reicht M2/S2/N2.
        nb = None
        for pflicht in (('M2', 'S2', 'N2', 'K1', 'O1'), ('M2', 'S2', 'N2')):
            nb = spender(r, R, speeds, gf, pflicht)
            if nb:
                break
        if nb is None:
            archiv.append((a, r['name']))
            print('%-6s %-36s kein Nachbar bis %.0f km -> archivieren' % (a, r['name'][:36], BIS_KM))
            continue
        s, d, w2, m2, fak = nb
        hub = 2 * (w['M2'][0] + w['S2'][0])
        f = hub / (2 * (w2['M2'][0] + w2['S2'][0]) * fak) if hub >= 0.5 else 1.0
        rM = rS = f
        con = {}
        for c, (amp, kap) in w2.items():
            if c not in speeds:
                continue
            amp *= fak
            if c == 'M2' or c in SEMI_M:
                f = rM
            elif c in ('S2', 'K2'):
                f = rS
            elif c in SHALLOW:
                f = rM * rM
            elif c in LANGZEIT:
                f = 1.0
            elif c in DIURNAL:
                f = 1.0
            else:
                f = rM if speeds[c] > 20 else 1.0
            G = X.greenwich(kap, speeds[c], m2)
            con[c] = (amp * f, (G + speeds[c] * mer) % 360)        # kappa im Meridian des Satzes
        neu[r['name']] = (a, s['name'], d, con, wrap(g_alt - (gf if gf is not None else g_alt)))
        print('%-6s %-36s <- %-40s %4.0f km  f %.2f/%.2f  (alt %+.0f Grad gegen FES)'
              % (a, r['name'][:36], s['name'][:40], d, rM, rS, neu[r['name']][4]))
    print('\n%d neu, %d ohne Nachbarn' % (len(neu), len(archiv)))
    if archiv:
        out = os.path.join(ROOT, 'harmonics/help/np202_ohne_zeit_%s_loeschen.csv' % dt.date.today().strftime('%Y%m%d'))
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write('datei,name,fehler_prozent,begruendung\n')
            for a, n in archiv:
                fh.write('harmonics/att/harmonics_att_np202_secondary.txt,"%s",100,"NP202 %s ohne Zeitdifferenz, '
                         'Phasen vom fernen Bezugshafen; kein Nachbar bis %.0f km (Oliver 26.10.)"\n' % (n, a, BIS_KM))
        print('->', out)
    if not schreiben:
        return
    shutil.copy(TXT, os.path.join(ROOT, 'harmonics/backup/harmonics_att_np202_secondary.txt.vor_ohne_zeit_%s'
                                  % dt.datetime.now().strftime('%Y%m%d_%H%M')))
    folge = ordnung(L)
    heute = dt.date.today().strftime('%Y%m%d')
    for name, (a, nbname, d, con, alt) in neu.items():
        i = L.index(name)
        k = i + 3
        while k < len(L) and L[k].strip() and not L[k].startswith('#'):
            k += 1
        rumpf = []
        for c in folge:
            if c in con and con[c][0] >= 0.00005:
                rumpf.append('%-15s %7.4f %7.2f' % (c, con[c][0], con[c][1]))
            else:
                rumpf.append('x 0 0')
        L[i + 3:k] = rumpf
        note = ('# note: %s Buch ohne Zeitdifferenz: Phasen/Verhaeltnisse von %s (%.0f km), '
                'Hub aus dem Buch; vorher M2 %+.0f Grad gegen FES' % (heute, nbname.split(',')[0], d, alt))
        L.insert(i, note[:199])
    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    print('geschrieben:', len(neu))


if __name__ == '__main__':
    main(sys.argv)
