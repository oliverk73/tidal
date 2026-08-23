#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loescht die in harmonics/help/bom_loeschen.csv aufgefuehrten Saetze.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.
Jede Datei wird vorher nach harmonics/backup/ gesichert.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP = os.path.join(ROOT, 'harmonics/backup')

LISTE = os.path.join(ROOT, 'harmonics/help/bom_loeschen.csv')


def liste():
    """Zu loeschende Saetze aus der CSV -- der Nachweis bleibt so im Baum."""
    import csv
    with open(LISTE, encoding='utf-8') as fh:
        return [(r['datei'], r['name'],
                 f"{r['fehler_prozent']} % Hub -- {r['begruendung']}")
                for r in csv.DictReader(fh)]


def block(lines, i):
    """Grenzen des Satzes, dessen Namenszeile bei i steht."""
    a = i
    while a > 0 and (lines[a - 1].startswith('#') or not lines[a - 1].strip()):
        a -= 1
    b = i + 3                                   # Name, Meridian, Z0
    while b < len(lines) and lines[b].strip() and not lines[b].startswith('#'):
        b += 1
    return a, b


def main(argv):
    schreiben = '--schreiben' in argv
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    proDatei = {}
    for datei, name, warum in liste():
        proDatei.setdefault(datei, []).append((name, warum))

    gesamt = 0
    for datei, faelle in sorted(proDatei.items()):
        pfad = os.path.join(ROOT, datei)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and lines[k + 1][:1] in '+-' and lines[k + 1][3:4] == ':')
        raus = []
        for name, warum in faelle:
            treffer = [k for k, l in enumerate(lines) if l.rstrip() == name]
            if len(treffer) != 1:
                print(f'  ABBRUCH {datei}: "{name}" {len(treffer)}x gefunden')
                return 1
            a, b = block(lines, treffer[0])
            raus.append((a, b, name, warum))
        raus.sort(reverse=True)
        print(f'\n{datei}  ({vorher} Saetze)')
        for a, b, name, warum in sorted(raus):
            print(f'   -{b - a:3} Zeilen  {name[:46]:46}\n                     {warum}')
        if schreiben:
            shutil.copy2(pfad, os.path.join(
                BACKUP, os.path.basename(datei) + f'.vor_bom_dedup_{stamp}'))
            for a, b, _n, _w in raus:
                del lines[a:b]
            open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(lines))
            nach = sum(1 for k, l in enumerate(lines)
                       if l and not l.startswith('#') and k + 1 < len(lines)
                       and lines[k + 1][:1] in '+-' and lines[k + 1][3:4] == ':')
            print(f'   geschrieben: {vorher} -> {nach} Saetze '
                  f'(erwartet {vorher - len(raus)})')
            if nach != vorher - len(raus):
                print('   ACHTUNG: Satzzahl passt nicht!')
                return 1
        gesamt += len(raus)
    print(f'\n{gesamt} Saetze {"geloescht" if schreiben else "waeren zu loeschen"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
