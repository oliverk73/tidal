#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traegt die MSf-Konstituente aus ATT NP203 Table VI ein.

Hintergrund: An zwoelf flachen Haefen schwankt das MITTELWASSER selbst im
Vierzehntagerhythmus -- bei Kolkata um 0.54 m zwischen Springtag und einer
Woche danach. Part II schreibt bei diesen Haefen ein "w" in die ML-Spalte und
verweist auf Table VI (S.xxxviii), die korrigierte ML-Werte fuer den Springtag
und jeden Tag davor/danach gibt.

Die Tabelle ist eine reine Kosinuskurve mit der MSf-Periode (14.765 Tage) --
nachgerechnet weicht sie um hoechstens 0.031 m ab. Damit ist die Umsetzung
eindeutig:

    Amplitude = (ML_Springtag - ML_+7Tage) / 2
    Z0        = Mittelwert beider (steht als "Average ML" in der Tabelle)

Die Phase folgt aus der Ueberlegung, dass das Mittelwasser-Maximum auf den
Springtag faellt. Springtide heisst: M2 und S2 sind in Phase, also

    sigma_MSf * t + V_MSf = g_S2 - g_M2        (wegen S2 - M2 = MSf)

und das MSf-Glied hat sein Maximum bei sigma_MSf * t + V_MSf = g_MSf. Daraus

    g_MSf = g_S2 - g_M2

Das ist unabhaengig von der Meridiankonvention, weil alle drei Phasen in
derselben stehen. Gegenprobe mit dem Buch: Es gibt an, dass der Springtag
x Tage nach Neu- und Vollmond liegt (x=2 fuer alle hiesigen Haefen), also
g_MSf = x * 24.38 Grad = 48.8 Grad. Bei den Haefen mit gemessenen
Part-III-Konstanten kommt g_S2 - g_M2 auf 1.93 bis 2.01 Tage heraus -- der
Befund des Buches wird damit bestaetigt.

Nicht in unserer Sammlung: 4346 Bhavnagar und 4354 Tapi River (Hazira) sind
Standardhaefen ohne Konstanten im Buch, 4475a Dhamra fehlt uns ganz.

