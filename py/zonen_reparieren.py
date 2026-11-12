#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zonenfehler aus py/zonen_ganzstunden.py beheben: Phasen aller Konstituenten um h Stunden drehen (g -> g + speed*h).

12.11.2026, Bristol Bay (NOAA CO-OPS, harmonics-dwf-20251228-free.txt): fuenf benachbarte Saetze passen nur untereinander;
um -9 h (Alaska-Zonenzeit) gedreht passen sie zu FES (62-70 % -> 2-3 %) und zu den unabhaengigen NOAA-Nachbarn
Kulukak Point 62 -> 11 %, Cape Constantine 59 -> 15 %, Cape Peirce 71 -> 17 %. Phasen standen in Ortszeit unter +00:00.
Usage: venv/bin/python py/zonen_reparieren.py [--schreiben]
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAELLE = {
    'harmonics/classic/harmonics-dwf-20251228-free.txt': (-9.0, [
        'Estus Point (Hagemeister Strait), Alaska', 'Hagemeister Island (north end), Alaska',
        'High Island (Bristol Bay), Alaska', 'Pyrite Point (Bristol Bay), Alaska',
        'Summit Island (NE side, Togiak Bay), Alaska']),
}
GRUND = 'Phasen in Ortszeit unter +00:00 (Alaska -9 h), auf Greenwich gedreht; FES und NOAA-Nachbarn bestaetigen'


def main(argv):
    heute = dt.date.today().strftime('%Y%m%d')
    for rel, (h, namen) in FAELLE.items():
        pfad = os.path.join(ROOT, rel)
        kopf = X.kopf_lesen(pfad)
        konst, speeds = kopf[0], kopf[1]
        L = open(pfad, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        for name in namen:
            i = L.index(name)
            assert L[i + 1].startswith('+00:00 '), (name, L[i + 1])
            n = 0
            for k in range(i + 3, i + 3 + len(konst)):
                t = L[k].split()
                if t[0] == 'x':
                    continue
                g = (float(t[2]) + speeds[t[0]] * h) % 360
                L[k] = '%-15s %s  %.2f' % (t[0], t[1], g)
                n += 1
            j = i - next(m for m in range(1, 40) if L[i - m].startswith('# !units'))
            L.insert(j, '# note: %s %s (py/zonen_reparieren.py).' % (heute, GRUND))
            print('%-50s %d Konstituenten um %+.0f h gedreht' % (name, n, h))
        if '--schreiben' in argv:
            schreiben(pfad, '\n'.join(L) + '\n')
            print('geschrieben:', rel)


if __name__ == '__main__':
    main(sys.argv[1:])
