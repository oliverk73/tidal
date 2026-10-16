#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laedt die amtlichen Jahresvorhersagen (Kentern/Maxima) der NOAA-Nebenstationen fuer Stroeme.

Oliver 16.10.2026: Die Strom-Nebenstationen der USA fehlten im Bestand. Von 1704
NOAA-Nebenstationen (Typ S der Schnittstelle) lagen nur 118 naeher als 300 m an
einer Stromstation des Bestands; die Bezugsstationen (Typ H) sind ueber den
DWF-Bestand fast alle da. Typ W ("weak and variable") hat keine Vorhersage.

Holt fuer jede fehlende Nebenstation die Ereignisse 2026 (interval=MAX_SLACK, GMT)
nach tide_tables/noaa_nebenstroeme/<id>.json. Vorhandene Dateien werden uebersprungen.

Usage: venv/bin/python py/download_noaa_nebenstroeme.py [--max N]
"""
import collections
import json
import math
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'tide_tables/noaa_nebenstroeme')
LISTE = os.path.join(ZIEL, 'stations.json')
MD = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=currentpredictions&units=english'
DG = ('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=currents_predictions&station=%s'
      '&begin_date=20260101&end_date=20261231&interval=MAX_SLACK&time_zone=gmt&units=english&format=json'
      '&application=tidal_xtide')


def holen(url, versuche=3):
    for k in range(versuche):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if k == versuche - 1:
                raise
            time.sleep(5 * (k + 1))


def bestand_stroeme():
    d = json.load(open(os.path.join(ROOT, 'static/js/leaflet_markers_data.json')))
    g = collections.defaultdict(list)
    for s in d['stations']:
        if s[5] == 1:
            g[(round(s[1] * 20), round(s[2] * 20))].append((s[1], s[2]))
    return g


def km_naechste(g, la, lo):
    best = 9e9
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            for x, y in g.get((round(la * 20) + a, round(lo * 20) + b), ()):
                best = min(best, math.hypot((x - la) * 111.2, (y - lo) * 111.2 * math.cos(math.radians(la))))
    return best


def fehlende():
    os.makedirs(ZIEL, exist_ok=True)
    if not os.path.exists(LISTE):
        open(LISTE, 'wb').write(holen(MD))
    S = json.load(open(LISTE))['stations']
    g = bestand_stroeme()
    out, seen = [], set()
    for s in S:
        if s['type'] != 'S' or s['id'] in seen:
            continue
        seen.add(s['id'])
        if km_naechste(g, s['lat'], s['lng']) >= 0.3:
            out.append(s)
    return out


def main(argv):
    mx = int(argv[argv.index('--max') + 1]) if '--max' in argv else None
    F = fehlende()
    print(len(F), 'fehlende Nebenstationen', flush=True)
    n = 0
    for s in F[:mx]:
        p = os.path.join(ZIEL, s['id'] + '.json')
        if os.path.exists(p):
            continue
        try:
            raw = holen(DG % s['id'])
        except Exception as e:  # noqa: BLE001
            print('FEHLER', s['id'], e, flush=True)
            continue
        open(p, 'wb').write(raw)
        n += 1
        if n % 100 == 0:
            print(n, 'geladen', flush=True)
        time.sleep(0.5)
    print('fertig,', n, 'neu geladen', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
