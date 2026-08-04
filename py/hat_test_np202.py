#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HAT-Test fuer NP202: vergleicht den vorhergesagten Jahresmaximalwert jeder
Station mit dem HAT aus ATT NP202 Table V Part 2 (Ausgabe 2015).

Gleiches Verfahren wie py/hat_test_np203.py: HAT ist der hoechste astronomisch
moegliche Wasserstand, der ueber ein volles Jahr vorhergesagte Maximalwert muss
knapp darunter liegen. Toleranz nach oben +0.30 m plus die Amplituden
abgeleiteter N2/K2, nach unten -1.00 m.

UNTERSCHIED ZU NP203 -- die Zuordnung laeuft ueber den NAMEN, nicht ueber die
Nummer. Unsere NP202-Nummerierung weicht an 17 Stellen vom Buch ab; wer nach
Nummer zuordnet, verpasst z.B. 2547 Wide Opening den HAT von Ship Channel.
Die Abweichungen stehen unten in VERSATZ und sind einzeln am Buchscan
nachgeschlagen, mehrere zusaetzlich ueber die Koordinaten bestaetigt.

Aufruf: venv/bin/python py/hat_test_np202.py [tcd] [txt] [--all]
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
import unicodedata

HARM = '/home/oliver/weather/harmonics'
TCD = f'{HARM}/binary/harmonics_att_np202_secondary.tcd'
TXT = f'{HARM}/att/harmonics_att_np202_secondary.txt'
TAB = f'{HARM}/help/np202_2015_table5_part2_hat.tsv'
OBEN, UNTEN = 0.30, -1.00

# unsere att-Nummer -> Nummer im Buch. Nur die Faelle, wo beide auseinander
# gehen; der Name ist jeweils derselbe Ort.
VERSATZ = {
    '1086': '1085',    # Mys Bol'shoy Gorodetskiy
    '1295b': '1295a',  # Larvik; das Buch schreibt "Larvick"
    '1295c': '1295b',  # Sandefjord; das Buch schreibt "Sandjeford"
    '1330': '1338',    # Bjoern
    '1412.5': '1412a',  # Hanstholm
    '1425.5': '1425a',  # Wyk auf Foehr; das Buch fuehrt ihn als "Fohr, Wyk"
    '1433.6': '1435a',  # Linnenplate
    '1588': '1587a',   # Heurteauville
    '1589': '1588',    # Duclair
    '1615': '1611b',   # Saint-Germain-sur-Ay; Buch 1615 ist Erquy
    '2504': '2505',    # Casilda
    '2547': '2546',    # Wide Opening
    '2548': '2547',    # Ship Channel
    '2997': '3423',    # Quamarujuk -- bei uns doppelt, siehe DUBLETTE
    '3423': '3423a',   # Uummannaq
    '3434': '3434b',   # Narsaq
}

# Stationen, die das Buch nicht fuehrt -- kein Fehler, sie fallen nur aus dem
# Test heraus.
OHNE_HAT = {
    '1295a': 'Porsgrunn steht nicht in Table V Part 2',
    '2457': 'English Harbour steht nicht in Table V Part 2',
}

# Namen, die bei uns anders lauten als im Buch, wo aber die Nummer stimmt.
# Ueber die Koordinaten geprueft -- hier NICHT nach Namen zuordnen.
NAME_ABWEICHEND = {
    '1083': 'wir "Ostrov Velikiy", Buch 1083 "Ostrov Veshnyak"; unsere Position '
            '67.10N 41.38E liegt an der Terski-Kueste, passt zum Buch',
    '1103': 'wir "Mys Bezlavnyy", Buch 1103 "Mys Bazisnyy"; Position im Kola-Fjord',
    '1212': 'wir "Tosbotn", Buch 1212 "Borkamo"',
    '1218': 'wir "Selva", Buch 1218 "Selvnes"',
    '1236': 'wir "Honningsvag (Stattvagen)" -- zwei Orte vermischt. Position '
            '62.19N 5.20E ist Stattvagen auf Stadlandet; Honningsvag in der '
            'Finnmark ist Buchnummer 1145. Nummer stimmt, unser Name nicht.',
}

# 2997 Quamarujuk und 3423 Uummannaq sind bei uns getrennte Stationen, im Buch
# 3423 und 3423a. 2997 ist im Buch nicht vergeben (2995 -> 3001, Nova Scotia).
DUBLETTE = '2997'


