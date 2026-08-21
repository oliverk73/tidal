#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht Saetze, deren Position von woanders stammt. Aendert nichts.

Zwei Fehlerbilder, beide an echten Faellen entwickelt:

  Kanal F  Ein Satz sitzt stellengenau auf den Koordinaten eines
           unverwandten Satzes, hat aber anderswo ein Namensgeschwister.
           So lag "Jacksonville, Acosta Bridge, Florida (5)" auf den
           Koordinaten von "Kings Bay, Navy Base, Georgia".

  Kanal G  Zwei Saetze gleichen Namens, eine Koordinate identisch, die
           andere um einen glatten Gradbetrag versetzt -- Ziffernfehler.
           So stand "Palmetto Bluff (4)" exakt 1.0000 Grad zu weit
           noerdlich.

Achtung bei Kanal G: liegen beide Werte auf einem groben Raster (halbe
oder ganze Grad), ist die glatte Differenz kein Ziffernfehler, sondern
zweimal grob gerundet. Die Rasterweite steht deshalb mit dabei.

Usage: python3 py/fremdkoordinaten.py
"""
from __future__ import annotations

import collections
import difflib
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, curve_diff, km            # noqa: E402
from positions_propose import gridsize_deg                       # noqa: E402


def _norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]', ' ', s)


def verwandt(a, b):
    """Gemeinsame Woerter, gleicher Schluessel -- oder blosse Transkription.

    "Ostrov Dolgiy" und "Dolgoi Island" sind derselbe Ort; ohne den
    zeichenweisen Vergleich gelten sie als unverwandt und ueberschwemmen
    Kanal F mit Fehlalarmen.
    """
    if a['toks'] & b['toks'] or a['key'] == b['key']:
        return True
    return difflib.SequenceMatcher(None, _norm(a['name']), _norm(b['name'])).ratio() > 0.55


def glatt(v):
    a = abs(v)
    return round(a) if a >= 0.5 and abs(a - round(a)) < 1e-6 and round(a) >= 1 else None


def main():
    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None]
    pos = collections.defaultdict(list)
    byk = collections.defaultdict(list)
    for x in recs:
        pos[(x['lat'], x['lon'])].append(x)
        if len(x['key']) >= 5:
            byk[x['key']].append(x)

    print('[F] Satz auf fremden Koordinaten, Namensgeschwister anderswo')
    treffer = []
    for (la, lo), g in pos.items():
        if len(g) < 2:
            continue
        for x in g:
            fremd = [y for y in g if y is not x and y['current'] == x['current']
                     and not verwandt(x, y)]
            gesch = [y for y in byk[x['key']] if y is not x
                     and (y['lat'], y['lon']) != (la, lo)]
            if fremd and gesch:
                rel = min(curve_diff(x, y)[1] for y in fremd)
                treffer.append((rel, x, min(fremd, key=lambda y: -curve_diff(x, y)[1]),
                                min(gesch, key=lambda y: curve_diff(x, y)[1])))
    for rel, x, f, s in sorted(treffer, key=lambda t: -t[0]):
        print(f'    {x["name"][:46]:46} {x["lat"]:8.4f} {x["lon"]:9.4f}  '
              f'{x["file"].split("/")[-1][:26]}')
        print(f'        sitzt auf {f["name"][:44]:44} Kurve {rel*100:.0f}% anders')
        print(f'        Geschwister {s["name"][:42]:42} {km(x, s):6.0f} km weg, '
              f'Kurve {curve_diff(x, s)[1]*100:.0f}% anders')
    print(f'    {len(treffer)} Faelle\n')

    print('[G] gleicher Name, eine Koordinate um glatte Grad versetzt')
    n = 0
    for _k, g in byk.items():
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                a, b = g[i], g[j]
                if a['current'] != b['current']:
                    continue
                dla, dlo = a['lat'] - b['lat'], a['lon'] - b['lon']
                if abs(dlo) < 1e-9 and glatt(dla):
                    art = f'Breite um {glatt(dla)} Grad'
                elif abs(dla) < 1e-9 and glatt(dlo):
                    art = f'Laenge um {glatt(dlo)} Grad'
                else:
                    continue
                n += 1
                ga, gb = gridsize_deg(a['lat'], a['lon']), gridsize_deg(b['lat'], b['lon'])
                grob = ' -- ACHTUNG: beide auf grobem Raster, also eher zweimal ' \
                       'gerundet als Ziffernfehler' if ga >= 0.5 and gb >= 0.5 else ''
                print(f'    {art}, Kurve {curve_diff(a, b)[1]*100:.0f}% anders{grob}')
                for x, gr in ((a, ga), (b, gb)):
                    print(f'        {x["name"][:44]:44} {x["lat"]:9.4f} {x["lon"]:10.4f}'
                          f'  Raster {gr:.4f}  {x["file"].split("/")[-1][:24]}')
    print(f'    {n} Faelle')


if __name__ == '__main__':
    main()
