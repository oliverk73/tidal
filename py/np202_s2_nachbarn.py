#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zu grosses S2 in NP202-Uebertragungen auf Nachbarwerte setzen (1.11.2026).

Holmiabukta und Skansbukta: Buch nur MHWS, Rest "no data" -> Bezugshafen-NW blieben stehen.
Kuba: Buchhoehen auf 0,1 m bei 0,5 m Hub und Tagestiden im Hub geben kein brauchbares S2.
Veraendert werden die Amplituden des M2- und S2-Bandes; Phasen und Tagestiden bleiben.

Usage: python3 py/np202_s2_nachbarn.py
"""
from __future__ import annotations

import os

import rebuild_np202_transfer as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'harmonics/att/harmonics_att_np202_secondary.txt')
S_BAND = {'K2', 'T2', 'R2', 'MS4'}
# Name: (M2 oder None, S2, Z0 oder None, Notiz)
FAELLE = {
    'Holmiabukta, Svalbard': (0.450, 0.130, 0.72, 'Buch nur MHWS 1.3; S2/M2 und Z0/M2 von Danskegat, Kongsfjorden, Ny-Alesund (war 0.92).'),
    'Skansbukta, Svalbard': (0.550, 0.210, 1.05, 'Buch nur MHWS 1.9; Longyearbyen x1.9/1.8 (S2/M2 war 0.95).'),
    'Cienfuegos, Cuba': (None, 0.0189, None, 'S2/M2 von Punta Pasacaballos (9 km, 0.13); war 0.71, Buchrundung.'),
    'Arroyos de Mantua, Cuba': (None, 0.0108, None, 'S2/M2 von La Coloma/Cabo San Antonio (0.14); war 0.95, Buchrundung.'),
    'Bahía Honda, Cuba': (None, 0.0479, None, 'S2/M2 von Bahia de Cabanas (20 km, 0.33); war 0.71, Buchrundung.'),
}


def main():
    z = open(P, encoding='iso-8859-1').read().split('\n')
    for name, (m2, s2, z0, notiz) in FAELLE.items():
        k = z.index(name)
        alt = {f[0]: float(f[1]) for f in (x.split() for x in z[k + 3:k + 178]) if len(f) == 3 and f[0] != 'x'}
        rM = m2 / alt['M2'] if m2 else 1.0
        rS = s2 / alt['S2']
        for j in range(k + 3, k + 178):
            if z[j].startswith('#'):
                break
            f = z[j].split()
            if len(f) != 3 or f[0] == 'x':
                continue
            if f[0] == 'S2':
                a = s2
            elif f[0] in S_BAND:
                a = float(f[1]) * rS
            elif f[0] in R.SEMI_M or f[0] == 'M2':
                a = float(f[1]) * rM
            else:
                continue
            z[j] = f'{f[0]:<15s} {a:7.4f} {f[2]:>7s}'
        if z0:
            z[k + 2] = f'{z0:.4f} meters'
        i = k
        while not z[i].startswith('# !units'):
            i -= 1
        z[i:i] = [f'# note: 20261101 {notiz}']
    open(P, 'w', encoding='iso-8859-1').write('\n'.join(z))


if __name__ == '__main__':
    main()
