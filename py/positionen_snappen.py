#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schlaegt fuer gerundete Pegelpositionen die Lage am Wasser vor.

Rund 640 Saetze stehen auf ganzen Bogenminuten -- das ist der Buchwert
aus ATT und NOAA, und er ist bis zu 0.93 km von der Wahrheit entfernt.
Wo der Pegel wirklich steht, weiss das Buch nicht; wir wissen aber, dass
er am Wasser steht.

Gesucht wird deshalb der naechste Punkt einer Kuestenlinie oder eines
BENANNTEN Flusses -- und zwar nur INNERHALB der Rundungszelle. Das ist
der Kern: die Wahrheit liegt in dieser Zelle, alles ausserhalb waere
geraten. Findet sich dort kein Wasser, bleibt die Position stehen und
der Fall kommt auf die Frageliste.

Auf den Namen des Flusses kommt es an, wie in py/lage_gewaesser.py: an
einer alten Matamoros-Position liegen acht Wasserflaechen, alle
unbenannt -- Altarme mitten in der Stadt. Ein Pegel steht nicht an einem
Tuempel.

Gefragt wird kachelweise (Gradfeld) und nicht punktweise; eine Abfrage
kostet zehn bis fuenfzehn Sekunden, unabhaengig davon, wie viele Punkte
darin liegen. Gespeichert werden nur die Linienzuege, nicht die
Rohantwort.

Geschrieben wird eine Vorschlagsliste. Uebernommen wird nichts: eine
verschobene Position ist eine Behauptung ueber die Welt, und die trifft
ein Mensch.

Usage: python3 py/positionen_snappen.py [--km 1.0]
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                         # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
CACHE = os.path.join(HELP, 'kuesten_cache')
ZIEL = os.path.join(HELP, 'positionen_snap_vorschlag.csv')
SPIEGEL = ['https://overpass-api.de/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter']
AGENT = ('xtide-harmonics-pflege/1.0 (Kuestenlinie fuer gerundete '
         'Pegelpositionen; Kontakt ueber github.com/oliver-k73)')
PAUSE = 4.0
ABFRAGE = """[out:json][timeout:180];
(way["natural"="coastline"]({bbox});
 way["waterway"="river"]["name"]({bbox});
 way["natural"="water"]["name"]({bbox}););
out geom;"""


def gerundet(r):
    la, lo = r['lat'] * 60, r['lon'] * 60
    return abs(la - round(la)) < 1e-6 and abs(lo - round(lo)) < 1e-6


def hole(kz, km_):
    """-> [[(lon, lat), ...], ...] Linienzuege des Gradfeldes."""
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'{kz}_{km_}.json'.replace('-', 'm'))
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    bbox = f'{kz - 0.2},{km_ - 0.2},{kz + 1.2},{km_ + 1.2}'
    daten = urllib.parse.urlencode({'data': ABFRAGE.format(bbox=bbox)}).encode()
    for url in SPIEGEL:
        try:
            req = urllib.request.Request(url, data=daten,
                                         headers={'User-Agent': AGENT})
            with urllib.request.urlopen(req, timeout=300) as f:
                antwort = json.load(f)
            linien = [[[round(g['lon'], 5), round(g['lat'], 5)]
                       for g in e.get('geometry', [])]
                      for e in antwort.get('elements', [])
                      if len(e.get('geometry', [])) > 1]
            json.dump(linien, open(p, 'w', encoding='utf-8'))
            time.sleep(PAUSE)
            return linien
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f'   Kachel {kz}/{km_}: {e}', file=sys.stderr)
            time.sleep(PAUSE)
    return []


def naechster(lon, lat, linien, grenze_km):
    """-> (Abstand km, lon, lat) des naechsten Linienpunktes."""
    cos = max(0.05, math.cos(math.radians(lat)))
    grad = grenze_km / 111.0
    best = (float('inf'), None, None)
    for linie in linien:
        for x, y in linie:
            if abs(y - lat) > grad or abs(x - lon) * cos > grad:
                continue
            d = math.hypot(y - lat, (x - lon) * cos) * 111.0
            if d < best[0]:
                best = (d, x, y)
    return best if best[0] <= grenze_km else (None, None, None)


def main(argv):
    grenze = float(argv[argv.index('--km') + 1]) if '--km' in argv else 1.0
    recs = [r for r in load_records() if r['lat'] is not None and gerundet(r)]
    kacheln = sorted({(int(math.floor(r['lat'])), int(math.floor(r['lon'])))
                      for r in recs})
    print(f'{len(recs)} gerundete Positionen in {len(kacheln)} Gradfeldern',
          file=sys.stderr)
    linien = {}
    for i, (kz, km_) in enumerate(kacheln, 1):
        linien[(kz, km_)] = hole(kz, km_)
        print(f'  {i:4}/{len(kacheln)}  {kz:+03d}/{km_:+04d}  '
              f'{len(linien[(kz, km_)]):5} Linien', file=sys.stderr, flush=True)

    zeilen = []
    for r in recs:
        kz, km_ = int(math.floor(r['lat'])), int(math.floor(r['lon']))
        menge = []
        for dz in (-1, 0, 1):
            for dm in (-1, 0, 1):
                menge += linien.get((kz + dz, km_ + dm), [])
        d, x, y = naechster(r['lon'], r['lat'], menge, grenze)
        zeilen.append(dict(
            name=r['name'], datei=os.path.basename(r['file']),
            lat=f'{r["lat"]:.4f}', lon=f'{r["lon"]:.4f}',
            neu_lat=f'{y:.5f}' if y is not None else '',
            neu_lon=f'{x:.5f}' if x is not None else '',
            km=f'{d:.3f}' if d is not None else '', uebernehmen=''))
    with open(ZIEL, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader()
        w.writerows(zeilen)
    mit = sum(1 for z in zeilen if z['km'])
    print(f'\n{len(zeilen)} gerundete Positionen, {mit} mit Wasser in der '
          f'Rundungszelle ({grenze:.2f} km)')
    print(f'-> {ZIEL}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
