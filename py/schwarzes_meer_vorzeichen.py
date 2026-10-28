#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bulgarische TICON/CMEMS-Saetze gegen unabhaengige Pegel (28.10.2026).

Die CMEMS-Reihen Varna und Burgas haben ein umgekehrtes Vorzeichen: gegen IOC Mangalia (RO) 2016-2017 Korrelation -0,73 bzw.
-0,52 ohne Zeitversatz; alle vier Hauptgezeiten liegen 172-185 Grad neben IOC Igneada (TR) und FES2022 (FES trifft dort beide
IOC-Pegel auf wenige Grad). -> jede Phase + 180 Grad.
Balchik hat das richtige Vorzeichen, aber Ortszeit: M2 104 Grad gegen Mangalia 46 / FES 30 -> jede Phase - speed x 2 h
(die TICON-Angabe +02:00 war hier richtig; die Meridian-Korrektur vom 28.10. nimmt das zurueck).
Burgas (Oil Port) ist umgedreht und 2,5-3 h spaet, K1 halb so gross -> archiviert (harmonics/help/schwarzes_meer_20261028_loeschen.csv).
Usage: venv/bin/python3 py/schwarzes_meer_vorzeichen.py [--schreiben]
"""
import datetime as dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/ticon/harmonics_ticon4_worldwide.txt')
# Name -> (Stunden, Grad, Notiz)
SAETZE = {
    'Varna, Bulgaria': (0, 180, 'Vorzeichen berichtigt: alle Phasen +180 Grad; CMEMS-Reihe umgedreht (gegen IOC Mangalia r=-0,73)'),
    'Burgas, Bulgaria': (0, 180, 'Vorzeichen berichtigt: alle Phasen +180 Grad; CMEMS-Reihe umgedreht (gegen IOC Mangalia r=-0,52)'),
    'Balchik, Bulgaria': (-2, 0, 'Zeit berichtigt: -2.00 h (Reihe in Ortszeit); trifft IOC Mangalia und FES2022'),
}


def main(argv):
    heute = dt.date.today().strftime('%Y%m%d')
    namen, speeds, _, _ = X.kopf_lesen(DATEI)
    L = open(DATEI, encoding='iso-8859-1').read().split('\n')
    for n, (std, grad, notiz) in SAETZE.items():
        i = L.index(n)
        assert L[i + 1].startswith('+00:00 '), L[i + 1]
        for k, c in enumerate(namen):
            p = L[i + 3 + k].split()
            assert p[0] in (c, 'x'), (p, c)
            if p[0] == c:
                L[i + 3 + k] = '%-15s %s  %.2f' % (c, p[1], (float(p[2]) + speeds[c] * std + grad) % 360)
        L[i:i] = ['# note: %s %s' % (heute, notiz), '# note: -- siehe py/schwarzes_meer_vorzeichen.py.']
        print(n)
    if '--schreiben' in argv:
        shutil.copy2(DATEI, os.path.join(ROOT, 'harmonics/backup', os.path.basename(DATEI) + '.vor_schwarzes_meer_%s' % heute))
        schreiben(DATEI, '\n'.join(L))


if __name__ == '__main__':
    main(sys.argv[1:])