def norm(s):
    s = unicodedata.normalize('NFD', s.split(',')[0].lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\(.*?\)', ' ', s)
    return re.sub(r'[^a-z0-9]', '', s)


def buchtabelle():
    """(nr -> hat, normierter Name -> [nr]) aus der Transkription."""
    hat, nach_name = {}, {}
    for l in open(TAB, encoding='utf-8'):
        if l.startswith('#') or not l.strip():
            continue
        nr, name, h = l.rstrip('\n').split('\t')
        hat[nr] = None if h == '-' else float(h)
        nach_name.setdefault(norm(name), []).append(nr)
    return hat, nach_name


def zuschlag(path):
    """att -> Summe der abgeleiteten N2/K2-Amplituden."""
    out, att, note, s = {}, None, '', 0.0
    for l in open(path, encoding='iso-8859-1').read().split('\n') + ['# BEGIN HOT COMMENTS']:
        if l.startswith('# BEGIN HOT COMMENTS'):
            if att:
                out[att] = s if 'inferiert' in note else 0.0
            att, note, s = None, '', 0.0
        elif l.startswith('# att_number:'):
            att = l.split(':', 1)[1].strip()
        elif l.startswith('# note:'):
            note += l
        else:
            m = re.match(r'^(N2|K2)\s+([\d.]+)\s+[\d.]+\s*$', l)
            if m:
                s += float(m.group(2))
    return out


def stationen(path):
    """att -> Stationsname."""
    L = open(path, encoding='iso-8859-1').read().split('\n')
    out, att = {}, None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att = l.split(':', 1)[1].strip()
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att:
            out[att] = L[i - 1].strip()
            att = None
    return out


def jahresmax(name, tcd, jahr=2026):
    env = dict(os.environ, HFILE_PATH=tcd)
    env['PATH'] = env.get('PATH', '') + ':' + os.path.expanduser('~/.local/bin')
    p = subprocess.run(['tide', '-l', name, '-b', f'{jahr}-01-01 00:00',
                        '-e', f'{jahr + 1}-01-01 00:00', '-m', 's'],
                       capture_output=True, env=env)
    m = re.search(r'Maximum was\s+([-\d.]+)', p.stdout.decode('utf-8', 'replace'))
    return float(m.group(1)) if m else None


def hat_fuer(att, name, hat, nach_name):
    """HAT einer Station. Reihenfolge: Ausnahmeliste, dann Name, dann Nummer."""
    if att in OHNE_HAT:
        return None, 'nicht im Buch'
    if att in VERSATZ:
        return hat.get(VERSATZ[att]), f'Buch {VERSATZ[att]}'
    if att in NAME_ABWEICHEND:
        return hat.get(att), 'Nummer (Name weicht ab)'
    tref = nach_name.get(norm(name), [])
    if len(tref) == 1 and tref[0] != att:
        return hat.get(tref[0]), f'Name -> Buch {tref[0]}'
    return hat.get(att), 'Nummer'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    tcd = args[0] if args else os.environ.get('HFILE_PATH') or TCD
    txt = args[1] if len(args) > 1 else TXT
    zeige_alle = '--all' in sys.argv
    print(f'TCD:  {tcd}\nText: {txt}\n')

    hat, nach_name = buchtabelle()
    NAME = stationen(txt)
    ZU = zuschlag(txt)

    geprueft, ohne, auffaellig = 0, [], []
    schluessel = lambda a: (float(re.match(r'([\d.]+)', a).group(1)), a)
    for att in sorted(NAME, key=schluessel):
        name = NAME[att]
        h, woher = hat_fuer(att, name, hat, nach_name)
        if h is None:
            ohne.append((att, name, woher))
            continue
        mx = jahresmax(name, tcd)
        if mx is None:
            print(f'{att:7s} {name[:44]:44s} keine Vorhersage')
            continue
        geprueft += 1
        d = mx - h
        grenze = OBEN + ZU.get(att, 0.0)
        flag = ('  <-- ueber HAT' if d > grenze else
                '  <-- weit unter HAT' if d < UNTEN else '')
        if flag:
            auffaellig.append((att, name, h, mx, d))
        if flag or zeige_alle:
            print(f'{att:7s} {name[:44]:44s} HAT {h:5.2f}  max {mx:5.2f}  {d:+5.2f}{flag}')

    print(f'\n{geprueft} Stationen geprueft, {len(auffaellig)} auffaellig, '
          f'{len(ohne)} ohne HAT.')
    if zeige_alle and ohne:
        print('\nohne HAT:')
        for a, n, g in ohne:
            print(f'  {a:7s} {n[:44]:44s} {g}')


if __name__ == '__main__':
    main()
