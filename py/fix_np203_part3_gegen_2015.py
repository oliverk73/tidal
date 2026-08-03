#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Part III der Standardhaefen gegen den 2015er Scan richtigstellen.

Anlass: der HAT-Test meldete 4279 Bandar-e Mahshahr (+0.42 m) und 4325 Kori
Creek Entrance (+0.91 m) ueber HAT. Die Pruefung der Buchseite ergab zweierlei:

1. Der Import vom 20260615 hat Zahlen verschoben. Bei 4325 steht in beiden
   Ausgaben (2002 und 2015) uebereinstimmend M2 349/1.00, S2 030/0.32,
   K1 064/0.37 -- in der Datei stand M2 100/1.00, S2 132/0.64, K1 037/0.74.
   Das Muster ist immer dasselbe: eine Amplitude wird als Phase gelesen
   ("1.00" -> 100) oder eine Phase als Amplitude ("074" -> 0.74). Betroffen
   sind 32 der 107 Stationen, meist nur in einer einzelnen Zahl.
   BUCH unten ist Zeile fuer Zeile von den Scanseiten S.240-249 abgelesen und
   gegen die OCR des 2002er Bandes gegengeprueft.

2. Die N2-Inferenz benutzte die rohe Phasendifferenz. g_N2 = g_M2 - 0.536 *
   (g_S2 - g_M2) verlangt die *kleine* Differenz; laeuft S2 ueber 360 hinweg
   (M2 z.B. 343 Grad, S2 51 Grad), liefert die rohe Rechnung -292 statt +68
   und die N2-Phase liegt 167 Grad daneben. Das traf 25 Stationen, darunter
   Mahshahr. Hier wird fuer alle 102 Stationen mit Inferenz neu gerechnet.

