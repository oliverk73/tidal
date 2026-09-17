#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Holt einen geloeschten Satz in den Bestand zurueck.

Gesucht wird zuerst im Archiv harmonics/backup/geloescht/ (dort legt
py/saetze_loeschen.py seit 17.09.2026 jeden geloeschten Satz ab), danach
in den Dateisicherungen harmonics/backup/<datei>.vor_* -- so kommen auch
Saetze zurueck, die vor dem Archiv geloescht wurden.

Der Satz wird ans Ende seiner alten Datei angehaengt, mit einem Vermerk,
und in harmonics/help/behalten.csv eingetragen. Diese Schutzliste liest
py/bestand_aufraeumen.py: ein zurueckgeholter Satz wird nicht noch einmal
automatisch geloescht.

Ohne --schreiben wird nur gezeigt, was gefunden wurde.

Usage: python3 py/satz_zurueckholen.py "<Name des Satzes>" [--schreiben]
       python3 py/satz_zurueckholen.py --liste [Suchtext]    Archiv durchsuchen
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sicher_schreiben                                             # noqa: E402
from health_check import MERIDIAN, ROOT, active_files               # noqa: E402

BACKUP = os.path.join(ROOT, 'harmonics/backup')
ARCHIV = os.path.join(BACKUP, 'geloescht')
BEHALTEN = os.path.join(ROOT, 'harmonics/help/behalten.csv')


def archiv_eintraege():
    """-> [(datei-basename, name, kopfzeile, blockzeilen)] aus dem Archiv."""
    out = []
    for pfad in sorted(glob.glob(os.path.join(ARCHIV, '*.txt'))):
        teile = open(pfad, encoding='iso-8859-1').read().split('# ARCHIV: ')[1:]
        for t in teile:
            kopf, _, rest = t.partition('\n')
            name = kopf.split(' | ')[2] if kopf.count(' | ') >= 3 else ''
            out.append((os.path.basename(pfad), name, kopf, rest.strip('\n').split('\n')))
    return out


def aus_sicherung(name):
    """Juengste Dateisicherung, die den Satz noch enthaelt -> (basename, blockzeilen)."""
    import saetze_loeschen as SL
    aktiv = {os.path.basename(f): os.path.join(ROOT, f) for f in active_files()}
    for pfad in sorted(glob.glob(os.path.join(BACKUP, '*.txt.vor_*')), key=os.path.getmtime, reverse=True):
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        treffer = [k for k, l in enumerate(lines) if l.rstrip() == name
                   and k + 1 < len(lines) and MERIDIAN.match(lines[k + 1])]
        basis = os.path.basename(pfad).split('.vor_')[0]
        if len(treffer) == 1 and basis in aktiv and not re.search(
                r'^' + re.escape(name) + r'$', open(aktiv[basis], encoding='iso-8859-1').read(), re.M):
            a, b = SL.block(lines, treffer[0])
            return basis, [l for l in lines[a:b] if l.strip()]
    return None, None


def main(argv):
    if '--liste' in argv:
        such = ' '.join(a for a in argv if not a.startswith('--')).lower()
        for datei, name, kopf, _b in archiv_eintraege():
            if such in kopf.lower():
                print(f'{datei:40} {kopf[:150]}')
        return 0
    rest = [a for a in argv if not a.startswith('--')]
    if not rest:
        print(__doc__.strip().split('Usage:')[-1].strip())
        return 2
    name = rest[0]
    schreiben = '--schreiben' in argv

    datei, block = None, None
    for d, n, kopf, b in archiv_eintraege():
        if n == name:
            datei, block = d, b                          # juengster Eintrag gewinnt
    herkunft = 'Archiv'
    if block is None:
        datei, block = aus_sicherung(name)
        herkunft = 'Dateisicherung'
    if block is None:
        print(f'"{name}" weder im Archiv noch in einer Sicherung gefunden.')
        return 1
    ziel = [f for f in active_files() if os.path.basename(f) == datei]
    if len(ziel) != 1:
        print(f'Datei {datei} nicht eindeutig im Bestand ({len(ziel)}).')
        return 1
    pfad = os.path.join(ROOT, ziel[0])
    text = open(pfad, encoding='iso-8859-1').read()
    if re.search(r'^' + re.escape(name) + r'$', text, re.M):
        print(f'"{name}" steht bereits in {ziel[0]}.')
        return 1
    vermerk = f'# note: {dt.date.today():%Y%m%d} aus {herkunft} zurueckgeholt (py/satz_zurueckholen.py).'
    k = next((i for i, l in enumerate(block) if l.startswith('# !units:')), None)
    if k is not None:
        block = block[:k] + [vermerk] + block[k:]
    print(f'{herkunft}: {len(block)} Zeilen -> {ziel[0]}')
    print('\n'.join(block[:6]) + '\n...')
    if not schreiben:
        print('(nur Probe; mit --schreiben wird zurueckgeholt)')
        return 0
    sicher_schreiben.schreiben(pfad, text.rstrip('\n') + '\n\n' + '\n'.join(block) + '\n')
    neu = not os.path.exists(BEHALTEN)
    with open(BEHALTEN, 'a', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        if neu:
            w.writerow(['datei', 'name', 'datum', 'grund'])
        w.writerow([ziel[0], name, f'{dt.date.today():%Y%m%d}', 'zurueckgeholt'])
    print(f'zurueckgeholt; Schutz in {os.path.relpath(BEHALTEN, ROOT)}. TCD neu bauen: python3 py/tcd_bauen.py')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
