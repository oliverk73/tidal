#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HAT-Test: vergleicht den vorhergesagten Jahresmaximalwert jeder Station mit
dem HAT aus ATT NP203 Table V Part 2.

HAT ist der hoechste astronomisch moegliche Wasserstand. Der ueber ein volles
Jahr vorhergesagte Maximalwert muss knapp darunter liegen. Die Pruefung stammt
aus derselben Quelle wie die Daten und braucht keine Modellannahmen.

Toleranz nach oben: +0.30 m. Wir synthetisieren mit sechs bis acht
Konstituenten, ATT leitet HAT aus vier ab -- ein kleiner Ueberschuss ist
normal. Nach unten wird ab -1.00 m gemeldet: so viel fehlender Hub deutet auf
einen geschrumpften Part-II-Transfer hin.

NICHT geeignet waere die Summe aller Amplituden plus Z0 -- eine obere Schranke,
die nie erreicht wird (Fehlalarm Suhar 20260728).

Aufruf: python3 py/hat_test_np203.py [tcd-Datei] [--all]
        --all listet auch die unauffaelligen Stationen.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys

TCD = '/home/oliver/weather/harmonics/binary/harmonics_att_np203_secondary.tcd'
TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'
HATJSON = '/home/oliver/weather/harmonics/help/np203_table5_part2_hat.json'
OBEN, UNTEN = 0.30, -1.00


def stations(path):
    """att-Nummer -> Stationsname, aus der Textquelle."""
    L = open(path, encoding='iso-8859-1').read().split('\n')
    out, att = {}, None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att = l.split(': ')[1].strip()
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att:
            out[att] = L[i - 1].strip()
            att = None
    return out


def jahresmax(name, tcd, jahr=2026):
    env = dict(os.environ, HFILE_PATH=tcd)
    env['PATH'] = env.get('PATH', '') + ':' + os.path.expanduser('~/.local/bin')
    p = subprocess.run(['tide', '-l', name, '-b', f'{jahr}-01-01 00:00', '-e',
                        f'{jahr + 1}-01-01 00:00', '-m', 's'],
                       capture_output=True, env=env)
    txt = p.stdout.decode('utf-8', errors='replace')
    m = re.search(r'Maximum was\s+([-\d.]+)', txt)
    return float(m.group(1)) if m else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    tcd = args[0] if args else TCD
    zeige_alle = '--all' in sys.argv
    HAT = json.load(open(HATJSON))['hat']
    NAME = stations(TXT)

    treffer, fehlend, auffaellig = 0, [], []
    for att, name in sorted(NAME.items()):
        hat = HAT.get(att)
        if hat is None:
            fehlend.append(att); continue
        mx = jahresmax(name, tcd)
        if mx is None:
            print(f'{att:7s} {name[:44]:44s} keine Vorhersage'); continue
        d = mx - hat
        treffer += 1
        flag = '  <-- ueber HAT' if d > OBEN else ('  <-- weit unter HAT' if d < UNTEN else '')
        if flag:
            auffaellig.append((att, name, hat, mx, d))
        if flag or zeige_alle:
            print(f'{att:7s} {name[:44]:44s} HAT {hat:5.2f}  max {mx:5.2f}  {d:+5.2f}{flag}')

    print(f'\n{treffer} Stationen geprueft, {len(auffaellig)} auffaellig, '
          f'{len(fehlend)} ohne HAT im Buch (Standardhaefen oder "no data").')


if __name__ == '__main__':
    main()
