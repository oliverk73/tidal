#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zweite Stufe zu lage_ausreisser: fragt OpenStreetMap nach Gewaessern.

lage_ausreisser misst den Abstand zum Ozean nach der GLOBE-Landmaske.
Das findet zwar die falschen Positionen, meldet aber ebenso die
Tidefluesse mit: Hudson bis Albany, St. Lorenz bis Montreal, Gambia bis
Fatoto, Columbia River. Die Landmaske kennt keine Fluesse.

Hier wird darum fuer jede gemeldete Position bei der Overpass-API
nachgefragt, ob in ihrer Naehe eine Kuestenlinie oder ein BENANNTER
Fluss liegt. Auf den Namen kommt es an: an der alten
Matamoros-Position liegen acht Wasserflaechen, aber alle unbenannt --
die Resacas, alte Flussschlingen mitten in der Stadt. Ein Pegel steht
nicht an einem Tuempel.

    Matamoros (alte Position)  8 Flaechen, keine benannt, keine Kueste
    Matamoros (Playa Lauro Villar)              Kuestenlinie
    Albany                                      "Hudson River"
    Fatoto, Gambia                              "Gambie"

Die Antworten werden zwischengespeichert; ein zweiter Lauf fragt nicht
noch einmal. Zwischen den Anfragen wird gewartet -- Overpass ist ein
Gemeinschaftsdienst, und tausend Anfragen im Sekundentakt waeren
schlechtes Benehmen.

Auch diese Stufe urteilt nicht. Sie sortiert die Liste so, dass oben
steht, was am ehesten falsch ist.

Usage: python3 py/lage_gewaesser.py [--radius 1000] [--max N]
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'harmonics/help/lage_ausreisser.csv')
ZIEL = os.path.join(ROOT, 'harmonics/help/lage_gewaesser.csv')
PUFFER = os.path.join(ROOT, 'tide_tables/osm_gewaesser')
# Der Spiegel statt der Hauptinstanz, und mit reichlich Pause. Ein
# erster Lauf mit zwei Sekunden Abstand gegen overpass-api.de wurde nach
# rund vierzig Anfragen gesperrt -- nicht mit 429, sondern mit
# abgewiesener Verbindung. Overpass ist ein Gemeinschaftsdienst; neunhundert
# Abfragen darf man dort stellen, aber nicht in zehn Minuten.
API = os.environ.get('OVERPASS_API', 'https://overpass.kumi.systems/api/interpreter')
UA = 'tidal-harmonics-position-check/1.0 (github.com/oliverk73/tidal)'
PAUSE = 4.0
RADIUS = 1000


def _frage(lat, lon, r):
    return (f'[out:json][timeout:30];('
            f'way(around:{r},{lat},{lon})["natural"="coastline"];'
            f'way(around:{r},{lat},{lon})["waterway"~"^(river|canal|tidal_channel)$"];'
            f'relation(around:{r},{lat},{lon})["waterway"~"^(river|canal)$"];'
            f'way(around:{r},{lat},{lon})["natural"="water"];'
            f'relation(around:{r},{lat},{lon})["natural"="water"];'
            f');out tags 40;')


