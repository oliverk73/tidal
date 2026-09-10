#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dreht einzelne Saetze um einen belegten Zeitfehler.

Ein reiner Zeitfehler verschiebt alle Partialtiden um dieselbe Zeit. Liegt
ein Satz um D Stunden zu frueh, kommt jede Phase um Geschwindigkeit mal D
dazu (g' = g + w*D); zu spaet entsprechend negativ. Amplituden und Z0
bleiben. Gedreht wird nur, was als ganze Stunde (oder halbe/Dreiviertel-
stunde in Zonen mit solchem Versatz) belegt ist -- ein krummer Betrag, den
man nur am Nachbarn abliest, macht den Satz zur zeitlichen Kopie des
Nachbarn (Oliver, 10.09.2026).

Liste: CSV mit datei, name, stunden, grund  (stunden = um so viel SPAETER legen)

Usage: python3 py/zeitfehler_drehen.py <liste.csv> [--schreiben]
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transfer_zonen_richten import speeds                          # noqa: E402
from health_check import MERIDIAN                                  # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEUTE = dt.date.today().strftime('%Y%m%d')


def main(argv):
    liste = list(csv.DictReader(open(argv[0], encoding='utf-8')))
    nach = {}
    for z in liste:
        nach.setdefault(z['datei'], []).append(z)
    for datei, zs in nach.items():
        pfad = os.path.join(ROOT, datei)
        sp = speeds(pfad)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        for z in zs:
            idx = [k for k, l in enumerate(lines) if l == z['name']
                   and k + 1 < len(lines) and MERIDIAN.match(lines[k + 1])]
            if len(idx) != 1:
                print(f'  NICHT EINDEUTIG ({len(idx)}): {z["name"]} in {datei}')
                continue
            k = idx[0]
            d = float(z['stunden'])
            n = 0
            j = k + 3
            while j < len(lines) and lines[j] and not lines[j].startswith('#'):
                p = lines[j].split()
                if p[0] != 'x' and p[0] in sp and len(p) >= 3:
                    g = (float(p[2]) + sp[p[0]] * d) % 360
                    lines[j] = f'{p[0]:<16}{float(p[1]):.4f}  {g:.2f}'
                    n += 1
                j += 1
            lines[k:k] = [f"# note: {HEUTE} Phasen um {d:+.2f} h gedreht (Zeitfehler): {z['grund'][:60]}",
                          '# note: -- Siehe py/ticon_zeitpruefung.py und py/zeitfehler_drehen.py.']
            print(f'  {z["name"][:44]:44} {d:+.2f} h, {n} Partialtiden')
        if '--schreiben' in argv:
            shutil.copy2(pfad, os.path.join(ROOT, 'harmonics/backup',
                                            os.path.basename(pfad) + f'.vor_zeitfehler_{HEUTE}'))
            schreiben(pfad, '\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
