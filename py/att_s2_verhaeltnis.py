#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Setzt S2/M2 gemeldeter ATT-Uebertragungen auf den Wert der Zeugen (1.11.2026).

Grundlage harmonics/help/att_hubprobe_20261101.csv. Bei kleinem Hub oder fehlendem Niedrigwasser gibt die
auf 0,1 m gerundete Buchzeile kein brauchbares S2. Der Springhub M2+S2 des Buchs ist dagegen belastbar und
bleibt erhalten; aufgeteilt wird er nach dem Mittel von Zeuge und FES, wenn beide auf 35 % einig sind.
Phasen und Tagestiden bleiben. Borj el Hsar ist von Hand ergaenzt (Sfax, El Abassia, FES).
"""
from __future__ import annotations

import csv
import os

import rebuild_np202_transfer as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S_BAND = {'K2', 'T2', 'R2', 'MS4'}


def main():
    z = list(csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/att_hubprobe_20261101.csv'), encoding='utf-8')))
    faelle = [(r['datei'], r['name'], (float(r['z_verh']) + float(r['f_verh'])) / 2, f"{r['zeuge'][:30]}/FES")
              for r in z if 'S2/M2' in r['fehler']
              and abs(float(r['z_verh']) - float(r['f_verh'])) <= 0.35 * max(float(r['z_verh']), float(r['f_verh']))]
    faelle.append(('harmonics_att_np208_secondary.txt', 'Borj el Hsar (Kerkennah), Tunisia', 0.53, 'El Abassia/FES'))
    print(len(faelle))
    for d in sorted({f[0] for f in faelle}):
        p = os.path.join(ROOT, 'harmonics/att', d)
        t = open(p, encoding='iso-8859-1').read().split('\n')
        for _d, name, v, zeuge in (f for f in faelle if f[0] == d):
            k = t.index(name)
            a = {}
            for j in range(k + 3, k + 178):
                if t[j].startswith('#'):
                    break
                f = t[j].split()
                if len(f) == 3 and f[0] != 'x':
                    a[f[0]] = float(f[1])
            m2 = (a['M2'] + a['S2']) / (1 + v)
            s2 = v * m2
            rM, rS = m2 / a['M2'], s2 / a['S2'] if a['S2'] else 0
            for j in range(k + 3, k + 178):
                if t[j].startswith('#'):
                    break
                f = t[j].split()
                if len(f) != 3 or f[0] == 'x':
                    continue
                if f[0] == 'M2':
                    w = m2
                elif f[0] == 'S2':
                    w = s2
                elif f[0] in S_BAND and rS:
                    w = float(f[1]) * rS
                elif f[0] in R.SEMI_M:
                    w = float(f[1]) * rM
                else:
                    continue
                t[j] = f'{f[0]:<15s} {w:7.4f} {f[2]:>7s}'
            i = k
            while not t[i].startswith('# !units'):
                i -= 1
            t[i:i] = [f"# note: 20261101 S2/M2 {a['S2'] / a['M2']:.2f} -> {v:.2f} ({zeuge}), Springhub des Buchs behalten (py/att_s2_verhaeltnis.py)."]
            print(f"{name[:40]:40s} M2 {a['M2']:.3f}->{m2:.3f} S2 {a['S2']:.3f}->{s2:.3f}")
        open(p, 'w', encoding='iso-8859-1').write('\n'.join(t))


if __name__ == '__main__':
    main()
