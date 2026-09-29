#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tragen NOAA-Uebertragungen die Tagestiden ihres Bezugsorts?

NOAA Table 2 legt EINEN Zeitversatz und EIN Hoehenverhaeltnis auf beide
Baender. Liegt der Nebenort in einem anderen Gezeitenregime als der
Bezugsort, stimmen die halbtaegigen Tiden, die taeglichen aber sind die des
Bezugsorts (24.09.2026 an den 51 Davao-Uebertragungen gezeigt).

Je NOAA-Uebertragung (alle harmonics_noaa_*.txt ausser Stroemungen):
  Bezugsort aus dem Vermerk "transfer from <Ort>"
  Vergleich K1-Phase gegen den naechsten unabhaengigen Satz (NAMRIA/NMDIS-
  Tafel-Fits, BIG, Messreihen, TICON, NP203) bis 60 km
  Klasse:  ok           |dK1| < 20 Grad
           zwilling     falsch, besserer Satz < 3 km
           reparierbar  falsch, unabhaengige Saetze <= 50 km einig (K1 +-20),
                        einer davon <= 30 km
           unsicher     falsch, Zeugen uneinig oder zu weit
           ohne         kein unabhaengiger Satz <= 60 km

Ausgabe: harmonics/help/noaa_bezug_tagestiden.csv und je Bezugsort eine
Zeile Uebersicht auf stdout. Aendert nichts; braucht kein Netz.

Usage: python3 py/noaa_bezug_tagestiden.py
"""
from __future__ import annotations

import cmath
import collections
import csv
import glob
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT, km, load_records                   # noqa: E402

AUS = os.path.join(ROOT, 'harmonics/help/noaa_bezug_tagestiden.csv')
UNABH = ('tidetables', 'observations', 'ticon4', 'big_srgi', 'np20', 'pushidrosal')


def ph(r, c):
    return -math.degrees(cmath.phase(r['z'].get(c, 0))) % 360


def dphi(a, b):
    return (a - b + 180) % 360 - 180


def main():
    R = [r for r in load_records() if r['lat'] is not None and not r['current']]
    unabh = [r for r in R if any(k in os.path.basename(r['file']) for k in UNABH)]
    texte = {os.path.basename(f): open(f, encoding='iso-8859-1').read().split('\n')
             for f in glob.glob(os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_*.txt'))
             if 'current' not in f}
    zeilen = []
    for r in R:
        L = texte.get(os.path.basename(r['file']))
        if L is None:
            continue
        kopf = '\n'.join(L[max(0, r['line'] - 40):r['line']])
        m = re.search(r'transfer from (.+?) \(no\.', kopf)
        if not m or 'Tagestiden ersetzt' in kopf:
            continue
        if abs(r['z'].get('K1', 0)) < 0.03:        # Tagestide zu klein, Phase ohne Aussage
            continue
        nb = sorted((x for x in unabh if km(r, x) <= 60), key=lambda x: km(r, x))
        if not nb:
            klasse, dk, zeuge = 'ohne', '', ''
        else:
            dk = dphi(ph(r, 'K1'), ph(nb[0], 'K1'))
            zeuge = f"{nb[0]['name']} [{os.path.basename(nb[0]['file'])}] {km(r, nb[0]):.0f} km"
            if abs(dk) < 20:
                klasse = 'ok'
            elif km(r, nb[0]) < 3:
                klasse = 'zwilling'
            else:
                z = [x for x in nb if km(r, x) <= 50]
                ks = [ph(x, 'K1') for x in z]
                spanne = max((abs(dphi(a, b)) for a in ks for b in ks), default=0)
                klasse = 'reparierbar' if z and km(r, z[0]) <= 30 and spanne <= 20 else 'unsicher'
            dk = f'{dk:+.0f}'
        zeilen.append(dict(datei=os.path.basename(r['file']), satz=r['name'], bezug=m.group(1),
                           k1=f"{ph(r, 'K1'):.0f}", dk1=dk, klasse=klasse, zeuge=zeuge))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print(f'-> {os.path.relpath(AUS, ROOT)}: {len(zeilen)} Uebertragungen')
    print(' ', dict(collections.Counter(z['klasse'] for z in zeilen)))
    je = collections.defaultdict(collections.Counter)
    for z in zeilen:
        je[z['bezug']][z['klasse']] += 1
    schlecht = sorted(je.items(), key=lambda kv: -(kv[1]['zwilling'] + kv[1]['reparierbar'] + kv[1]['unsicher']))
    print('\nBezugsorte mit den meisten falschen Tagestiden:')
    for bezug, c in schlecht[:40]:
        falsch = c['zwilling'] + c['reparierbar'] + c['unsicher']
        if not falsch:
            break
        print(f'  {bezug[:40]:40} falsch {falsch:3} (zwilling {c["zwilling"]}, reparierbar {c["reparierbar"]},'
              f' unsicher {c["unsicher"]})  ok {c["ok"]}  ohne Zeugen {c["ohne"]}')


if __name__ == '__main__':
    sys.exit(main())
