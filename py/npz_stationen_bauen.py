#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ordnet npz-Reihen ohne eigene Kennung einer Position zu.

Die meisten Reihen bringen Name und Position im Archiv mit. Die
deutschen PEGELONLINE-Reihen nicht: sie enthalten nur datetimes_utc und
levels_cm. Damit fielen alle 99 aus jeder Guetepruefung heraus -- und
das war ausgerechnet der Bestand, in dem die TICON-Saetze 40 Minuten zu
spaet liegen. Der Fehler blieb unsichtbar, weil die Reihe unlesbar war.

Zugeordnet wird ueber den Dateinamen. Der ist eine Kurzform des
Stationsnamens ohne Sonderzeichen, und zwar mit WEGGELASSENEN Umlauten:
"borkumsdstrand" ist Borkum (Suedstrand), nicht "borkumsudstrand".
Deshalb werden zwei Schluessel gebildet, einer mit umschriebenen und
einer mit getilgten Umlauten, und dazu die Namensformen mit und ohne
Klammerzusatz.

Wo mehrere Saetze passen, entscheidet die Mehrheitsposition: derselbe
Pegel steht oft in drei Dateien, und die stimmen ueberein. Bleibt es
uneindeutig, wird die Reihe nicht zugeordnet -- lieber eine Luecke als
eine falsche Reihe unter einem Pegelnamen.

Das Ergebnis liegt als npz_stationen.json neben den Reihen und wird von
py/messreihe_qualitaet.py gelesen. Es steht bewusst dort und nicht im
Baum: water_levels ist nicht versioniert, dieses Skript schon.

Usage: python3 py/npz_stationen_bauen.py [Ordner]     (Vorgabe: Germany)
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                       # noqa: E402

REIHEN = os.path.join(ROOT, 'water_levels')
KASTEN = {'Germany': (48, 56, 5, 15)}     # lat/lon-Fenster je Ordner


def schluessel(s):
    """-> zwei Formen: Umlaute umschrieben und Umlaute getilgt."""
    s = s.lower()
    a = b = s
    for x, y in (('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('ß', 'ss')):
        a = a.replace(x, y)
    for x in 'äöü':
        b = b.replace(x, '')
    b = b.replace('ß', 'ss')
    return {re.sub(r'[^a-z0-9]', '', a), re.sub(r'[^a-z0-9]', '', b)}


def formen(name):
    v = name.split(',')[0]
    out = {v, re.sub(r'\s*\(.*?\)', '', v), v.replace('(', '').replace(')', '')}
    m = re.match(r'^(.*?)\s*\((.*)\)\s*$', v)
    if m:
        out |= {m.group(1), m.group(2), f'{m.group(1)} {m.group(2)}',
                f'{m.group(2)} {m.group(1)}'}
    return out


def main(argv):
    ordner = argv[0] if argv else 'Germany'
    la1, la2, lo1, lo2 = KASTEN.get(ordner, (-90, 90, -180, 180))
    recs = [r for r in load_records()
            if r['lat'] is not None and not r['current']
            and la1 < r['lat'] < la2 and lo1 < r['lon'] < lo2]
    kand = collections.defaultdict(list)
    for r in recs:
        for f in formen(r['name']):
            for s in schluessel(f):
                kand[s].append(r)

    out, fehlt = {}, []
    pfade = sorted(glob.glob(os.path.join(REIHEN, ordner, '**', '*.npz'),
                             recursive=True))
    for pfad in pfade:
        n = os.path.basename(pfad)[:-4]
        treffer = [r for s in schluessel(n) for r in kand.get(s, [])]
        if not treffer:
            fehlt.append(n)
            continue
        c = collections.Counter((round(r['lat'], 4), round(r['lon'], 4))
                                for r in treffer)
        (la, lo), n_hits = c.most_common(1)[0]
        if len(c) > 1 and n_hits == c.most_common(2)[1][1]:
            fehlt.append(f'{n} (uneindeutig)')
            continue
        name = next(r['name'] for r in treffer
                    if round(r['lat'], 4) == la and round(r['lon'], 4) == lo)
        out[n] = dict(lat=la, lon=lo, name=name)

    ziel = os.path.join(REIHEN, ordner, 'npz_stationen.json')
    json.dump(out, open(ziel, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(out)} von {len(pfade)} Reihen zugeordnet -> '
          f'{os.path.relpath(ziel, ROOT)}')
    if fehlt:
        print(f'{len(fehlt)} ohne Zuordnung: ' + ', '.join(fehlt[:20]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