def gewaesser(lat, lon, r=RADIUS):
    """-> dict mit kueste, fluesse (benannt), flaechen, flaechen_benannt."""
    os.makedirs(PUFFER, exist_ok=True)
    p = os.path.join(PUFFER, f'{lat:.4f}_{lon:.4f}_{r}.json')
    if os.path.exists(p):
        d = json.load(open(p, encoding='utf-8'))
    else:
        req = urllib.request.Request(
            API, data=urllib.parse.urlencode({'data': _frage(lat, lon, r)}).encode(),
            headers={'User-Agent': UA})
        for versuch in range(4):
            try:
                with urllib.request.urlopen(req, timeout=90) as fh:
                    d = json.load(fh)
                break
            except (urllib.error.HTTPError, urllib.error.URLError,
                    TimeoutError, json.JSONDecodeError):
                if versuch == 3:
                    raise
                # Overpass antwortet unter Last mit 429 oder 504; dann
                # laenger warten statt haerter nachfragen.
                # Nach einem Fehlschlag deutlich laenger warten: wer
                # gesperrt wurde, kommt durch schnelleres Nachfragen
                # nicht wieder herein.
                time.sleep(30 * (versuch + 1))
        json.dump(d, open(p, 'w', encoding='utf-8'))
        time.sleep(PAUSE)
    kueste, fluesse, flaechen, benannt = 0, [], 0, []
    for e in d.get('elements', []):
        t = e.get('tags', {})
        name = t.get('name')
        if t.get('natural') == 'coastline':
            kueste += 1
        elif t.get('waterway'):
            if name:
                fluesse.append(name)
        elif t.get('natural') == 'water':
            flaechen += 1
            if name:
                benannt.append(name)
    return {'kueste': kueste, 'fluesse': sorted(set(fluesse)),
            'flaechen': flaechen, 'flaechen_benannt': sorted(set(benannt))}


def main(argv):
    g = lambda n, v: (int(argv[argv.index(n) + 1]) if n in argv else v)
    r, grenze = g('--radius', RADIUS), g('--max', 0)
    if not os.path.exists(QUELLE):
        print(f'{QUELLE} fehlt -- erst py/lage_ausreisser.py --csv laufen lassen')
        return 1
    zeilen = list(csv.DictReader(open(QUELLE, encoding='utf-8')))
    # Je Position nur einmal fragen.
    nach_ort = {}
    for z in zeilen:
        nach_ort.setdefault((z['lat'], z['lon']), []).append(z)
    orte = sorted(nach_ort.items(), key=lambda x: -float(x[1][0]['ozean_km'])
                  if x[1][0]['ozean_km'] != 'inf' else -1e9)
    if grenze:
        orte = orte[:grenze]
    print(f'{len(orte)} Positionen zu pruefen', file=sys.stderr)
    aus = []
    for i, ((la, lo), zs) in enumerate(orte, 1):
        try:
            w = gewaesser(float(la), float(lo), r)
        except Exception as e:
            print(f'  {zs[0]["name"][:40]}: {type(e).__name__}', file=sys.stderr)
            continue
        # Ein Pegel gehoert an die Kueste oder an einen benannten Fluss.
        verdacht = not w['kueste'] and not w['fluesse'] and not w['flaechen_benannt']
        aus.append((verdacht, zs[0]['ozean_km'], zs, w))
        if i % 25 == 0:
            print(f'  {i}/{len(orte)}', file=sys.stderr, flush=True)
    verdaechtig = [x for x in aus if x[0]]
    print(f'\n{len(verdaechtig)} von {len(aus)} Positionen ohne Kueste und ohne '
          f'benanntes Gewaesser im Umkreis von {r} m\n')
    for _v, ozean, zs, w in sorted(verdaechtig, key=lambda x: -len(x[2])):
        z = zs[0]
        print(f'  Ozean {ozean:>4} km, {w["flaechen"]} unbenannte Flaechen  '
              f'{z["name"][:42]:42} {z["lat"]:>9} {z["lon"]:>10}  '
              f'{", ".join(q["datei"][:22] for q in zs[:2])}')
    with open(ZIEL, 'w', newline='', encoding='utf-8') as fh:
        w_ = csv.writer(fh)
        w_.writerow(['verdacht', 'ozean_km', 'datei', 'name', 'lat', 'lon',
                     'kueste', 'fluesse', 'flaechen', 'flaechen_benannt'])
        for v, ozean, zs, w in sorted(aus, key=lambda x: (not x[0], x[1])):
            for z in zs:
                w_.writerow([int(v), ozean, z['datei'], z['name'], z['lat'], z['lon'],
                             w['kueste'], '; '.join(w['fluesse']), w['flaechen'],
                             '; '.join(w['flaechen_benannt'])])
    print(f'\n-> {ZIEL}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
