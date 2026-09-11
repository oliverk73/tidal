#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zieht Olivers Umbenennungen in die Hilfstabellen nach.

Die Qualitaetstabellen und Pruefllisten sind am Satznamen geschluesselt.
Benennt Oliver einen Satz um (11.09.2026: 25 Saetze an der englischen
Kueste, "Cowes, Isle of Wight" -> "Cowes (Isle of Wight), England"), findet
niemand mehr die Messungen: py/blinde_paare.py liess Cowes stumm fallen.

Der alte Name steht in harmonics/help/messung_fingerabdruck.csv (jetzt oder
im letzten Commit) zusammen
mit dem Fingerabdruck des Satzes (md5 der Partialtiden-Zeilen, vom Namen
unabhaengig). Gibt es den alten Namen in der Datei nicht mehr, aber genau
einen Satz derselben Datei mit demselben Fingerabdruck, ist das eine
Umbenennung. Geaendert wird nur dann; alles andere bleibt, wie es ist.

Usage: python3 py/umbenennungen_nachziehen.py [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import glob
import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
SEITE = os.path.join(HELP, 'messung_fingerabdruck.csv')

# Tabelle -> [(Spalte Datei, Spalte Name)]
PAARE = [('datei', 'satz'), ('weg_datei', 'weg'), ('bleibt_datei', 'bleibt'),
         ('datei', 'name'), ('datei_a', 'name_a'), ('datei_b', 'name_b')]


def _seitenzeilen():
    """Beiblatt jetzt und im letzten Commit.

    Wird das Beiblatt nach einer Umbenennung neu geschrieben, verliert es
    den alten Namen samt Fingerabdruck -- der Commit hat ihn noch.
    """
    zeilen = list(csv.DictReader(open(SEITE, encoding='utf-8')))
    try:
        alt = subprocess.run(['git', '-C', ROOT, 'show', 'HEAD:' + os.path.relpath(SEITE, ROOT)],
                             capture_output=True, text=True, check=True).stdout
        zeilen += list(csv.DictReader(io.StringIO(alt)))
    except (subprocess.CalledProcessError, OSError):
        pass
    return [z for z in zeilen if z.get('fp')]


def umbenennungen(recs):
    da = {(os.path.basename(r['file']), r['name']) for r in recs}
    nach_fp = collections.defaultdict(set)
    for r in recs:
        nach_fp[(os.path.basename(r['file']), r['fp'])].add(r['name'])
    out = {}
    for z in _seitenzeilen():
        alt = (z['datei'], z['satz'])
        if alt in da:
            continue
        neu = nach_fp.get((z['datei'], z['fp']), set())
        if len(neu) == 1:
            out[alt] = next(iter(neu))
    return out


def nachziehen(pfad, karte, schreiben):
    roh = open(pfad, encoding='utf-8', newline='').read()
    ende = '\r\n' if '\r\n' in roh[:2000] else '\n'
    zeilen = list(csv.reader(io.StringIO(roh, newline='')))
    if not zeilen:
        return 0
    kopf = zeilen[0]
    spalten = [(kopf.index(d), kopf.index(n)) for d, n in PAARE if d in kopf and n in kopf]
    if not spalten:
        return 0
    n = 0
    for z in zeilen[1:]:
        for i, j in spalten:
            if len(z) > j:
                datei = os.path.basename(z[i])
                if (datei, z[j]) in karte:
                    z[j] = karte[(datei, z[j])]
                    n += 1
    if n and schreiben:
        puffer = io.StringIO(newline='')
        csv.writer(puffer, lineterminator=ende).writerows(zeilen)
        open(pfad, 'w', encoding='utf-8', newline='').write(puffer.getvalue())
    return n


def main(argv):
    schreiben = '--schreiben' in argv
    karte = umbenennungen(load_records())
    for (datei, alt), neu in sorted(karte.items()):
        print(f'  {datei[:30]:30} {alt[:45]:45} -> {neu}')
    print(f'{len(karte)} Umbenennungen')
    for pfad in sorted(glob.glob(os.path.join(HELP, '*.csv'))):
        n = nachziehen(pfad, karte, schreiben)
        if n:
            print(f'  {n:5d} Eintraege in {os.path.basename(pfad)}')
    if not schreiben:
        print('(Probelauf -- mit --schreiben aendern)')


if __name__ == '__main__':
    main(sys.argv[1:])
