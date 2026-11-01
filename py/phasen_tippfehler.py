#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verbessert Tippfehler aus harmonics/help/phasenprobe_20261101.csv (1.11.2026).

Aufgenommen ist nur, was eine Ziffer aendert, Altersprobe UND FES auf <8 Grad trifft, Amplitude
>=5 cm hat und nicht zu einer Gruppe gleich verschobener Nachbarn gehoert (N2 Queensland und
Tasman-Halbinsel sind systematisch, kein Tippfehler; sie bleiben in der Liste).
Section Cove und Misaki haben zwei passende Ziffern; genommen ist die mit dem kleineren groessten Abstand.
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = 'harmonics/classic/harmonics-1997-05-25_mod.txt'
B = 'harmonics/classic/harmonics-2004-06-14_mod.txt'
FIXES = [(A, 'Rota, Spain', 'O1', 302.00, '300.7', '300.2'),
         (A, 'Ibo, Mozambique', 'N2', 57.00, '55.2', '61.9'),
         (B, 'Aulatsivik Point, Nunavut, Canada', 'N2', 148.10, '148.3', '148.9'),
         (B, 'Cape Legendre, Western Australia, Australia', 'P1', 288.40, '284.7', '288.5'),
         (B, 'Double Bay, Queensland, Australia', 'N2', 290.00, '293.8', '285.3'),
         (B, 'Great Glennie Island, Victoria, Australia', 'N2', 291.10, '292.2', '287.9'),
         (B, 'Gabo Island, Victoria, Australia', 'O1', 63.00, '55.6', '63.9'),
         (B, 'Section Cove, British Columbia, Canada', 'N2', 9.30, '14.3', '12.9'),
         (B, 'Misaki (Fuke), Osaka, Japan', 'N2', 190.69, '188.2', '184.4')]


def main():
    for pfad in (A, B):
        p = os.path.join(ROOT, pfad)
        z = open(p, encoding='iso-8859-1').read().split('\n')
        for datei, name, tide, neu, alter, fes in FIXES:
            if datei != pfad:
                continue
            k = z.index(name)
            for j in range(k + 3, k + 178):
                if z[j].startswith('#'):
                    raise SystemExit(f'{name}: {tide} nicht gefunden')
                f = z[j].split()
                if len(f) == 3 and f[0] == tide:
                    alt = f[2]
                    z[j] = f'{tide:<16}{f[1]}  {neu:.2f}'
                    break
            i = k
            while not z[i].startswith('# !longitude'):
                i -= 1
            z[i:i] = [f'# note: 20261101 {tide}-Phase {alt} war verschrieben: Altersprobe {alter}, FES {fes} (py/phasenprobe.py).']
        open(p, 'w', encoding='iso-8859-1').write('\n'.join(z))


if __name__ == '__main__':
    main()
