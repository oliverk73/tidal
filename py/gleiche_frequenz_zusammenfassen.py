#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paare gleicher (oder fast gleicher) Frequenz in eigenen Fits zu einer Konstituente zusammenfassen
(Oliver 11.11.2026: "Ja").

Anlass: qld_msq_fit.rayleigh() gab bis 11.11.2026 ab 400 Tagen die volle Liste zurueck; Paare wie L2/2MN2, MNS2/EPS2,
SA/SA-IOS, H2/MSP2 (Frequenzabstand < 1e-4 Grad/h, trennbar erst nach Jahrhunderten) wurden gegenphasig aufgeblasen
(Hamburg MNS2/EPS2 je 1 m). Im Fitzeitraum heben sie sich auf, danach driften sie mit den verschiedenen Knotenfaktoren
(2020-2040 meist 1-4 cm, Hamburg 7-8 cm).

Zusammenfassung im Fitjahr y0 (Mitte der Jahre in den Notizzeilen, sonst Importjahr - 1), damit die Kurve dort gleich
bleibt:  a*e^(-ig) = a_k*e^(-ig_k) + (f_j/f_k) * a_j * e^(i(V_j+u_j - V_k-u_k)) * e^(-ig_j)
Behalten: bei gegenphasig aufgeblasenen Paaren die Konstituente, die rayleigh() heute waehlen wuerde (Vorrangliste,
dann Kopfreihenfolge), sonst die groessere.
Nur harmonics/utide/harmonics_utide_{observations,tidetables}.txt; nur Paare mit beiden Amplituden > 0.

