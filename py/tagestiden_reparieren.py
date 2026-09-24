#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tagestiden einer NOAA-Uebertragung durch die unabhaengiger Nachbarn ersetzen.

NOAA Table 2 legt EINEN Zeitversatz und EIN Hoehenverhaeltnis auf beide
Baender (siehe Gedaechtnis "NOAA ein Zeitversatz"). Ist der Bezugsort in
einem anderen Gezeitenregime, stimmen die halbtaegigen Tiden, die
taeglichen aber sind die des Bezugsorts: die 51 Davao-Uebertragungen
tragen K1 ~100 / O1 ~90 Grad, der Moro-Golf hat ~135-142 / 113-126
(NAMRIA Pagadian/Polloc/Kalamansig, NP203).

Repariert wird nur, wo die unabhaengigen Saetze (NAMRIA, BIG, Messreihen,
NP203) im Umkreis von 50 km untereinander einig sind (K1 auf 20 Grad) und
einer davon hoechstens 30 km entfernt liegt. Alle Tiden der taeglichen
Gruppe (Winkelgeschwindigkeit 12-17 Grad/h) werden als komplexes, nach
1/Abstand gewichtetes Mittel der Zeugen gesetzt; halbtaegige, Flachwasser-
und langperiodische Tiden sowie Z0 bleiben. Vermerk + confidence 4.

Usage: python3 py/tagestiden_reparieren.py <satzname> [...] [--schreiben]
"""
from __future__ import annotations

import cmath
import datetime as dt
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from health_check import ROOT, km, load_records                   # noqa: E402

DATEI = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_cptt.txt')
UNABH = ('tidetables', 'observations', 'ticon4', 'big_srgi', 'np203')


def konstituenten(pfad, zeile, name):
    """-> {name: (amp, phase)} eines Satzes (Zeile = Namenszeile)."""
    namen = X.kopf_lesen(pfad)[0]
    L = open(pfad, encoding='iso-8859-1').read().split('\n')
    zeile = next(k for k in range(max(0, zeile - 5), zeile + 6) if L[k] == name)   # Namenszeile
    # Phasen stehen je Satz auf dessen Meridian (NP203: +08:00), Hoehen in m oder ft
    mer = L[zeile + 1].split()[0]
    vz = -1 if mer.startswith('-') else 1
    hh, mm = mer.lstrip('+-').split(':')
    stunden = vz * (int(hh) + int(mm) / 60)
    skala = 0.3048 if 'feet' in L[zeile + 2] else 1.0
    sp = X.kopf_lesen(pfad)[1]
    sp = sp if isinstance(sp, dict) else dict(zip(namen, sp))
    out = {}
    for n, l in zip(namen, L[zeile + 3: zeile + 3 + len(namen)]):
        f = l.split()
        if f and f[0] != 'x':
            out[n] = (float(f[1]) * skala, (float(f[2]) - float(sp[n]) * stunden) % 360)
    return out


def main(argv):
    ziele = [a for a in argv if not a.startswith('--')]
    R = [r for r in load_records() if r['lat'] is not None and not r['current']]
    unabh = [r for r in R if any(k in r['file'] for k in UNABH)]
    namen, speeds, _a, _f = X.kopf_lesen(DATEI)
    sp = speeds if isinstance(speeds, dict) else dict(zip(namen, speeds))
    taeglich = {n for n in namen if 12 <= float(sp[n]) <= 17}
    L = open(DATEI, encoding='iso-8859-1').read().split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    geaendert = []
    for ziel in ziele:
        r = next(x for x in R if x['name'] == ziel and x['file'].endswith('harmonics_noaa_cptt.txt'))
        zeugen = [x for x in unabh if km(r, x) <= 50]
        gew = [(1 / max(km(r, x), 1.0), konstituenten(x['file'], x['line'], x['name'])) for x in zeugen]
        i = L.index(ziel)
        alt_k1 = new_k1 = None
        for j, n in enumerate(namen):
            if n not in taeglich:
                continue
            z = sum(w * cmath.rect(k.get(n, (0, 0))[0], -math.radians(k.get(n, (0, 0))[1])) for w, k in gew)
            z /= sum(w for w, _ in gew)
            a, g = abs(z), (-math.degrees(cmath.phase(z))) % 360
            if n == 'K1':
                alt_k1, new_k1 = L[i + 3 + j], (a, g)
            L[i + 3 + j] = f'{n:<16}{a:.4f}  {g:.2f}' if a >= 0.00005 else 'x 0 0'
        # Vermerk vor die Namenszeile, confidence senken
        k = i
        while not L[k].startswith('# BEGIN HOT'):
            if L[k].startswith('# confidence:'):
                L[k] = '# confidence: 4'
            k -= 1
        L.insert(i, f'# note: {heute} Tagestiden ersetzt (Davao-Uebertragung, K1 war {alt_k1.split()[2]} Grad):'
                    f' 1/Abstand-Mittel aus')
        L.insert(i + 1, '# note: ' + '; '.join(f"{x['name'].split(',')[0]} {km(r, x):.0f} km" for x in zeugen)[:140])
        geaendert.append((ziel, alt_k1.split()[2], f'{new_k1[1]:.0f}', len(zeugen)))
    for z in geaendert:
        print(f'  {z[0][:44]:44} K1 {z[1]:>6} -> {z[2]:>4} Grad  ({z[3]} Zeugen)')
    if '--schreiben' in argv:
        shutil.copy(DATEI, os.path.join(ROOT, 'harmonics/backup',
                                        f'harmonics_noaa_cptt.txt.vor_tagestiden_{heute}'))
        open(DATEI, 'w', encoding='iso-8859-1').write('\n'.join(L))
        print(f'-> {len(geaendert)} Saetze geschrieben')
    else:
        print('(Probe; mit --schreiben aendern)')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
