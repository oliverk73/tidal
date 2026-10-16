#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Teilt die CHS-Stromvorhersage-Saetze durch 1.943844 (doppelte Umrechnung m/s -> Knoten).

Befund 16.10.2026 (Pruefliste Stroemungen): Die 30 Saetze "CHS IWLS API predictions" in
harmonics_utide_current_tables.txt lagen 1.92-1.96 x ueber den amtlichen CHS-Vorhersagen
(wcsp1, 20.-26.10.2026: Seymour Narrows 23.7 gegen 12.2 kn, Sechelt 23.8 gegen 12.4 kn), und
ebenso ueber den unabhaengigen Saetzen von 1995 (2004er Datei) und NOAA Table 2. Die API liefert
die Vorhersage schon in Knoten; beim Fit wurde sie noch einmal mit 1.943844 (Knoten je m/s)
multipliziert. Phasen bleiben, Amplituden und Z0 werden geteilt.

Die 9 CHS-Messsaetze (wcs1) in harmonics_utide_current_observations.txt haben denselben Fehler:
gegen die amtlichen Ereignisse am selben Ort 1.66-2.08 x, nach der Korrektur 0.85-1.07 x.

Vorzeichen: 6 Vorhersagesaetze und der Messsatz Tillicum Bridge zeigen Flut, wo CHS (wcp1-events,
20.-27.10.2026, je 26-28 Ereignisse, alle) Ebbe meldet -> Phasen +180 Grad, Z0 und Richtungen getauscht.

Usage: python3 py/chs_stromtafel_einheit.py [--schreiben]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sicher_schreiben import schreiben                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEIEN = {os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt'):
           '# source: Canadian Hydrographic Service (CHS) IWLS API predictions',
           os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt'):
           '# source: Canadian Hydrographic Service (CHS) IWLS API, UTide'}
UMGEKEHRT = {"Big Bras D'Or, Canada Current", 'Tillicum Bridge, Canada Current', 'Dodd Narrows, Canada Current',
             'Weynton Passage, Canada Current', 'Nakwakto Rapids, Canada Current', 'Hiekish Narrows, Canada Current'}
F = 1.943844
NOTIZ = '# note: 20261016 Amplituden und Z0 durch 1.943844 geteilt: Fit hatte die CHS-Werte (schon in kn) noch einmal von m/s umgerechnet (Oliver).'
NOTIZ_DREH = '# note: 20261016 Flut/Ebbe vertauscht gegen CHS-Ereignisse (0 von 26-28 richtig): Phasen +180 Grad, Z0 und Richtungen getauscht (Oliver).'


def main(argv):
    for datei, quelle in DATEIEN.items():
        L = open(datei, encoding='iso-8859-1').read().split('\n')
        i, n, d = 0, 0, 0
        while i < len(L):
            if not L[i].startswith(quelle):
                i += 1
                continue
            k0 = i
            while k0 > 0 and L[k0 - 1].startswith('#'):
                k0 -= 1
            j = i
            while L[j].startswith('#'):
                j += 1
            name, kopf = L[j], L[k0:j]
            teilen = not any('1.943844' in x for x in kopf)
            drehen = name in UMGEKEHRT and not any('Flut/Ebbe vertauscht' in x for x in kopf)
            if teilen or drehen:
                m = re.match(r'^(-?[\d.]+) (knots)$', L[j + 2])
                assert m, (name, L[j + 2])
                z0 = float(m.group(1)) / (F if teilen else 1.0) * (-1 if drehen else 1)
                L[j + 2] = '%.4f knots' % z0
                k = j + 3
                while k < len(L) and (L[k] == 'x 0 0' or re.match(r'^\S+\s+[\d.]+\s+[\d.]+$', L[k])):
                    if L[k] != 'x 0 0':
                        c, a, g = L[k].split()
                        a = float(a) / (F if teilen else 1.0)
                        g = '%.2f' % ((float(g) + 180) % 360) if drehen else g
                        L[k] = '%-15s %.4f  %s' % (c, a, g)
                    k += 1
                if drehen:
                    for x in range(k0, j):
                        mm = re.match(r'# (max|min)_direction: (.*)', L[x])
                        if mm:
                            L[x] = '# %s_direction: %s' % ('min' if mm.group(1) == 'max' else 'max', mm.group(2))
                neu = ([NOTIZ] if teilen else []) + ([NOTIZ_DREH] if drehen else [])
                L[j:j] = neu
                n += teilen
                d += drehen
                print('  %-40s %s%s' % (name, 'geteilt ' if teilen else '', 'gedreht' if drehen else ''))
                i = j + len(neu) + 3
            else:
                i = j + 1
        print(os.path.basename(datei), n, 'geteilt,', d, 'gedreht')
        if '--schreiben' in argv and (n or d):
            schreiben(datei, '\n'.join(L))

if __name__ == '__main__':
    main(sys.argv[1:])
