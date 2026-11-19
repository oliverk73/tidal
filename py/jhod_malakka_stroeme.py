#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemessene Stromkonstanten Malakkastrasse, Table 3 aus Sujino et al. (1982), Report of Hydrographic
Researches No. 17, "Tide and tidal stream in the Straits of Malacca and Singapore" (JHOD, frei:
www1.kaiho.mlit.go.jp/kenkyu/report/rhr17/rhr17-11.pdf). Japan/Indonesien/Malaysia/Singapur 1977-79,
je Station 2 x 35 Tage. Abgelesen 19.11.2026.

kappa = Ortsphase (local epoch). Probe: die ATT-NP203-Saetze an St. 4-6 (Takong Kecil, Batu Berhanti,
Pengerang) sind dieselben Messungen; aus kappa - p*lambda (UTC) + sigma*8 h ergeben sich die ATT-Phasen
(+08:00) auf 0,1-1 Grad (M2 283,7 -> 308, K1 56,3 -> 73). Also Greenwich G = kappa - p*lambda.
Nur St. 1-3 sind neu (St. 4-6 stehen schon als ATT-Saetze im Bestand).

Usage: venv/bin/python py/jhod_malakka_stroeme.py [--schreiben]
"""
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_germany_harmonics_175 import CONSTITUENTS_175     # noqa: E402
from sicher_schreiben import schreiben                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')
TIDEN = 'SA SSA MM MSF MF Q1 O1 M1 K1 J1 OO1 P1 MU2 N2 NU2 M2 L2 S2 K2 2SM2 MO3 M3 MK3 MN4 M4 SN4 MS4 2MN6 M6 MSN6 2MS6 2SM6'.split()
P_ART = {'SA': 0, 'SSA': 0, 'MM': 0, 'MSF': 0, 'MF': 0}          # sonst erste Ziffer des Namens / Spezies
STATIONEN = [
    dict(nr=1, quelle='Off One Fathom Bank', lat=2 + 40 / 60 + 15 / 3600, lon=101 + 10 / 60 + 4 / 3600, achse=300, mittel=0.087,
         name='One Fathom Bank (31 km SE, Malacca Strait), Malaysia Current',
         w='0.079 297.8 0.016 298.1 0.010 234.6 0.011 212.3 0.032 221.3 0.024 153.1 0.220 187.5 0.016 65.2 0.314 214.4 '
           '0.017 180.7 0.042 257.1 0.104 213.2 0.015 221.4 0.219 319.3 0.043 319.1 1.118 325.1 0.042 330.6 0.521 0.9 '
           '0.142 1.6 0.030 209.4 0.027 297.6 0.009 78.2 0.011 322.0 0.025 342.9 0.059 343.3 0.004 157.1 0.051 34.6 '
           '0.008 333.3 0.010 206.7 0.008 20.6 0.014 278.6 0.001 143.9'),
    dict(nr=2, quelle='Off Raleigh Shoal', lat=2 + 6 / 60 + 51 / 3600, lon=101 + 56 / 60 + 41 / 3600, achse=305, mittel=0.094,
         name='Raleigh Shoal (7 km E, Malacca Strait), Malaysia Current',
         w='0.061 287.7 0.012 301.1 0.009 224.1 0.015 215.5 0.027 221.7 0.022 147.1 0.178 168.9 0.003 108.8 0.287 219.8 '
           '0.004 53.0 0.061 251.4 0.095 218.6 0.017 211.8 0.226 11.3 0.044 11.0 1.206 12.0 0.058 358.4 0.551 49.2 '
           '0.150 49.9 0.055 298.8 0.040 356.1 0.011 215.8 0.044 23.3 0.017 156.8 0.052 162.0 0.022 214.9 0.061 196.9 '
           '0.011 266.7 0.012 273.7 0.009 272.0 0.017 293.7 0.014 337.1'),
    dict(nr=3, quelle='Off Tg. Segenting', lat=1 + 37 / 60 + 57 / 3600, lon=102 + 43 / 60 + 30 / 3600, achse=292, mittel=0.036,
         name='Tanjung Segenting (25 km SW, Malacca Strait), Johor, Malaysia Current',
         w='0.088 297.1 0.017 296.6 0.008 254.4 0.003 93.1 0.023 220.3 0.024 74.8 0.162 123.0 0.019 135.6 0.258 222.4 '
           '0.023 24.5 0.019 276.7 0.085 221.2 0.012 206.5 0.197 36.8 0.038 36.5 1.019 49.6 0.050 65.6 0.486 94.8 '
           '0.133 95.5 0.042 303.3 0.047 77.0 0.019 264.5 0.038 121.5 0.015 221.0 0.047 241.4 0.005 38.3 0.051 276.9 '
           '0.007 12.0 0.007 114.0 0.014 76.6 0.029 88.6 0.007 158.3'),
]


def spezies(k):
    if k in P_ART:
        return P_ART[k]
    return int(next(c for c in reversed(k) if c.isdigit()))


def block(s):
    z = s['w'].split()
    assert len(z) == 2 * len(TIDEN), (s['nr'], len(z))
    konst = {k: (float(z[2 * i]), (float(z[2 * i + 1]) - spezies(k) * s['lon']) % 360) for i, k in enumerate(TIDEN)}
    heute = dt.date.today().strftime('%Y%m%d')
    B = ['#', '# %s' % s['name'],
         '# Measured tidal stream harmonic constants, station %d "%s", Table 3 of Sujino et al. (1982),' % (s['nr'], s['quelle']),
         '# Report of Hydrographic Researches No. 17 (JHOD), joint survey Japan/Indonesia/Malaysia/Singapore 1977-79 (2 x 35 days).',
         '# Main direction %d deg true; local epoch kappa converted to Greenwich (G = kappa - p*lon), checked against ATT NP203' % s['achse'],
         '# BEGIN HOT COMMENTS', '# country: Malaysia', '# source: JHOD current meter 1978-79, harmonic constants table (paper)',
         '# datum: n/a', '# station_type: current', '# major_axis_deg_true: %d' % s['achse'], '# confidence: 7',
         '# date_imported: %s' % heute, '# !units: knots', '# !longitude: %.4f' % s['lon'], '# !latitude: %.4f' % s['lat'],
         s['name'], '+00:00 :UTC', '%.4f knots' % s['mittel']]
    for k, _sp in CONSTITUENTS_175:
        c = konst.get(k)
        B.append('%-15s %.4f  %.2f' % (k, c[0], c[1]) if c else 'x 0 0')
    return '\n'.join(B), konst


def main(argv):
    bl = []
    for s in STATIONEN:
        b, k = block(s)
        print('%-70s M2 %.3f kn G %.1f  K1 %.3f G %.1f' % (s['name'], k['M2'][0], k['M2'][1], k['K1'][0], k['K1'][1]))
        bl.append(b)
    if '--schreiben' in argv:
        T = open(OBS, encoding='iso-8859-1').read()
        for s in STATIONEN:
            assert '\n%s\n' % s['name'] not in T, s['name']
        schreiben(OBS, T.rstrip('\n') + '\n' + '\n'.join(bl) + '\n')
        nl = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d'))
        with open(nl, 'a', newline='', encoding='utf-8') as fh:
            csv.writer(fh).writerows([('harmonics_utide_current_observations.txt', s['name']) for s in STATIONEN])
        print('->', OBS)


if __name__ == '__main__':
    main(sys.argv[1:])