Aufruf: venv/bin/python py/fix_np203_part3_gegen_2015.py
"""
from __future__ import annotations
import os
import re
import shutil
import time

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203.txt'
BACKUP = '/home/oliver/weather/harmonics/backup'

# att -> {'z0': m} und/oder Konstituente -> (Amplitude, Phase) laut Buch.
# Nur die Werte, die von der Datei abwichen.
BUCH = {
    # --- S.240 ---
    '3832': {'z0': 2.56, 'K1': (0.03, 38)},
    '3844': {'O1': (0.07, 36)},
    # --- S.241 ---
    '3932': {'M2': (0.20, 43), 'O1': (0.04, 56)},
    # --- S.242 ---
    '4015': {'S2': (0.53, 153)},
    '4112': {'S2': (0.14, 4)},
    # 4151 stand noch komplett auf der Ausgabe 2002 -- hier der 2015er Satz.
    '4151': {'z0': 0.58, 'M2': (0.10, 328), 'S2': (0.04, 274),
             'K1': (0.19, 38), 'O1': (0.08, 34)},
    # --- S.243 ---
    '4170': {'K1': (0.38, 39), 'O1': (0.18, 41)},
    '4175': {'K1': (0.40, 43), 'O1': (0.20, 42)},
    '4188': {'S2': (0.26, 307), 'K1': (0.38, 36)},
    '4189a': {'K1': (0.40, 48), 'O1': (0.20, 40)},
    '4189b': {'S2': (0.26, 309), 'K1': (0.40, 39), 'O1': (0.22, 39)},
    '4191': {'M2': (0.68, 274)},
    # --- S.244 ---
    '4199': {'O1': (0.18, 63)},
    # --- S.245 ---
    '4243': {'K1': (0.20, 99), 'O1': (0.09, 42)},
    # --- S.246 ---
    '4263': {'M2': (0.95, 343), 'S2': (0.34, 45)},
    '4264': {'M2': (0.99, 341)},
    '4277': {'K1': (0.49, 301), 'O1': (0.31, 253)},
    '4280': {'S2': (0.26, 334), 'O1': (0.30, 252)},
    # --- S.247 ---
    '4325': {'M2': (1.00, 349), 'S2': (0.32, 30), 'K1': (0.37, 64)},
    '4334': {'M2': (1.59, 44), 'O1': (0.25, 73)},
    '4340': {'M2': (0.54, 327), 'S2': (0.20, 5), 'K1': (0.36, 63),
             'O1': (0.18, 58)},
    # --- S.248 ---
    '4356': {'K1': (0.53, 62), 'O1': (0.25, 60)},
    '4357': {'K1': (0.49, 53), 'O1': (0.21, 56)},
    '4358': {'O1': (0.21, 50)},
    '4373': {'K1': (0.32, 52)},
    '4374': {'M2': (0.56, 311)},
    '4381': {'K1': (0.24, 58)},
    '4394': {'K1': (0.21, 51)},
    # --- S.249 ---
    '4439': {'K1': (0.05, 328), 'O1': (0.01, 3)},
    '4440': {'K1': (0.08, 91)},
    '4448': {'M2': (0.26, 250), 'O1': (0.03, 331)},
    '4461': {'O1': (0.04, 328)},
}

KONST = re.compile(r'^(\w+)\s+([\d.]+)\s+([\d.]+)\s*$')


def zeile(name, amp, phase):
    return f'{name:<15s} {amp:.4f}  {phase:.2f}'


def inferenz(m2, s2):
    """N2 und K2 nach ATT-Regel. Die Phasendifferenz wird auf (-180,180]
    normiert -- ohne das laeuft die Rechnung ueber den Nullpunkt aus dem
    Ruder."""
    (am, gm), (as_, gs) = m2, s2
    d = (gs - gm + 180) % 360 - 180
    n2 = (0.19 * am, (gm - 0.536 * d) % 360)
    k2 = (0.27 * as_, gs % 360)
    return n2, k2


def main():
    src = open(TXT, encoding='iso-8859-1').read()
    L = src.split('\n')
    starts = [i for i, l in enumerate(L) if l.startswith('# BEGIN HOT COMMENTS')]
    starts.append(len(L))

    geaendert, neu_inferiert, offen = [], 0, set(BUCH)
    for a, b in zip(starts, starts[1:]):
        att, note, pos = None, '', {}
        for i in range(a, b):
            l = L[i]
            if l.startswith('# att_number:'):
                att = l.split(':', 1)[1].strip()
            elif l.startswith('# note:'):
                note += l
            else:
                m = KONST.match(l)
                if m:
                    pos[m.group(1)] = (i, float(m.group(2)), float(m.group(3)))
        if att is None:
            continue

        aend = []
        korr = BUCH.get(att, {})
        offen.discard(att)
        for k, v in korr.items():
            if k == 'z0':
                for i in range(a, b):
                    if re.match(r'^[\d.]+ meters$', L[i]):
                        alt = float(L[i].split()[0])
                        if abs(alt - v) > 1e-9:
                            L[i] = f'{v:.4f} meters'
                            aend.append(f'Z0 {alt:.2f}->{v:.2f}')
                        break
                continue
            i, alt_a, alt_g = pos[k]
            if abs(alt_a - v[0]) > 1e-9 or abs(alt_g - v[1]) > 1e-9:
                L[i] = zeile(k, v[0], v[1])
                pos[k] = (i, v[0], v[1])
                aend.append(f'{k} {alt_g:.0f}/{alt_a:.2f}->{v[1]:.0f}/{v[0]:.2f}')

        # N2/K2 nachziehen, wo sie abgeleitet sind
        if 'inferiert' in note and 'M2' in pos and 'S2' in pos:
            n2, k2 = inferenz((pos['M2'][1], pos['M2'][2]),
                              (pos['S2'][1], pos['S2'][2]))
            for k, v in (('N2', n2), ('K2', k2)):
                if k not in pos:
                    continue
                i, alt_a, alt_g = pos[k]
                if abs(alt_a - v[0]) > 5e-5 or abs(alt_g - v[1]) > 5e-3:
                    L[i] = zeile(k, v[0], v[1])
                    aend.append(f'{k} {alt_g:.0f}/{alt_a:.2f}->{v[1]:.0f}/{v[0]:.2f}')
            neu_inferiert += 1

        if aend:
            geaendert.append((att, aend))
            # Herkunftsvermerk direkt hinter die letzte note-Zeile
            letzte = max(i for i in range(a, b) if L[i].startswith('# note:'))
            L.insert(letzte + 1,
                     '# note: 20260802 gegen den Scan der Ausgabe 2015 richtiggestellt '
                     '(Part III).')
            starts = [s + 1 if s > letzte else s for s in starts]

    if offen:
        raise SystemExit(f'nicht gefunden: {sorted(offen)}')

    stamp = time.strftime('%Y%m%d')
    shutil.copy2(TXT, f'{BACKUP}/harmonics_att_np203_pre_part3fix_{stamp}.txt')
    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    os.chmod(TXT, 0o600)

    for att, aend in geaendert:
        print(f'{att:7s} ' + ', '.join(aend))
    print(f'\n{len(geaendert)} Stationen geaendert, {neu_inferiert} mit Inferenz geprueft.')


if __name__ == '__main__':
    main()
