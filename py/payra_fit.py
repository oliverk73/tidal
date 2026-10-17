#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Saetze fuer den Rabnabad-Kanal (Payra, Bangladesch) aus den PPA-Tidenkalendern.

Oliver 17.10.2026. Eingabe: tide_tables/bangladesh/payra/payra_hwlw.json (py/payra_tafeln.py),
Hoch-/Niedrigwasser der Payra Port Authority 2021-2025 in UTC. Fit mit der Scheitelgleichung aus
py/scheitelfit.py (Hoehe am Scheitel und waagerechte Tangente; Korea 13.10.2026: 12.7 -> 1.1 cm).
Probe: Fit nur 2025, geprueft an den Tafeln der Vorjahre (unabhaengige Vorhersage); Endfit alle Jahre.
Positionen aus der Tafel ("Positions of PPA tide gauges"), Zeitzone Asia/Dhaka, Phasen Greenwich.

Befund 17.10.2026: Die vier Pegel stehen seit 13.06. im Bestand (UTide aus denselben Tafeln); der Scheitelfit
ist an der Tafel 2025 nur 1-1.3 cm besser, die Jahrestafeln weichen untereinander 15-20 cm ab -> nicht ersetzt.
Nur Andharmanik (aeltere Vierteljahrestafeln) wurde neu gefittet. Namen = Bestandsnamen, --schreiben legt
also nichts doppelt an.

Usage: venv/bin/python py/payra_fit.py [--schreiben]  -> harmonics/utide/harmonics_utide_tidetables.txt
"""
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'tide_tables/bangladesh/payra/payra_hwlw.json')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')


def dms(g, m, s):
    return g + m / 60 + s / 3600


PEGEL = {  # Tafel-Name -> (Satzname, Breite, Laenge)
    'Charipara': ('Charipara (Rabnabad Channel), Bangladesh', dms(21, 57, 5), dms(90, 18, 2)),
    'Kauar Char': ('Kauar Char (Rabnabad Channel), Bangladesh', dms(21, 49, 58), dms(90, 15, 18)),
    'Monopile-1': ('Monopile-1 (Rabnabad Channel), Bangladesh', dms(21, 37, 17), dms(90, 12, 29)),
    'Monopile-2': ('Monopile-2 (Rabnabad Channel), Bangladesh', dms(21, 27, 28), dms(90, 7, 35)),
}


def main(argv):
    D = json.load(open(QUELLE))
    namen, speeds, arg, fak = X.kopf_lesen(ZIEL)
    kopf = (namen, speeds, arg, fak)
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    for tafelname, (name, lat, lon) in PEGEL.items():
        ev = D[tafelname]
        t = np.array([dt.datetime.fromisoformat(x[:-1]).replace(tzinfo=dt.timezone.utc).timestamp() for x, _ in ev])
        h = np.array([v for _, v in ev])
        jahr = np.array([int(x[:4]) for x, _ in ev])
        nutz = SF.konstituenten(namen, SF.CONSTIT_67)
        probe = ''
        if (jahr < 2025).sum() > 500:
            z0p, wp = SF.fit(t[jahr == 2025], h[jahr == 2025], nutz, speeds, arg, fak)
            rp, dtp, _ = SF.guete(t[jahr < 2025], h[jahr < 2025], z0p, wp, kopf)
            r25, _, _ = SF.guete(t[jahr == 2025], h[jahr == 2025], z0p, wp, kopf)
            probe = 'Probe: Fit 2025 an den Tafeln 2021-2024 %.1f cm, %.0f min (an 2025 selbst %.1f cm)' % (100 * rp, dtp, 100 * r25)
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r, dtm, _ = SF.guete(t, h, z0, w, kopf)
        print('%-44s %4d Scheitel %s..%s  Endfit %.1f cm, %.0f min  M2 %.3f@%.0f K1 %.3f@%.0f  %s' % (
            name, len(t), ev[0][0][:7], ev[-1][0][:7], 100 * r, dtm, *w['M2'], *w['K1'], probe))
        blk = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: Bangladesh',
               '# source: Payra Port Authority tide tables (Rabnabad Channel), Scheitelfit',
               '# date_imported: %s' % heute,
               '# datum: Chart Datum (Pegelnull ~ LAT laut Tafel)', '# confidence: 7',
               '# utide: scheitel=%d period=%s..%s rms=%.4fm const=%d' % (len(t), ev[0][0][:10], ev[-1][0][:10], r, len(nutz)),
               '# note: %s HW/NW-Tafeln der PPA (UTC+6) per Scheitelgleichung (py/payra_fit.py); %s (Oliver).' % (heute, probe or 'nur 2025'),
               '# !units: meters', '# !longitude: %.4f' % lon, '# !latitude: %.4f' % lat,
               '# region: Barishal Division', name, '+00:00 :Asia/Dhaka', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        if name in L:
            print('   existiert schon')
            continue
        L += blk
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