Aufruf: python3 py/add_np203_table6_msf.py [--write]
"""
from __future__ import annotations
import os
import re
import shutil
import sys
from datetime import datetime

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'
HARM = '/home/oliver/weather/harmonics'
SPEED_MSF = 1.0158958
GRAD_PRO_TAG = SPEED_MSF * 24.0

# ATT NP203 Table VI, S.xxxviii, am 20260801 aus dem Scan gelesen.
# att: (x, Average ML, [ML am Springtag, dann 1..7 Tage davor/danach])
T6 = {
    '4326':  (2, 2.53, [2.70, 2.68, 2.64, 2.57, 2.49, 2.42, 2.38, 2.36]),
    '4327':  (2, 1.90, [2.00, 1.99, 1.96, 1.92, 1.88, 1.84, 1.81, 1.80]),
    '4346':  (2, 6.07, [6.19, 6.18, 6.14, 6.10, 6.04, 6.00, 5.96, 5.95]),
    '4349':  (2, 4.90, [5.20, 5.17, 5.09, 4.97, 4.83, 4.71, 4.63, 4.60]),
    '4350':  (2, 4.22, [4.38, 4.36, 4.32, 4.26, 4.18, 4.12, 4.08, 4.06]),
    '4354':  (1, 2.25, [2.57, 2.54, 2.45, 2.32, 2.18, 2.05, 1.96, 1.93]),
    '4362':  (2, 2.59, [2.68, 2.67, 2.65, 2.61, 2.57, 2.53, 2.51, 2.50]),
    '4472':  (2, 1.16, [1.24, 1.23, 1.21, 1.18, 1.14, 1.11, 1.09, 1.08]),
    '4475a': (2, 2.00, [2.06, 2.05, 2.04, 2.01, 1.99, 1.96, 1.95, 1.94]),
    '4476':  (2, 1.77, [1.88, 1.87, 1.84, 1.79, 1.75, 1.70, 1.67, 1.66]),
    '4484':  (2, 3.30, [3.47, 3.45, 3.41, 3.35, 3.28, 3.21, 3.16, 3.13]),
    '4488':  (2, 3.19, [3.46, 3.44, 3.37, 3.27, 3.15, 3.05, 2.96, 2.92]),
}


def order(L):
    """Reihenfolge der 175 Konstituenten-Slots aus dem Dateikopf."""
    i = next(k for k, l in enumerate(L) if l.startswith('# Constituent speeds'))
    out = []
    for l in L[i:]:
        m = re.match(r'^(\S+)\s+[\d.]+\s*$', l)
        if m:
            out.append(m.group(1))
        elif out and l.startswith('#'):
            break
    return out


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    ORDER = order(L)
    islot = ORDER.index('MSF')

    # Bloecke einlesen: att -> (Kopfanfang, Namenszeile, erste Konstituentenzeile)
    bl, att = {}, None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att = l.split(': ')[1].strip()
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att:
            s = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
            bl[att] = (s, i - 1, i + 2)
            att = None

    print(f'MSf-Slot Nr. {islot} von {len(ORDER)}; ein Tag = {GRAD_PRO_TAG:.2f} Grad\n')
    print(f'{"att":7s} {"Station":34s} {"A":>6s} {"g":>7s} {"Buch x*Grad":>11s} {"Fit":>6s}')
    print('-' * 76)

    todo = []
    for a, (x, mittel, v) in sorted(T6.items()):
        if a not in bl:
            print(f'{a:7s} -- nicht in der Sammlung --')
            continue
        s, ni, c0 = bl[a]
        con = {}
        for k in range(c0, c0 + len(ORDER)):
            m = re.match(r'^([A-Z][A-Z0-9]*)\s+([\d.]+)\s+([\d.]+)$', L[k])
            if m:
                con[m.group(1)] = (float(m.group(2)), float(m.group(3)))
        if 'M2' not in con or 'S2' not in con:
            print(f'{a:7s} {L[ni].strip()[:34]:34s} ohne M2/S2 -- uebersprungen')
            continue
        A = (v[0] - v[-1]) / 2.0
        g = (con['S2'][1] - con['M2'][1]) % 360.0
        # Kosinusfit gegen die Buchzeile, als Kontrolle der Ablesung
        import math
        fit = max(abs(mittel + A * math.cos(math.radians(GRAD_PRO_TAG * d)) - v[d])
                  for d in range(8))
        print(f'{a:7s} {L[ni].strip()[:34]:34s} {A:6.3f} {g:7.2f} {x * GRAD_PRO_TAG:11.1f} '
              f'{fit:6.3f}')
        if fit > 0.05:
            print(f'{"":7s} ACHTUNG: Fit ueber 0.05 m -- Ablesung pruefen')
        todo.append((a, s, c0 + islot, A, g, x))

    if not write:
        print(f'\n{len(todo)} Stationen. (Dry-run. --write zum Schreiben.)')
        return

    shutil.copy(TXT, f'{HARM}/backup/harmonics_att_np203_secondary_pre_table6_'
                     f'{datetime.now():%Y%m%d}.txt')
    # von hinten nach vorn, damit die eingefuegten Notizzeilen die Indizes
    # der noch folgenden Bloecke nicht verschieben
    for a, s, islot_abs, A, g, x in sorted(todo, key=lambda t: -t[1]):
        alt = L[islot_abs]
        if not (alt == 'x 0 0' or alt.startswith('MSF')):
            print(f'{a}: unerwarteter Slot-Inhalt "{alt}" -- ABBRUCH')
            return
        L[islot_abs] = f'{"MSF":<16}{A:.4f}  {g:.2f}'
        j = next(k for k in range(s, islot_abs) if L[k].startswith('# date_imported:'))
        L[j:j] = [f'# note: MSf aus NP203 Table VI S.xxxviii: ML schwankt vierzehntaegig '
                  f'um {2 * A:.2f} m',
                  f'# note: (Springtag {A + (0):.2f} m ueber Mittel). Phase = g(S2)-g(M2) '
                  f'= {g:.1f} Grad, so dass das',
                  f'# note: Maximum auf den Springtag faellt -- laut Buch {x} Tage nach '
                  f'Neu-/Vollmond.']

    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    os.chmod(TXT, 0o600)
    print(f'\n{len(todo)} Stationen mit MSf versehen.')


if __name__ == '__main__':
    main()
