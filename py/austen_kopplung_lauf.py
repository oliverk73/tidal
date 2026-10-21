#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSIRO-AusTEN-Stroemungssaetze ohne K2/P1 analytisch koppeln (Oliver 21.10.2026).

Die AusTEN-Konstanten (harmonics_utide_australia_oceancurrent.txt) stammen aus UTide-Fits an
Reihen von 48-206 Tagen; bei UTas-ARENA, CSIRO und IMOS SAM6IS fehlen K2 und P1, ihr S2/K1
enthaelt sie also mit dem Gewicht des Messfensters. Wie bei den kurzen Pegelfits
(py/pegel_kopplung_lauf.py) werden sie mit Verhaeltnis/Phasenabstand des naechsten vollstaendigen
Pegels herausgerechnet (py/kopplung_analytisch.py) und K2/P1 eingesetzt. Das Messfenster kommt
aus observation_period der Quelldatei; die Projektion auf die M2-Achse ist linear, die Korrektur
gilt daher fuer den projizierten Satz genauso wie fuer u und v.

Usage: venv/bin/python py/austen_kopplung_lauf.py [--schreiben]
"""
import os
import re
import subprocess
import sys

import numpy as np
import xarray as xr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc                                           # noqa: E402
import kopplung_analytisch as A                                     # noqa: E402
import stroemung_kopplung as K                                      # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = 'harmonics/utide/harmonics_utide_australia_oceancurrent.txt'
NC = os.path.join(ROOT, 'currents/Australia_OceanCurrent/Aust_current_meter_tidal_cnstits_v2.nc')
NOTIZ = '# note: 20261021 S2/K1 corrected for K2/P1 inside the %d-day window (ratio/lag of %s, %.0f km); K2/P1 added'


def fenster():
    d = xr.open_dataset(NC)
    code = [s.decode().strip() for s in d.station_code.values]
    op = d.observation_period.values
    return {c: (str(op[j, 0])[:10], str(op[j, 1])[:10]) for j, c in enumerate(code)}


def bearbeite(text):
    L = text.split('\n')
    namen, sp, _a, _f = X.kopf_lesen(os.path.join(ROOT, DATEI))
    per = fenster()
    st = [k for k in range(len(L) - 1) if L[k] and not L[k].startswith('#') and hc.MERIDIAN.match(L[k + 1])]
    v, aend = 0, []
    for k in st:
        kopf = '\n'.join(L[v:k])
        v = k
        m = re.search(r'station_id_context: AUSTEN-(\S+)', kopf)
        if not m or '20261021 S2/K1 corrected' in kopf:
            continue
        a, b = per[m.group(1)]
        t0, t1 = A.unix(a), A.unix(b) + 86400
        tage = (t1 - t0) / 86400
        alt = {}
        for n, z in zip(namen, L[k + 3:k + 3 + len(namen)]):
            f = z.split()
            if f[0] != 'x':
                assert f[0] == n, (L[k], n, z)
                alt[n] = (float(f[1]), float(f[2]))
        if 'K2' in alt or 'S2' not in alt:
            continue
        assert L[k + 1].startswith('+00:00'), L[k + 1]               # Greenwich-Phasen
        la = float(re.search(r'# !latitude: (\S+)', kopf).group(1))
        lo = float(re.search(r'# !longitude: (\S+)', kopf).group(1))
        rat, pn, km = K.verhaeltnisse(la, lo, 300)
        if rat is None:
            print('kein Pegel bis 300 km:', L[k])
            continue
        neu = A.korrigiere(K.KOPF, alt, t0, t1, rat)
        print('%-45s %3.0f d  S2 %.3f -> %.3f  K2 %.3f  K1 %.3f -> %.3f  P1 %.3f  (%s %.0f km)' % (
            L[k][:45], tage, alt['S2'][0], neu['S2'][0], neu['K2'][0], alt.get('K1', (0, 0))[0],
            neu.get('K1', (0, 0))[0], neu.get('P1', (0, 0))[0], pn.split(',')[0], km))
        aend.append((k, neu, tage, pn, km))
    for k, neu, tage, pn, km in reversed(aend):
        for j, n in enumerate(namen):
            if n in ('S2', 'K2', 'K1', 'P1') and n in neu:
                L[k + 3 + j] = '%-15s %.4f  %.2f' % (n, neu[n][0], neu[n][1])
        L.insert(k, NOTIZ % (round(tage), pn.split(',')[0][:40], km))
    return '\n'.join(L), len(aend)


def main(argv):
    pfad = os.path.join(ROOT, DATEI)
    neu, n = bearbeite(open(pfad, encoding='iso-8859-1').read())
    print('%s: %d Saetze' % (DATEI, n))
    if '--schreiben' in argv:
        open(pfad, 'w', encoding='iso-8859-1', newline='').write(neu)
        subprocess.run(['git', 'add', DATEI], check=True, cwd=ROOT)


if __name__ == '__main__':
    main(sys.argv[1:])
