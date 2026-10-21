#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kurze Pegelfits (< 182,6 Tage, ohne K2) analytisch koppeln (Oliver 21.10.2026).

S2 und K1 enthalten bei diesen Fits K2 bzw. P1 mit dem Gewicht des Messfensters
(py/kopplung_analytisch.py). Mit Verhaeltnis/Phasenabstand vom naechsten vollstaendigen Pegel
werden sie herausgerechnet und K2/P1 eingesetzt. Probe an 180 Stroemungssaetzen (Neufit aus
Rohreihen): S2 im Median 1,5 %, K1 3,6 % daneben (ohne Korrektur 21 / 26 %).

Usage: python3 py/pegel_kopplung_lauf.py [--schreiben]
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc                                           # noqa: E402
import kopplung_analytisch as A                                     # noqa: E402
import stroemung_kopplung as K                                      # noqa: E402
import xtide_modell as X                                            # noqa: E402
from generate_germany_harmonics_175 import CONSTITUENTS_175         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEIEN = ['harmonics/utide/harmonics_utide_observations.txt', 'harmonics/utide/harmonics_utide_tidetables.txt']
N175 = [n for n, _ in CONSTITUENTS_175]
# Olivers Dateien mit offenen Aenderungen: nur auf HEAD-Basis stagen
OLIVER = {'harmonics/utide/harmonics_utide_tidetables.txt'}
NOTIZ = '# note: 20261021 S2/K1 corrected for K2/P1 inside the %d-day window (ratio/lag of %s, %.0f km); K2/P1 added'


def bearbeite(text, datei, ausgabe=True):
    L = text.split('\n')
    namen, sp, _a, _f = X.kopf_lesen(os.path.join(ROOT, datei))
    st = [k for k in range(len(L) - 1) if L[k] and not L[k].startswith('#') and hc.MERIDIAN.match(L[k + 1])]
    v, aend = 0, []
    for k in st:
        kopf = '\n'.join(L[v:k])
        v = k
        m = re.search(r'(?:from|period=)\s*(\d{4}-\d\d-\d\d)\s*(?:to|\.\.)\s*(\d{4}-\d\d-\d\d)', kopf)
        if not m or '20261021 S2/K1 corrected' in kopf:
            continue
        t0, t1 = A.unix(m.group(1)), A.unix(m.group(2)) + 86400
        tage = (t1 - t0) / 86400
        slots = L[k + 3:k + 3 + 175]
        alt = {}
        for n, z in zip(N175, slots):
            f = z.split()
            if f[0] != 'x':
                assert f[0] == n, (L[k], n, z)
                alt[n] = (float(f[1]), float(f[2]))
        if tage >= 182.6 or 'K2' in alt or 'S2' not in alt:
            continue
        mer = L[k + 1].split()[0]
        vz = -1.0 if mer[0] == '-' else 1.0
        hh, mm = mer.lstrip('+-').split(':')
        meridian = vz * (int(hh) + int(mm) / 60)
        la = float(re.search(r'# !latitude: (\S+)', kopf).group(1))
        lo = float(re.search(r'# !longitude: (\S+)', kopf).group(1))
        rat, pn, km = K.verhaeltnisse(la, lo, 300)
        if rat is None:
            print('kein Pegel bis 300 km:', L[k])
            continue
        g = {n: (a, X.greenwich(kap, sp[n], meridian) % 360) for n, (a, kap) in alt.items()}
        neu = A.korrigiere(K.KOPF, g, t0, t1, rat)
        lok = {n: (a, (kap + sp[n] * meridian) % 360) for n, (a, kap) in neu.items()}
        if ausgabe:
            print('%-60s %3.0f d  S2 %.3f -> %.3f  K2 %.3f  K1 %.3f -> %.3f  P1 %.3f  (%s %.0f km)' % (
                L[k][:60], tage, alt['S2'][0], lok['S2'][0], lok['K2'][0], alt.get('K1', (0, 0))[0],
                lok.get('K1', (0, 0))[0], lok.get('P1', (0, 0))[0], pn.split(',')[0], km))
        aend.append((k, lok, tage, pn, km))
    for k, lok, tage, pn, km in reversed(aend):
        for j, n in enumerate(N175):
            if n in ('S2', 'K2', 'K1', 'P1') and n in lok:
                L[k + 3 + j] = '%-15s %.4f  %.2f' % (n, lok[n][0], lok[n][1])
        L.insert(k, NOTIZ % (round(tage), pn.split(',')[0][:40], km))
    return '\n'.join(L), len(aend)


def main(argv):
    for datei in DATEIEN:
        pfad = os.path.join(ROOT, datei)
        neu, n = bearbeite(open(pfad, encoding='iso-8859-1').read(), datei)
        print('%s: %d Saetze' % (datei, n))
        if '--schreiben' in argv:
            open(pfad, 'w', encoding='iso-8859-1', newline='').write(neu)
            if datei in OLIVER:
                head = subprocess.run(['git', 'show', 'HEAD:' + datei], capture_output=True, cwd=ROOT).stdout.decode('iso-8859-1')
                h, nh = bearbeite(head, datei, False)
                blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], input=h.encode('iso-8859-1'),
                                      capture_output=True, cwd=ROOT).stdout.decode().strip()
                subprocess.run(['git', 'update-index', '--cacheinfo', '100644,%s,%s' % (blob, datei)], check=True, cwd=ROOT)
                print('   gestaged auf HEAD-Basis: %d Saetze' % nh)
            else:
                subprocess.run(['git', 'add', datei], check=True, cwd=ROOT)


if __name__ == '__main__':
    main(sys.argv[1:])
