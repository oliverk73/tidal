#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FES2022b-Saetze fuer archivierte Offshore-Plattformen ohne Messreihe (28.10.2026).

Aukfield Platform: TICON-4 aus GESLA-4 RWS 1984-2006, dieselbe krumme -24-min-Signatur wie die gemessenen RWS-Plattformen,
am 27.10. archiviert (harmonics/help/rws_plattformen_20261027_loeschen.csv), RWS misst dort nicht mehr. Offene, tiefe
Nordsee: FES trifft die gemessenen Plattformen A12/D15/F3 auf -7..+3 min und 0-5 % Amplitude -> FES ungeeicht.
Name/Position/Z0 vom archivierten Satz (harmonics/backup/geloescht/harmonics_ticon4_worldwide.txt).
Usage: venv/bin/python py/fes_offshore_neu.py [--schreiben]  -> harmonics_fes2022.txt
"""
import datetime as dt
import os
import sys

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, stem, FES_DIR, ZIEL, ROOT    # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

# Name, Breite, Laenge, Land, Zeitzone, Z0, Begruendung
PLATTFORMEN = [
    ('Aukfield Platform, Netherlands', 56.39904, 2.06402, 'Netherlands', 'Europe/London', 0.0,
     'Ersetzt TICON-RWS-Satz (krumm -24 min, archiviert 27.10.); FES an A12/D15/F3 -7..+3 min'),
]


def main(argv):
    namen, speeds, _, _ = X.kopf_lesen(ZIEL)
    heute = dt.date.today().strftime('%Y%m%d')
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    ds = {}
    for name, la, lo, land, tz, z0, grund in PLATTFORMEN:
        blk = ['#', '# %s' % name, '# BEGIN HOT COMMENTS', '# country: %s' % land,
               '# source: FES2022b global ocean tide model (extrapolated), sampled at station location',
               '# note: MODEL-DERIVED (not observations). %s.' % grund,
               '# note: FES ungeeicht, offene Nordsee (py/fes_offshore_neu.py).',
               '# date_imported: %s' % heute, '# datum: MSL (Z0 vom ersetzten Satz)', '# confidence: 5',
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la,
               name, '+00:00 :%s' % tz, '%.4f meters' % z0]
        n = 0
        for c in namen:
            p = os.path.join(FES_DIR, '%s_fes2022.nc' % stem(c))
            m = None
            if os.path.exists(p):
                ds.setdefault(c, nc.Dataset(p))
                m = sample(ds[c], la, lo)
            if m and m[0] and m[0] >= 0.00005:
                blk.append('%-15s %.4f  %.2f' % (c, m[0], m[1] % 360))
                n += 1
            else:
                blk.append('x 0 0')
        print('%-40s %d Tiden' % (name, n))
        if name in L:
            print('   existiert schon')
            continue
        L += blk
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
