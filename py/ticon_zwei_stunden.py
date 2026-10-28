#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TICON-Saetze aus GESLA-4 'RWS historisch' mit Meridian +01:00, die 2 h zu frueh liegen (28.10.2026).

Vuren (Waal) gegen Messfit Dalem (0,0 km) -114 min und gegen CMEMS Vuren 2023-2025 -118 min, Willemstad gegen den Messfit am Ort
-120 min (beide als Dubletten archiviert). Gorinchem (Boven Merwede, 1800-1983) liegt gleich wie Vuren (+3 min) und gegen Dalem
(2,9 km) -117 min, hat aber keinen eigenen Ersatz -> glatt +2 h: Meridian +01:00 -> +00:00 und jede Rohphase + speed x 1 h
(Greenwich vorher Roh - speed x 1 h, nachher Roh + speed x 1 h). Die rws_hist-Saetze mit +00:00 stimmen (Eemshaven, Holwerd ...).
Usage: venv/bin/python3 py/ticon_zwei_stunden.py [--schreiben]
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
NAMEN = ['Gorinchem (Boven Merwede), Netherlands']


def main(argv):
    heute = dt.date.today().strftime('%Y%m%d')
    namen, speeds, _, _ = X.kopf_lesen(DATEI)
    L = open(DATEI, encoding='iso-8859-1').read().split('\n')
    for n in NAMEN:
        i = L.index(n)
        assert L[i + 1].startswith('+01:00 '), L[i + 1]
        L[i + 1] = '+00:00 ' + L[i + 1].split(' ', 1)[1]
        for k, c in enumerate(namen):
            p = L[i + 3 + k].split()
            assert p[0] in (c, 'x'), (p, c)
            if p[0] == c:
                L[i + 3 + k] = '%-15s %s  %.2f' % (c, p[1], (float(p[2]) + speeds[c]) % 360)
        L[i:i] = ['# note: %s Zeit berichtigt: +2.00 h (Meridian +01:00 -> +00:00, Rohphasen + 1 h); wie Vuren -114..-118 min' % heute,
                  '# note: -- gegen Messfit Dalem und CMEMS Vuren, siehe py/ticon_zwei_stunden.py.']
        print(n)
    if '--schreiben' in argv:
        shutil.copy2(DATEI, os.path.join(ROOT, 'harmonics/backup', os.path.basename(DATEI) + '.vor_zwei_stunden_%s' % heute))
        schreiben(DATEI, '\n'.join(L))


if __name__ == '__main__':
    main(sys.argv[1:])
