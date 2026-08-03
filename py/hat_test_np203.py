#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HAT-Test: vergleicht den vorhergesagten Jahresmaximalwert jeder Station mit
dem HAT aus ATT NP203 Table V Part 2.

HAT ist der hoechste astronomisch moegliche Wasserstand. Der ueber ein volles
Jahr vorhergesagte Maximalwert muss knapp darunter liegen. Die Pruefung stammt
aus derselben Quelle wie die Daten und braucht keine Modellannahmen.

Toleranz nach oben: +0.30 m plus die Amplituden der abgeleiteten N2/K2. ATT
rechnet HAT aus M2, S2, K1 und O1; jede Konstituente, die wir zusaetzlich
ansetzen, kann den Jahresmaximalwert ueber diesen HAT heben, und zwar umso
mehr, je groesser der Hub ist. Der feste Zuschlag allein reichte deshalb bei
4279 Bandar-e Mahshahr nicht (N2 0.29 m + K2 0.14 m, Ueberschuss +0.43 m,
ohne die beiden nur +0.13 m) -- 20260802 geprueft, die Konstanten stimmen
Ziffer fuer Ziffer mit S.246. Nach unten wird ab -1.00 m gemeldet: so viel
fehlender Hub deutet auf einen geschrumpften Part-II-Transfer hin.

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

HARM = '/home/oliver/weather/harmonics'
TCD = f'{HARM}/binary/harmonics_att_np203_secondary.tcd'
TXT = f'{HARM}/att/harmonics_att_np203_secondary.txt'
HAT2 = f'{HARM}/help/np203_table5_part2_hat.json'    # Sekundaerhaefen
HAT1 = f'{HARM}/help/np203_table5_part1_levels.json'  # Standardhaefen
OBEN, UNTEN = 0.30, -1.00

# Welche Textquelle zu welcher TCD gehoert -- der Test braucht die Namen und
# att-Nummern, die nur im Text stehen.
QUELLE = {'harmonics_att_np203_secondary': TXT,
          'harmonics_att_np203': f'{HARM}/att/harmonics_att_np203.txt'}


def hat_tabelle():
    """att -> HAT, aus Table V Part 2 (Sekundaer-) und Part 1 (Standardhaefen)."""
    H = dict(json.load(open(HAT2))['hat'])
    P1 = json.load(open(HAT1))
    for teil in ('halbtaegig', 'tagesungleich'):
        for v in P1[teil].values():
            if v.get('att') and v.get('hat') is not None:
                H.setdefault(v['att'], v['hat'])
    return H


def zuschlag(path):
    """att-Nummer -> Summe der abgeleiteten N2/K2-Amplituden. Um so viel darf
    der Jahresmaximalwert den HAT des Buches ueberschreiten, ohne dass etwas
    faul waere."""
    L = open(path, encoding='iso-8859-1').read().split('\n')
    out, att, note, s = {}, None, '', 0.0
    for l in L + ['# BEGIN HOT COMMENTS']:
        if l.startswith('# BEGIN HOT COMMENTS'):
            if att:
                out[att] = s if 'inferiert' in note else 0.0
            att, note, s = None, '', 0.0
        elif l.startswith('# att_number:'):
            att = l.split(': ')[1].strip()
        elif l.startswith('# note:'):
            note += l
        else:
            m = re.match(r'^(N2|K2)\s+([\d.]+)\s+[\d.]+\s*$', l)
            if m:
                s += float(m.group(2))
    return out


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
    # Argument schlaegt HFILE_PATH schlaegt Vorgabe. Ohne die mittlere Stufe
    # testet ein gesetztes HFILE_PATH stillschweigend die alte TCD aus binary/.
    tcd = args[0] if args else os.environ.get('HFILE_PATH') or TCD
    txt = args[1] if len(args) > 1 else QUELLE.get(
        os.path.basename(tcd)[:-4], TXT)
    print(f'TCD:  {tcd}\nText: {txt}\n')
    zeige_alle = '--all' in sys.argv
    HAT = hat_tabelle()
    NAME = stations(txt)
    ZU = zuschlag(txt)

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
        oben = OBEN + ZU.get(att, 0.0)
        flag = '  <-- ueber HAT' if d > oben else ('  <-- weit unter HAT' if d < UNTEN else '')
        if flag:
            auffaellig.append((att, name, hat, mx, d))
        if flag or zeige_alle:
            print(f'{att:7s} {name[:44]:44s} HAT {hat:5.2f}  max {mx:5.2f}  {d:+5.2f}{flag}')

    print(f'\n{treffer} Stationen geprueft, {len(auffaellig)} auffaellig, '
          f'{len(fehlend)} ohne HAT im Buch (Standardhaefen oder "no data").')


if __name__ == '__main__':
    main()
