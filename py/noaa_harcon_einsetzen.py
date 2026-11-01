#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schreibt die aktuellen CO-OPS-Konstanten (harcon) in DWF-2025-Saetze.

Die Saetze behalten Kopf, Position und Name. Phasen sind Greenwich (phase_GMT),
die DWF-Datei steht auf Meridian +00:00. Gefunden mit py/noaa_harcon_abgleich.py.

Usage: python3 py/noaa_harcon_einsetzen.py <station_id>[=<Z0 in Fuss>] ... [--schreiben]
"""
import json
import re
import sys
import urllib.request

import sicher_schreiben

DATEI = 'harmonics/classic/harmonics-dwf-20251228-free.txt'
URL = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/%s/harcon.json?units=english'
UMNAME = {'LAM2': 'LDA2', 'RHO': 'RHO1'}


def main(argv):
    schreiben = '--schreiben' in argv
    z = open(DATEI, encoding='iso-8859-1').read().split('\n')
    n = int(z[next(i for i, l in enumerate(z) if re.fullmatch(r'\d+', l))])
    a = next(i for i, l in enumerate(z) if re.fullmatch(r'\d+', l)) + 1
    slots = [l.split()[0] for l in z[a:a + n + 50] if not l.startswith('#')][:n]
    for arg in [x for x in argv if not x.startswith('--')]:
        sid, _, z0 = arg.partition('=')
        kopf = z.index('# noaa_station_id: ' + sid)
        i = kopf
        while not re.match(r'[+-]\d\d:\d\d ', z[i + 1]):
            i += 1
        assert z[i + 1].startswith('+00:00')
        d = json.load(urllib.request.urlopen(URL % sid, timeout=30))
        kk = d['HarmonicConstituents']
        neu = {UMNAME.get(c['name'], c['name']): c for c in kk if c['amplitude'] > 0}
        fremd = set(neu) - set(slots)
        assert not fremd, fremd
        anfang = i + 3
        for k, s in enumerate(slots):
            alt = z[anfang + k]
            assert alt == 'x 0 0' or alt.split()[0] == s, (alt, s)
            if s in neu:
                z[anfang + k] = '%-15s %.4f %7.2f' % (s, neu[s]['amplitude'], neu[s]['phase_GMT'])
            else:
                z[anfang + k] = 'x 0 0'
        if z0:
            z[i + 2] = '%.4f feet' % float(z0)
        u = next(j for j in range(kopf, i) if z[j].startswith('# !units:'))
        z.insert(u, '# note: 20261101 Konstanten neu aus CO-OPS harcon: ' + kk[0]['comments'][:110])
        print(z[i + 2 - 0], sid, z[i + 1], '-', len(neu), 'Tiden')
    if schreiben:
        sicher_schreiben.schreiben(DATEI, '\n'.join(z))
        print('geschrieben')


main(sys.argv[1:])