Usage: venv/bin/python py/gleiche_frequenz_zusammenfassen.py [--schreiben]
"""
import cmath
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEIEN = ['harmonics/utide/harmonics_utide_observations.txt', 'harmonics/utide/harmonics_utide_tidetables.txt']
VORRANG = ['M2', 'S2', 'K1', 'O1', 'N2', 'K2', 'P1', 'Q1', 'M4', 'MS4', 'M6', 'MK3', 'MN4', 'L2', 'NU2', 'J1', 'M3',
           '2N2', 'MU2', 'OO1', 'SN4']


def fitjahr(kopfzeilen):
    jahre = []
    imp = None
    for z in kopfzeilen:
        if z.startswith('# date_imported:'):
            m = re.search(r'(\d{4})', z)
            imp = int(m.group(1)) if m else None
        if z.startswith('# note:'):
            jahre += [int(j) for j in re.findall(r'(?<!\d)(19[89]\d|20[0-2]\d)(?!\d)', z)]
    jahre = [j for j in jahre if 1980 <= j <= 2027]
    if jahre:
        return int(round((min(jahre) + max(jahre)) / 2))
    return (imp - 1) if imp else 2024


def main(argv):
    kopf = X.kopf_lesen(os.path.join(ROOT, DATEIEN[1]))
    namen, speeds, arg, fak = kopf
    paare = [(a, b) for i, a in enumerate(namen) for b in namen[i + 1:]
             if a in speeds and b in speeds and abs(speeds[a] - speeds[b]) < 1e-4]
    rang = {k: (VORRANG.index(k) if k in VORRANG else 100 + namen.index(k)) for k in namen}
    tg = np.arange(1609459200.0, 2240611200.0, 6 * 3600.0)           # 2021-2040, fuer die Driftprobe
    for datei in DATEIEN:
        pfad = os.path.join(ROOT, datei)
        T = open(pfad, encoding='iso-8859-1').read().split('\n')
        recs = [r for r in H.load_records() if r['file'] == datei]
        einfuegen = []
        n = 0
        drift = []
        for r in recs:
            a = r['amp']
            treffer = [(x, y) for x, y in paare if x in a and y in a and a[x][0] > 0 and a[y][0] > 0]
            if not treffer:
                continue
            i0 = r['line'] - 1                                        # Namenszeile (0-basiert)
            k = i0 - 1
            while k >= 0 and T[k].startswith('#') and T[k].strip() != '#':
                k -= 1
            kz = T[k + 1:i0]
            y0 = fitjahr(kz)
            mer = X.satz_lesen(pfad, r['name'])[3]
            zeilen = {}
            for j in range(len(namen)):
                p = T[i0 + 3 + j].split()
                if p and p[0] != 'x':
                    assert p[0] == namen[j], (r['name'], p[0], namen[j])
                zeilen[namen[j]] = i0 + 3 + j
            w = {c: list(v) for c, v in a.items()}
            vorher = {c: (v[0], X.greenwich(v[1], speeds[c], mer)) for c, v in a.items() if c in speeds}
            text = []
            for x, y in treffer:
                # Aufgeblasen (gegenphasig, Resultierende < 50 % der groesseren): Rangfolge wie rayleigh(). Sonst traegt eine
                # der beiden echte Tide (Hamburg 2MN2 0,2 m neben L2 0,02 m) -> die groessere behalten, sonst erbt die Kurve
                # fremde Knotenmodulation.
                zx = w[x][0] * cmath.exp(-1j * math.radians(w[x][1] - arg[y0][x] - speeds[x] * 4383)) * fak[y0][x]
                zy = w[y][0] * cmath.exp(-1j * math.radians(w[y][1] - arg[y0][y] - speeds[y] * 4383)) * fak[y0][y]
                if abs(zx + zy) < 0.5 * max(abs(zx), abs(zy)):
                    bleibt, weg = sorted((x, y), key=lambda c: rang[c])
                else:
                    bleibt, weg = sorted((x, y), key=lambda c: -w[c][0])
                vk = arg[y0][bleibt] + speeds[bleibt] * 4383
                vj = arg[y0][weg] + speeds[weg] * 4383
                z = (w[bleibt][0] * cmath.exp(-1j * math.radians(w[bleibt][1]))
                     + fak[y0][weg] / fak[y0][bleibt] * w[weg][0]
                     * cmath.exp(1j * math.radians(vj - vk)) * cmath.exp(-1j * math.radians(w[weg][1])))
                w[bleibt] = [abs(z), math.degrees(-cmath.phase(z)) % 360]
                w[weg] = [0.0, 0.0]
                T[zeilen[bleibt]] = '%-15s %.4f  %.2f' % (bleibt, w[bleibt][0], w[bleibt][1])
                T[zeilen[weg]] = 'x 0 0'
                text.append('%s+%s->%s' % (bleibt, weg, bleibt))
            nachher = {c: (v[0], X.greenwich(v[1], speeds[c], mer)) for c, v in w.items() if c in speeds and v[0] > 0}
            d = SF.hoehe_und_ableitungen(tg, 0.0, vorher, kopf)[0] - SF.hoehe_und_ableitungen(tg, 0.0, nachher, kopf)[0]
            ty = np.arange(X.jahresbeginn(y0), X.jahresbeginn(y0 + 1), 3600.0)
            dy = SF.hoehe_und_ableitungen(ty, 0.0, vorher, kopf)[0] - SF.hoehe_und_ableitungen(ty, 0.0, nachher, kopf)[0]
            drift.append((float(np.ptp(d)), r['name'] + '  (im Fitjahr %d: %.1f cm; %s)' % (y0, 100 * np.ptp(dy), ', '.join(text))))
            einfuegen.append((k + 1, '# note: 20261111 gleichfrequente Paare zusammengefasst (Fitjahr %d): %s' % (y0, ', '.join(text))[:190]))
            n += 1
        for pos, z in sorted(einfuegen, reverse=True):
            T.insert(pos, z)
        drift.sort(reverse=True)
        print('%s: %d Saetze; groesste Kurvenaenderung 2021-2040 (= bisherige Drift):' % (datei, n))
        for v, nm in drift[:15]:
            print('   %5.1f cm  %s' % (100 * v, nm))
        if '--schreiben' in argv and n:
            from sicher_schreiben import schreiben
            '\n'.join(T).encode('latin-1')
            schreiben(pfad, '\n'.join(T))
            print('->', datei)


if __name__ == '__main__':
    main(sys.argv[1:])
