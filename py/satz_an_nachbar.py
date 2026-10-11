#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Einen Satz an einen gemessenen Nachbarn anschliessen (Verallgemeinerung von
py/qianyan_an_jiangjunao.py).

Uebernommen werden Amplitude und Phase aller Konstituenten, die der Nachbar
fuehrt; Plaetze, die beim Nachbarn frei sind ("x 0 0"), behalten den Wert des
Satzes. Name, Position, Zeitzone, Kopf und Z0 des Satzes bleiben.
Beide Saetze muessen dieselbe Zeitzone haben (hier UTC) und dasselbe Raster.

Aufruf: python3 py/satz_an_nachbar.py ZIEL_DATEI "ZIEL_NAME" QUELL_DATEI "QUELL_NAME" "BEGRUENDUNG" [--schreiben]
"""
from __future__ import annotations

import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'py'))
from sicher_schreiben import schreiben                             # noqa: E402

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
    return k, k + 3, j


def main(a):
    ziel, zname, quelle, qname, grund = a[:5]
    zp, qp = os.path.join(ROOT, ziel), os.path.join(ROOT, quelle)
    z = open(zp, encoding='iso-8859-1').read().split('\n')
    q = open(qp, encoding='iso-8859-1').read().split('\n')
    kz, az, ez = block(z, zname)
    kq, aq, eq = block(q, qname)
    zone = z[kz + 1].split()[0]
    if zone != q[kq + 1].split()[0]:
        sys.exit(f'Zeitzone verschieden: {z[kz + 1]} gegen {q[kq + 1]}')
    nz = [s.split()[0] for s in z[az:ez]]
    nq = [s.split()[0] for s in q[aq:eq]]
    if len(nz) != len(nq) or any(x != y and 'x' not in (x, y) for x, y in zip(nz, nq)):
        sys.exit(f'Zeilenraster verschieden: {len(nz)} gegen {len(nq)}')
    block_neu = [b if b.split()[0] != 'x' else x for x, b in zip(z[az:ez], q[aq:eq])]
    behalten = [x.split()[0] for x, b in zip(z[az:ez], q[aq:eq])
                if b.split()[0] == 'x' and x.split()[0] != 'x']
    print(f'  {sum(1 for b in q[aq:eq] if b.split()[0] != "x")} Konstituenten vom Nachbarn, '
          f'Satzwerte behalten: {", ".join(behalten) or "-"}')
    alt = {s.split()[0]: s for s in z[az:ez]}
    neu_d = {s.split()[0]: s for s in block_neu}
    for c in ('M2', 'S2', 'K2', 'N2', 'K1', 'O1'):
        x, y = alt[c].split(), neu_d[c].split()
        print(f'  {c:3s} {float(x[1]):.4f} @ {float(x[2]):6.2f}  ->  {float(y[1]):.4f} @ {float(y[2]):6.2f}')
    neu = z[:az] + block_neu + z[ez:]
    neu[kz:kz] = [f"# note: {HEUTE} Konstanten von {qname.split(',')[0]} ({os.path.basename(quelle)}) uebernommen;",
                  f'# note: {grund} Z0 behalten. Siehe py/satz_an_nachbar.py.']
    txt = '\n'.join(neu)
    txt.encode('iso-8859-1')
    if '--schreiben' in a:
        sich = os.path.join(ROOT, 'harmonics/backup',
                            f"{os.path.basename(ziel)[:-4]}_pre_nachbar_{HEUTE}.txt")
        shutil.copy2(zp, sich)
        schreiben(zp, txt)
        print('  geschrieben; Sicherung', os.path.basename(sich))


if __name__ == '__main__':
    main(sys.argv[1:])
