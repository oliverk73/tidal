#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Einzelne falsche Phasen aus harmonics/help/phasenprobe_20261101.csv, die keine Ziffer erklaert (1.11.2026).

Neue Phase: Altersprobe und FES, wo vorhanden auch der naechste Nachbar. Bata bleibt: NP208 am selben Ort
stuetzt die alte Phase eher als FES.
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = 'harmonics/classic/harmonics-1997-05-25_mod.txt'
B = 'harmonics/classic/harmonics-2004-06-14_mod.txt'
# Datei, Station, Tide, Amplitude oder None, Phase
FIXES = [(B, 'Kieta Harbour, North Solomons, Papua New Guinea', 'N2', 0.0600, 78.00),
         (B, 'Bonne Island, Nunavut, Canada', 'N2', None, 167.00),
         (B, "Pointe Heath (Île d'Anticosti), Québec, Canada", 'O1', None, 198.00),
         (B, 'Finsch Harbour, Papua New Guinea', 'O1', None, 175.00),
         (B, 'Inenew Passage, Québec, Canada', 'O1', None, 80.00),
         (B, 'Mary Ann Haven, Western Australia, Australia', 'P1', None, 322.00),
         (B, "Wasque Point (Chappaquiddick Island), Massachusetts", 'O1', None, 126.40),
         (A, 'Beachley (Aust, River Severn), England, United Kingdom', 'O1', None, 14.00),
         (A, 'Oamaru, New Zealand', 'O1', None, 29.50),
         (A, 'Melchior Harbour, Antarctica', 'N2', None, 133.00),
         (A, 'Pontal do Sul (Canal Galheta), Paraná, Brazil', 'N2', None, 144.00),
         (A, 'Dakhla, Western Sahara', 'O1', None, 266.00),
         (A, 'Nouadhibou, Mauritania', 'O1', None, 272.00),
         (A, 'Raivavae, Austral Islands, French Polynesia', 'N2', None, 341.00)]


def main():
    for pfad in (A, B):
        p = os.path.join(ROOT, pfad)
        z = open(p, encoding='iso-8859-1').read().split('\n')
        for datei, name, tide, amp, neu in FIXES:
            if datei != pfad:
                continue
            try:
                k = z.index(name)
            except ValueError:
                print('fehlt:', name)
                continue
            alt = None
            for j in range(k + 3, k + 178):
                if z[j].startswith('#'):
                    break
                f = z[j].split()
                if len(f) == 3 and f[0] == tide:
                    alt = f[2]
                    z[j] = f'{tide:<16}{f[1] if amp is None else f"{amp:.4f}"}  {neu:.2f}'
                    break
            if alt is None:
                print('keine Tide:', name, tide)
                continue
            i = k
            while not z[i].startswith('# !longitude'):
                i -= 1
            z[i:i] = [f'# note: 20261101 {tide}-Phase {alt} passte weder zum Satz noch zu FES (py/phasenprobe.py).']
        open(p, 'w', encoding='iso-8859-1').write('\n'.join(z))


if __name__ == '__main__':
    main()
