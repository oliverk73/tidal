#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wie py/saetze_loeschen.py, stagt aber nur die Loeschungen (Oliver 21.10.2026).

Fuer Dateien mit Olivers ungecommitteten Aenderungen: die Arbeitskopie wird mit
saetze_loeschen.py bearbeitet (Archiv + Backup), gestaged wird HEAD mit denselben Saetzen
entfernt -- seine offenen Aenderungen bleiben ungestaged.

Usage: python3 py/saetze_loeschen_teilweise.py <liste.csv> [--schreiben]
"""
import csv
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import saetze_loeschen as SL                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ohne(text, namen):
    L = text.split('\n')
    weg = []
    for n in namen:
        t = [k for k, l in enumerate(L) if l.rstrip() == n]
        if len(t) == 1:
            weg.append(SL.block(L, t[0]))
    for a, b in sorted(weg, reverse=True):
        del L[a:b]
    return '\n'.join(L), len(weg)


def main(argv):
    liste = argv[0]
    pro = {}
    for r in csv.DictReader(open(liste, encoding='utf-8')):
        pro.setdefault(r['datei'], []).append(r['name'])
    for datei, namen in pro.items():
        head = subprocess.run(['git', 'show', 'HEAD:' + datei], capture_output=True, cwd=ROOT).stdout.decode('iso-8859-1')
        h, n = ohne(head, namen)
        print(datei, 'HEAD:', n, 'von', len(namen), 'Saetzen')
    if '--schreiben' not in argv:
        return 0
    subprocess.run([sys.executable, os.path.join(ROOT, 'py/saetze_loeschen.py'), liste, '--schreiben'], check=True, cwd=ROOT)
    for datei, namen in pro.items():
        head = subprocess.run(['git', 'show', 'HEAD:' + datei], capture_output=True, cwd=ROOT).stdout.decode('iso-8859-1')
        h, n = ohne(head, namen)
        blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], input=h.encode('iso-8859-1'), capture_output=True,
                              cwd=ROOT).stdout.decode().strip()
        subprocess.run(['git', 'update-index', '--cacheinfo', '100644,%s,%s' % (blob, datei)], check=True, cwd=ROOT)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
