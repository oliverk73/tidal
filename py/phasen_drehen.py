#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dreht die Phasen einzelner Saetze um eine angegebene Zeit.

py/transfer_zonen_richten.py kann das auch, aber nur fuer die
NOAA-Baender und nur mit der Buchzone als Begruendung. Fuer alles
andere fehlte das Werkzeug: die vier belgischen TICON-Saetze etwa
liegen eine Stunde zu frueh, und das steht in keinem Buch, sondern in
der Messung gegen die belgischen Pegelreihen.

Die Liste ist eine CSV mit den Spalten datei, name, stunden und
begruendung -- so bleibt der Nachweis im Baum, statt im Code zu stehen.
Positive Stunden schieben den Satz nach SPAETER, negative nach frueher.
Die Geschwindigkeiten kommen aus dem congen-Kopf der Datei selbst.

Ohne --schreiben wird nur gezeigt, was passieren wuerde. Jede Datei
wird vorher nach harmonics/backup/ gesichert.

Usage: python3 py/phasen_drehen.py <liste.csv> [--schreiben]
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                       # noqa: E402
from transfer_zonen_richten import speeds                         # noqa: E402

BACKUP = os.path.join(ROOT, 'harmonics/backup')


def main(argv):
    if not argv or argv[0].startswith('--'):
        sys.exit(__doc__.strip().split('\n')[-1])
    liste = list(csv.DictReader(open(argv[0], encoding='utf-8')))
    recs = load_records()
    nach = {}
    for r in recs:
        nach.setdefault((os.path.basename(r['file']), r['name']), r)

    auftrag = {}
    for row in liste:
        r = nach.get((os.path.basename(row['datei']), row['name']))
        if r is None:
            print(f'  ?? nicht gefunden: {row["name"]} in {row["datei"]}')
            continue
        auftrag.setdefault(r['file'], []).append((r, float(row['stunden']),
                                                  row['begruendung']))

    heute = dt.date.today().strftime('%Y%m%d')
    for datei, gs in sorted(auftrag.items()):
        pfad = os.path.join(ROOT, datei)
        sp = speeds(pfad)
        if not sp:
            sys.exit(f'keine Konstituentengeschwindigkeiten in {datei}')
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        print(f'\n{os.path.basename(datei)}  ({len(gs)} Saetze)')
        # Von hinten nach vorne, damit die Zeilennummern gueltig bleiben.
        for r, stunden, grund in sorted(gs, key=lambda x: -x[0]['line']):
            print(f'  {stunden:+.2f} h  {r["name"][:44]:44s} {grund[:60]}')
            if '--schreiben' not in argv:
                continue
            k = r['line'] - 1
            j, n = k + 3, 0
            while j < len(lines) and n < 175:
                p = lines[j].split()
                if not p or p[0].startswith('#'):
                    break
                if p[0] != 'x' and p[0] in sp:
                    amp, g = float(p[1]), float(p[2])
                    lines[j] = (f'{p[0]:<16}{amp:.4f}  '
                                f'{(g + sp[p[0]] * stunden) % 360:.2f}')
                n += 1
                j += 1
            umbruch = [grund[i:i + 62] for i in range(0, len(grund), 62)]
            lines[k:k] = ([f'# note: {heute} Phasen um {stunden:+.2f} h gedreht.']
                          + [f'# note: {z}' for z in umbruch]
                          + ['# note: Siehe py/phasen_drehen.py.'])
        if '--schreiben' in argv:
            os.makedirs(BACKUP, exist_ok=True)
            shutil.copy2(pfad, os.path.join(
                BACKUP, f'{os.path.basename(datei)[:-4]}_{heute}_drehen.txt'))
            open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(lines))
            print(f'  geschrieben: {len(gs)} Saetze gedreht')
    if '--schreiben' not in argv:
        print('\n(Trockenlauf -- mit --schreiben wird geschrieben)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
