#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uebertraegt die NOAA-Saetze im Anadyr-Golf von Admiralty Anadyr (8369) statt von Pusan.

Oliver 17.10.2026: Bukhta Melkaya, Kosa Salomatova, Kosa Russkaya Koshka und Kosa Strelka sind im
NOAA-Buch (Table 2, Nr. 91-99) auf Pusan (Korea) bezogen und tragen dessen Verhaeltnisse
(S2/M2 0.33-0.44, (K1+O1)/M2 0.25), im Golf gelten nach FES 0.12 und 0.45. Das Buch fuehrt auch
"Anadyr River entrance" (Nr. 97) gegen Pusan; der Unterschied Station minus Nr. 97 ist damit die
Uebertragung von Anadyr. Bezug ist der Admiralty-Satz Anadyr (8369, eigene Analyse; Part-II-Probe
5-38 min).

  Zeit:  mittlere Differenz (dtHW+dtLW)/2 Station minus Nr. 97, eine Verschiebung fuer alle Tiden
         wie in Table 2.
  Hub:   Verhaeltnis der mittleren Hube (mean_ft) Station / Nr. 97 fuer alle Amplituden.
  Z0:    Anadyr-Z0 mal Verhaeltnis des Mittelwassers (mtl_ft).
Name, Position, Meridianzeile und alle Vermerke der Saetze bleiben.

Usage: venv/bin/python py/anadyr_neu_uebertragen.py [--schreiben]
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_cptt.txt')
BEZUG = (os.path.join(ROOT, 'harmonics/att/harmonics_att_np204_secondary.txt'), 'Anadyr, Chukotka Autonomous Okrug, Russia')
STATIONEN = {91: 'Kosa Russkaya Koshka, Chukotka Autonomous Okrug, Russia',
             93: 'Kosa Salomatova, Chukotka Autonomous Okrug, Russia',
             95: 'Bukhta Melkaya, Chukotka Autonomous Okrug, Russia',
             99: 'Kosa Strelka (Anadyrskiy Zaliv), Chukotka Autonomous Okrug, Russia'}


def main(argv):
    B = {b['no']: b for b in json.load(open(os.path.join(ROOT, 'harmonics/help/cptt2018_table2_full.json')))}
    r = B[97]
    namen, speeds, _, _ = X.kopf_lesen(ZIEL)
    z0a, wa, _, ma = X.satz_lesen(*BEZUG)
    L = open(ZIEL, encoding='iso-8859-1').read().split('\n')
    for no, name in STATIONEN.items():
        b = B[no]
        dt_min = (b['dtHW'] + b['dtLW']) / 2 - (r['dtHW'] + r['dtLW']) / 2
        k = b['mean_ft'] / r['mean_ft']
        z0 = z0a * b['mtl_ft'] / r['mtl_ft']
        _, wa_alt, _, ms = X.satz_lesen(ZIEL, name)
        neu = {}
        for c, (a, g) in wa.items():
            if c not in speeds:
                continue
            greenwich = g - speeds[c] * ma
            neu[c] = (a * k, (greenwich + speeds[c] * ms + speeds[c] * dt_min / 60.0) % 360)
        i = L.index(name)
        assert re.match(r'^-?[\d.]+ meters$', L[i + 2]), L[i + 2]
        j = i + 3
        while j < len(L) and (L[j] == 'x 0 0' or re.match(r'^\S+\s+[\d.]+\s+[\d.]+$', L[j])):
            j += 1
        assert j - (i + 3) == len(namen), (name, j - i - 3, len(namen))
        L[i + 2] = '%.4f meters' % z0
        L[i + 3:j] = ['%-15s %.4f  %.2f' % (c, *neu[c]) if c in neu and neu[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        L.insert(i, '# note: 20261017 neu von Admiralty Anadyr (8369) statt Pusan uebertragen: Buch Nr.%d minus Nr.97 '
                    '%+.0f min, Hub x%.2f (Oliver).' % (no, dt_min, k))
        def f(w, c):
            return '%.3f@%3.0f' % w[c] if c in w else '-'
        print('%-62s %+5.0f min x%.2f  alt M2 %s S2 %s K1 %s | neu M2 %s S2 %s K1 %s O1 %s' % (
            name, dt_min, k, f(wa_alt, 'M2'), f(wa_alt, 'S2'), f(wa_alt, 'K1'), f(neu, 'M2'), f(neu, 'S2'), f(neu, 'K1'), f(neu, 'O1')))
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L))
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
