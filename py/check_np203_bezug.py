#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft, ob die Part-II-Transfers den richtigen Bezugshafen benutzen.

Hintergrund: In ATT Part II gilt der eingerahmte Standardhafen ueber einer
Gruppe bis zum naechsten eingerahmten Kopf. Ein Standardhafen, der INNERHALB
der Liste an seiner geografischen Stelle steht ("STANDARD PORT / See Table V"),
ist nur ein Eintrag -- kein neuer Bezug. Der Import von 2026-06 hat das
verwechselt und ab jedem solchen Eintrag den Bezug gewechselt.

Die Soll-Zuordnung steht in harmonics/help/np203_part2_bezugshaefen.json,
am 20260730 aus den Scans der Seiten 222-238 gelesen.

Aufruf: python3 py/check_np203_bezug.py [--alle]
"""
from __future__ import annotations
import json
import re
import sys

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'
JSON = '/home/oliver/weather/harmonics/help/np203_part2_bezugshaefen.json'


def key(att):
    m = re.match(r'(\d+)(.*)', att)
    return (int(m.group(1)), m.group(2))


def gruppe(att, gruppen):
    """Erste Gruppe, deren Bereich die Nummer enthaelt."""
    k = key(att)
    for g in gruppen:
        if key(g['von']) <= k <= key(g['bis']):
            return g
    return None


def bestand():
    """att -> (Name, benutzter Bezugshafen oder None)."""
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    out, att, ref = {}, None, None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att, ref = l.split(': ')[1].strip(), None
        elif l.startswith('# note: NP203 Part II Sekundaerhafen-Transfer von '):
            ref = re.match(r'# note: NP203 Part II Sekundaerhafen-Transfer von (.+?) \(att', l).group(1)
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att:
            out[att] = (L[i - 1].strip(), ref)
            att = None
    return out


# Derselbe Hafen, anderer Name in unserer Sammlung.
ALIAS = [
    {'kilindini', 'mombasakilindiniharbour', 'mombasa'},
    {'portsultanqaboos', 'muscatsultanqaboosport', 'muscat'},
    {'jebelali', 'minajebelali'},
    {'suezassuways', 'suez'},
]


def _n(s):
    return re.sub(r'[^a-z]', '', s.split(',')[0].lower())


def passt(benutzt, buch):
    """Grober Namensvergleich -- unsere Namen tragen Zusaetze."""
    x, y = _n(benutzt), _n(buch)
    for g in ALIAS:
        if x in g and y in g:
            return True
    a = re.sub(r'[^a-z]', '', benutzt.split(',')[0].split('(')[0].lower())
    b = re.sub(r'[^a-z]', '', buch.split('(')[0].lower())
    return bool(a) and bool(b) and (a.startswith(b[:6]) or b.startswith(a[:6]))


def main():
    alle = '--alle' in sys.argv
    gruppen = json.load(open(JSON))['gruppen']
    B = bestand()

    falsch, ohne_gruppe, ok = [], [], 0
    for att, (name, ref) in sorted(B.items(), key=lambda x: key(x[0])):
        if ref is None:
            continue                       # laeuft schon ueber Part III
        g = gruppe(att, gruppen)
        if g is None:
            ohne_gruppe.append((att, name, ref)); continue
        if passt(ref, g['name']):
            ok += 1
            if alle:
                print(f'  ok  {att:7s} {name[:40]:40s} {ref}')
        else:
            falsch.append((att, name, ref, g))

    print(f'{"att":8s} {"Station":40s} {"benutzt":26s} {"laut Buch (Seite)":30s}')
    print('-' * 110)
    for att, name, ref, g in falsch:
        print(f'{att:8s} {name[:40]:40s} {ref.split(",")[0][:26]:26s} '
              f'{g["name"][:22]:22s} S.{g["seite"]}')
    for att, name, ref in ohne_gruppe:
        print(f'{att:8s} {name[:40]:40s} {ref.split(",")[0][:26]:26s} -- keine Gruppe gefunden --')

    print(f'\n{ok} richtig, {len(falsch)} falsch, {len(ohne_gruppe)} ohne Gruppe '
          f'({ok + len(falsch) + len(ohne_gruppe)} Transfer-Stationen).')
    if falsch:
        from collections import Counter
        c = Counter((f[2].split(',')[0], f[3]['name']) for f in falsch)
        print('\nNach Bezugshafen:')
        for (benutzt, soll), n in c.most_common():
            print(f'  {n:4d}  {benutzt[:30]:30s} -> {soll}')


if __name__ == '__main__':
    main()
