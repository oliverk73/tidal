#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Island 1.11.2026: Einzelfehler der Altsaetze, belegt durch LHG-Tafla II, sjolag.is und Nachbarn.

Die Saetze aus Sjomaelingar Islands (harmonics-2004/1997) treffen Tafla I auf 2-3 min, wo sie
heil sind. Die fuenf hier tragen je eine verschriebene Phase; die Zeugen liegen um weniger
als 5 Grad am verbesserten Wert. Veraendert werden nur die genannten Zeilen.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F04 = os.path.join(ROOT, 'harmonics/classic/harmonics-2004-06-14_mod.txt')
F97 = os.path.join(ROOT, 'harmonics/classic/harmonics-1997-05-25_mod.txt')
# (Datei, Station, {Tide: (Amplitude oder None, Phase)}, Notiz)
FIXES = [
    (F04, 'Seyðisfjörður, Iceland', {'M2': (None, 32.00)},
     'M2-Phase 319.70 war 31.97 mit verrutschtem Komma: LHG Tafla II 31.7, FES 32.6, Loðmundarfjörður und Neskaupstaður 30-32.'),
    (F04, 'Hornafjörður, Iceland', {'M2': (None, 175.10)},
     'M2-Phase 75.10 war 175.10: LHG Tafla II 179.5, N2 und S2 passen dazu; FES taugt in der Lagune nicht.'),
    (F04, 'Þingeyri, Iceland', {'M2': (None, 235.90)},
     'M2-Phase 215.90 war 235.90: LHG Tafla II 235.7, FES 233.3.'),
    (F04, 'Patreksfjörður, Iceland', {'S2': (None, 262.60)},
     'S2-Phase 222.60 war 262.60: sjolag.is 258.7, Sveinseyri 264.6, FES 258.'),
    (F04, 'Akureyri, Iceland', {'M2': (None, 315.00), 'O1': (0.0590, 67.90)},
     'M2-Phase 305.00 war 315.00: LHG Tafla II 314.5, sjolag.is 315.1; O1 (0.015/90.9) von Siglufjörður.'),
    (F97, 'Hrútafjörður, Iceland', {'K1': (None, 141.50), 'P1': (None, 132.00)},
     'K1/P1-Phasen 351/359 passten zu keinem Nachbarn (alle um 140); Phasen von Hólmavík.'),
]


def main(nur=0):
    for pfad in (F04, F97)[nur:]:
        z = open(pfad, encoding='iso-8859-1').read().split('\n')
        for datei, name, tiden, notiz in FIXES:
            if datei != pfad:
                continue
            k = z.index(name)
            for j in range(k + 3, k + 178):
                if z[j].startswith('#'):
                    break
                f = z[j].split()
                if len(f) == 3 and f[0] in tiden:
                    a, g = tiden[f[0]]
                    z[j] = re.sub(r'\S+\s+\S+$', lambda _m: f'{f[1] if a is None else f"{a:.4f}"}  {g:.2f}', z[j])
            i = k
            while not z[i].startswith('# !longitude'):
                i -= 1
            z[i:i] = [f'# note: 20261101 {notiz}']
        open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(z))


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
