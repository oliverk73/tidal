#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze neu fitten, deren Rohreihe in Ortszeit statt UTC gestempelt ist (13.11.2026).

Anlass: Die historischen Feuerschiff-Reihen (CMEMS in-situ, Elbe 1 1924-88, Elbe 4 und Bremen 1924-44) liegen gegen den
BSH-Gezeitenstromatlas in allen Jahrzehnten ohne Sommerzeit gleichmaessig +60..+75 min, in den Sommern 1940er/1980er
und in den Wintern 1940-44 (ganzjaehrige Kriegs-Sommerzeit) +115..+147 min -- also deutsche Ortszeit (MEZ/MESZ).
Rohreihe ueber py/strom_ellipsen_eigen.rohreihe, Stempel als Europe/Berlin (historische Regeln der tz-Datenbank) lesen,
nach UTC wandeln, mit cmems_stroemung_nachholen.analyse (gleiche Tiden wie der Satz) neu fitten. Ersetzt nur Z0- und
Konstantenzeilen und ergaenzt eine Notiz; Vorzeichen der Hauptachse wie im alten Satz (M2-Phase naechst der alten).

Usage: venv/bin/python py/zeitzone_neufit.py [--schreiben] [--tz Europe/Berlin] "<Satzname>" ...
"""
import datetime as dt
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                              # noqa: E402
import health_check as H                                           # noqa: E402
import strom_ellipsen_eigen as E                                   # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')


def main(argv):
    tz = argv[argv.index('--tz') + 1] if '--tz' in argv else 'Europe/Berlin'
    namen = [a for a in argv if not a.startswith('--') and a != tz]
    E.KOPF = X.kopf_lesen(P)
    kopf_namen, speeds = E.KOPF[0], E.KOPF[1]
    R = {r['name']: r for r in H.load_records()}
    txt = {n: t for n, t in E.saetze(P)}
    L = open(P, encoding='iso-8859-1').read().split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    for name in namen:
        r = R[name]
        df = E.rohreihe(txt[name], name, r['lat'], r['lon'])
        idx = df.index.tz_localize(tz, ambiguous='NaT', nonexistent='NaT')
        ok = ~idx.isna()
        df = df[ok]
        df.index = idx[ok].tz_convert('UTC').tz_localize(None)
        p = re.search(r'period=(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)', txt[name])
        if p:
            df = df.loc[p.group(1):p.group(2) + ' 23:59']
        _z0, alt, _e, mer = X.satz_lesen(P, name)
        res = C.analyse(df, r['lat'], C.KONST)
        k = res['konst']
        # Vorzeichen: Flutrichtung wie im alten Satz (alte M2-Phase minus ~1-2 h liegt nahe der neuen)
        g_alt = X.greenwich(alt['M2'][1], speeds['M2'], mer)
        d0 = abs((k['M2'][1] - g_alt + 180) % 360 - 180)
        d1 = abs((k['M2'][1] + 180 - g_alt + 180) % 360 - 180)
        vz = 1 if d0 <= d1 else -1
        if vz < 0:
            k = {c: (a, (g + 180) % 360) for c, (a, g) in k.items()}
        dm = ((k['M2'][1] - g_alt + 180) % 360 - 180) / speeds['M2'] * 60
        mean = res['mean'] * vz
        print('%-40s n=%6d  M2 %.3f -> %.3f kn  Phase %+5.0f min  (Achse %.0f%s)' % (
            name[:40], len(df), alt['M2'][0], k['M2'][0], dm, res['achse'], ', Vorzeichen gedreht' if vz < 0 else ''))
        if '--schreiben' not in argv:
            continue
        i = L.index(name)
        assert L[i + 1].split()[0] == '+00:00'
        L[i + 2] = '%.4f knots' % mean
        j = i + 3
        for c in kopf_namen:
            a = k.get(c)
            L[j] = '%-15s %.4f  %.2f' % (c, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0'
            j += 1
        L.insert(i, '# note: %s Zeitstempel der Rohreihe waren %s (MEZ/MESZ) statt UTC, nach UTC gewandelt und neu gefittet '
                    '(Phasen %+.0f min; py/zeitzone_neufit.py)' % (heute, tz, dm))
    if '--schreiben' in argv:
        from sicher_schreiben import schreiben
        schreiben(P, '\n'.join(L))
        print('->', os.path.relpath(P, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
