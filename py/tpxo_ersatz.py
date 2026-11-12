#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FES-Saetze, an denen TPXO10 nachweislich besser ist, auf TPXO10-atlas-v2 umstellen (Oliver 12.11.2026: "Ja").

Grundlage py/tpxo_vergleich.py: Abstand FES<->TPXO10 >= 10 % markiert unsichere FES-Saetze (30 von 416). Einzelpruefung
gegen gemessene Nachbarn (scratchpad fes30.py/barth.py): nur wo TPXO10 an ALLEN nahen Messsaetzen deutlich besser ist
als FES, wird umgestellt -- Finnischer Meerbusen (Kronstadt FES 23 %/T10 7 %, St. Petersburg 30/4, Narva 12/5,
Sillamaee 13/3, Hamina 11/4) und Barth (Bodden-Pegel FES 31-40 %, T10 16-22 %).
Umstellung: Konstituenten, die TPXO10 hat (15), aus der naechsten TPXO10-Wasserzelle; uebrige bleiben. Z0 = -Minimum
der 19-Jahres-Kurve (Bezug wie bisher approx. LAT). Phasen Greenwich (alle Saetze +00:00).

Zusaetzlich ZONEN: vier FES-Saetze vom 30.10.2026 (NOAA-Zeugenabgleich) tragen Greenwich-Phasen unter einer
Ortszeit-Zeile (-05:00/+03:00/+01:00) -> Zeitzeile auf +00:00.
Usage: venv/bin/python py/tpxo_ersatz.py [--schreiben]
"""
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheitelfit as SF                                           # noqa: E402
import tpxo as T                                                   # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt')
ERSATZ = {
    'Sestroretsk, St. Petersburg, Russia': 'Kronstadt FES 23 %/T10 7 %, St. Petersburg 30/4',
    'Zelenogorsk, St. Petersburg, Russia': 'Kronstadt FES 23 %/T10 7 %, St. Petersburg 30/4',
    'Sosnovyy Bor, Leningrad Oblast, Russia': 'Kronstadt FES 23 %/T10 7 %, Narva-Joesuu 12/5',
    'Primorsk, Leningrad Oblast, Russia': 'Kronstadt FES 23 %/T10 7 %, Hamina 11/4',
    'Sovetsky, Leningrad Oblast, Russia': 'Hamina FES 11 %/T10 4 %, Kronstadt 23/7',
    'Vyborg, Leningrad Oblast, Russia': 'Hamina FES 11 %/T10 4 %, Kronstadt 23/7',
    'Barth, Mecklenburg-Vorpommern, Germany': 'Bodden-Pegel Althagen FES 31 %/T10 17 %, Barhoeft 33/16, Stralsund 38/22',
}
ZONEN = {
    'Agger, Denmark': '+01:00',
    'Byam Martin Island, Nunavut, Canada': '-05:00',
    'Ostrova Gorbovy (Novaya Zemlya), Arkhangelsk Oblast, Russia': '+03:00',
    'Bridport Inlet (Melville Island), Nunavut, Canada': '-05:00',
}


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen = kopf[0]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    tk = T.konstituenten('10')
    tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 1800.0)
    for name, alt in ZONEN.items():
        i = L.index(name)
        assert L[i + 1].startswith(alt + ' '), (name, L[i + 1])
        print('%-60s %s -> %s' % (name, L[i + 1], L[i + 1].replace(alt, '+00:00', 1)))
        L[i + 1] = L[i + 1].replace(alt, '+00:00', 1)
        L.insert(i - next(k for k in range(1, 40) if L[i - k].startswith('# !units')),
                 '# note: %s Zeitzeile %s -> +00:00 (Phasen sind Greenwich; Fehler seit 30.10., py/tpxo_ersatz.py).' % (heute, alt))
    for name, beleg in ERSATZ.items():
        i = L.index(name)
        assert L[i + 1].startswith('+00:00 '), (name, L[i + 1])
        lat = float(next(z for z in L[i - 30:i][::-1] if z.startswith('# !latitude:')).split(':')[1])
        lon = float(next(z for z in L[i - 30:i][::-1] if z.startswith('# !longitude:')).split(':')[1])
        w_t, dk = T.konstanten('10', lat, lon)
        w = {}
        for n, z in zip(namen, L[i + 3:i + 3 + len(namen)]):
            t = z.split()
            if t[0] != 'x':
                assert t[0] == n, (name, n, z)
                w[n] = (float(t[1]), float(t[2]))
        alt_m2 = w.get('M2')
        for k in tk:
            if k in namen and k in w_t:
                w[k] = w_t[k]
        z0 = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
        print('%-45s TPXO10-Zelle %.1f km  M2 %.3f@%.0f -> %.3f@%.0f  Z0 %s -> %.4f' % (
            name, dk, *alt_m2, *w['M2'], L[i + 2].split()[0], z0))
        L[i + 2] = '%.4f meters' % z0
        L[i + 3:i + 3 + len(namen)] = ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        j = i - next(k for k in range(1, 40) if L[i - k].startswith('# !units'))
        L[j:j] = ['# note: %s Hauptkonstituenten aus TPXO10-atlas-v2 (Zelle %.1f km) statt FES (py/tpxo_ersatz.py).' % (heute, dk),
                  '# note: Grund: an Messsaetzen TPXO10 besser: %s.' % beleg]
        for k in range(j, j - 40, -1):
            if L[k].startswith('# source:'):
                L[k] = '# source: TPXO10-atlas-v2 (OSU) + FES2022b, sampled at station location'
                break
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('geschrieben')


if __name__ == '__main__':
    main(sys.argv[1:])
