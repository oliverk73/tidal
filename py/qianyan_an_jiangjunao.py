#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qianyan [Knob Rock] (NOAA CPTT, Table-2-Uebertragung von Xiamen) an den
Nachbarn Jiangjun'ao (NMDIS T123, 13 km, Konfidenz 7) anschliessen.

Anlass 11.10.2026 (Oliver): Der Buch-Satz hat M2 1.78 m, S2 0.073 m. Jiangjun'ao
(offene Kueste, 13 km) und FES2022 an der Position liegen beide bei M2 1.34 m,
S2/M2 0.27-0.31 (Buch: 0.04); die Phasen des Buchs stimmen dagegen auf 1-3 deg.

Uebernommen werden Amplitude und Phase aller Konstituenten, die der Nachbar
fuehrt (Zeilenraster gleich, ein "x 0 0" ist ein freier Platz). Plaetze, die
beim Nachbarn frei sind, behalten den Buchwert (M1, M8, S1, SA). Name,
Position, Zeitzone, Kopf und Z0 (Buch-Seekartennull, 2.4079 m) bleiben.

Aufruf: venv/bin/python py/qianyan_an_jiangjunao.py            # nur anzeigen
        venv/bin/python py/qianyan_an_jiangjunao.py --schreiben
"""
from __future__ import annotations

import difflib
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'py'))
from sicher_schreiben import schreiben                             # noqa: E402

ZIEL = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_cptt.txt')
QUELLE = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
NAME_Z = 'Qianyan [Knob Rock], Fujian, China'
NAME_Q = "Jiangjun'ao, Fujian, China"
HEUTE = time.strftime('%Y%m%d')


def block(lines, name):
    ks = [k for k, z in enumerate(lines) if z == name and k + 1 < len(lines)
          and lines[k + 1].startswith(('+', '-')) and ':' in lines[k + 1]]
    if len(ks) != 1:
        sys.exit(f'{name}: {len(ks)} Treffer')
    k = ks[0]
    j = k + 3
    while j < len(lines) and lines[j] and not lines[j].startswith('#'):
        j += 1
    return k, k + 3, j          # Namenszeile, erste Konstituente, Ende


def main():
    z = open(ZIEL, encoding='iso-8859-1').read().split('\n')
    q = open(QUELLE, encoding='iso-8859-1').read().split('\n')
    kz, az, ez = block(z, NAME_Z)
    kq, aq, eq = block(q, NAME_Q)
    nz = [s.split()[0] for s in z[az:ez]]
    nq = [s.split()[0] for s in q[aq:eq]]
    if len(nz) != len(nq) or any(a != b and 'x' not in (a, b) for a, b in zip(nz, nq)):
        sys.exit(f'Zeilenraster verschieden: {len(nz)} gegen {len(nq)}')
    neu_block = [b if b.split()[0] != 'x' else a for a, b in zip(z[az:ez], q[aq:eq])]
    behalten = [a.split()[0] for a, b in zip(z[az:ez], q[aq:eq])
                if b.split()[0] == 'x' and a.split()[0] != 'x']
    print(f'  {sum(1 for b in q[aq:eq] if b.split()[0] != "x")} Konstituenten vom Nachbarn, '
          f'Buchwerte behalten: {", ".join(behalten)}')
    if z[kz + 1] != '+00:00 :Asia/Shanghai' or q[kq + 1] != '+00:00 :Asia/Shanghai':
        sys.exit('Zeitzone nicht UTC')
    alt = {s.split()[0]: s for s in z[az:ez]}
    neu = z[:az] + neu_block + z[ez:]
    note = [f"# note: {HEUTE} Konstanten von Jiangjun'ao (NMDIS T123, 13 km, offene Kueste) uebernommen;",
            '# note: Buch-M2 1.78 war ~30 % zu gross, S2 0.073 viel zu klein; Nachbar und FES2022 stimmen',
            '# note: ueberein (M2 1.34, S2/M2 0.27-0.31). Z0 aus dem Buch behalten. Siehe py/qianyan_an_jiangjunao.py.']
    neu[kz:kz] = note
    for c in ('M2', 'S2', 'K2', 'N2', 'K1', 'O1'):
        a = alt[c].split()
        b = next(s for s in neu_block if s.split()[0] == c).split()
        print(f'  {c:3s} {float(a[1]):.4f} @ {float(a[2]):6.2f}  ->  {float(b[1]):.4f} @ {float(b[2]):6.2f}')
    d = list(difflib.unified_diff(z, neu, lineterm='', n=0))
    print(f'  {sum(1 for x in d if x[:1] == "-" and x[:3] != "---")} Zeilen entfernt, '
          f'{sum(1 for x in d if x[:1] == "+" and x[:3] != "+++")} neu')
    if '--schreiben' in sys.argv:
        shutil.copy2(ZIEL, os.path.join(ROOT, 'harmonics/backup', f'harmonics_noaa_cptt_pre_qianyan_{HEUTE}.txt'))
        schreiben(ZIEL, '\n'.join(neu))
        print('  geschrieben')


if __name__ == '__main__':
    main()
