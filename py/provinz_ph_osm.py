#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provinz der philippinischen Saetze aus den OSM-Verwaltungsgrenzen.

py/provinz_ergaenzen.py beschriftet Natural-Earth-Polygone nach den Namen,
die schon im Bestand stehen -- auf den Philippinen hat das die alten
NOAA-Fehler weitergetragen ("Dapitan, Negros Oriental", "Moalboal, Bohol",
"Jolo, Tawi-Tawi"). Nominatim (reverse, zoom 10) liefert die Provinz als
'state', auch fuer Punkte vor der Kueste; an acht bekannten Orten richtig
(Dapitan, Moalboal, Jolo, Legazpi, Currimao, Bolinao, Mapun, Corregidor).
Kreisfreie Staedte haben in OSM keine Provinz, nur die Region -> STADT.

Vorschlag je Satz: fehlende Provinz einfuegen, falsche ersetzen. Als
Provinz gilt das vorletzte Namensglied nur, wenn es eine bekannte Provinz
ist ("Tilik, Lubang" -> Lubang ist die Insel, bleibt stehen).

Zwischenspeicher: harmonics/help/provinz_ph_osm_cache.json (1 Anfrage/s).
Ausgabe: harmonics/help/provinz_ph_osm.csv (nur Vorschlag)

Usage: python3 py/provinz_ph_osm.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT, load_records                       # noqa: E402

CACHE = os.path.join(ROOT, 'harmonics/help/provinz_ph_osm_cache.json')
AUS = os.path.join(ROOT, 'harmonics/help/provinz_ph_osm.csv')
PROVINZEN = {
    'Abra', 'Agusan del Norte', 'Agusan del Sur', 'Aklan', 'Albay', 'Antique', 'Apayao', 'Aurora',
    'Basilan', 'Bataan', 'Batanes', 'Batangas', 'Benguet', 'Biliran', 'Bohol', 'Bukidnon', 'Bulacan',
    'Cagayan', 'Camarines Norte', 'Camarines Sur', 'Camiguin', 'Capiz', 'Catanduanes', 'Cavite', 'Cebu',
    'Cotabato', 'Davao de Oro', 'Davao del Norte', 'Davao del Sur', 'Davao Occidental', 'Davao Oriental',
    'Dinagat Islands', 'Eastern Samar', 'Guimaras', 'Ifugao', 'Ilocos Norte', 'Ilocos Sur', 'Iloilo',
    'Isabela', 'Kalinga', 'La Union', 'Laguna', 'Lanao del Norte', 'Lanao del Sur', 'Leyte', 'Maguindanao',
    'Maguindanao del Norte', 'Maguindanao del Sur', 'Marinduque', 'Masbate', 'Misamis Occidental',
    'Misamis Oriental', 'Mountain Province', 'Negros Occidental', 'Negros Oriental', 'Northern Samar',
    'Nueva Ecija', 'Nueva Vizcaya', 'Occidental Mindoro', 'Oriental Mindoro', 'Palawan', 'Pampanga',
    'Pangasinan', 'Quezon', 'Quirino', 'Rizal', 'Romblon', 'Samar', 'Sarangani', 'Siquijor', 'Sorsogon',
    'South Cotabato', 'Southern Leyte', 'Sultan Kudarat', 'Sulu', 'Surigao del Norte', 'Surigao del Sur',
    'Tarlac', 'Tawi-Tawi', 'Zambales', 'Zamboanga del Norte', 'Zamboanga del Sur', 'Zamboanga Sibugay',
    'Metro Manila'}
# kreisfreie Staedte (OSM: nur Region) -> geografische Provinz
STADT = {'Puerto Princesa': 'Palawan', 'Iloilo City': 'Iloilo', 'Davao City': 'Davao del Sur',
         'Cebu City': 'Cebu', 'Mandaue': 'Cebu', 'Lapu-Lapu': 'Cebu', 'Olongapo': 'Zambales',
         'Zamboanga City': 'Zamboanga del Sur', 'Cagayan de Oro': 'Misamis Oriental',
         'Bacolod': 'Negros Occidental', 'Iligan': 'Lanao del Norte', 'General Santos': 'South Cotabato',
         'Butuan': 'Agusan del Norte', 'Tacloban': 'Leyte', 'Ormoc': 'Leyte', 'Lucena': 'Quezon',
         'Naga': 'Camarines Sur', 'Isabela City': 'Basilan', 'Cotabato City': 'Maguindanao',
         'Angeles': 'Pampanga', 'Baguio': 'Benguet', 'Legazpi': 'Albay', 'Surigao': 'Surigao del Norte'}


def osm(lat, lon, cache):
    k = f'{lat:.4f},{lon:.4f}'
    if k not in cache:
        url = (f'https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json'
               f'&zoom=10&addressdetails=1')
        try:
            cache[k] = json.load(urllib.request.urlopen(urllib.request.Request(
                url, headers={'User-Agent': 'tide-lookup/1.0'}), timeout=60)).get('address', {})
        except Exception as e:
            print(f'  {k}: {e}', file=sys.stderr)
            return None
        time.sleep(1.1)
    a = cache[k]
    p = a.get('state') or a.get('province')
    if not p:
        stadt = a.get('city') or a.get('town') or ''
        p = STADT.get(stadt) or ('Metro Manila' if a.get('region') == 'Metro Manila' else None)
    return p if p in PROVINZEN else None


def vorschlag(name, prov):
    teile = [t.strip() for t in name.split(',')]
    if len(teile) >= 3 and teile[-2] in PROVINZEN:
        if teile[-2] == prov:
            return None
        teile[-2] = prov
    else:
        teile.insert(-1, prov)
    return ', '.join(teile)


def main():
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    R = [r for r in load_records() if r['lat'] is not None and r['name'].endswith('Philippines')]
    zeilen, offen = [], []
    for i, r in enumerate(R):
        p = osm(r['lat'], r['lon'], cache)
        if i % 50 == 0:
            json.dump(cache, open(CACHE, 'w'), ensure_ascii=False)
            print(f'  {i}/{len(R)}', file=sys.stderr)
        if not p:
            offen.append(r)
            continue
        neu = vorschlag(r['name'], p)
        if neu:
            alt = [t.strip() for t in r['name'].split(',')]
            zeilen.append(dict(datei=os.path.basename(r['file']), alt=r['name'], neu=neu, provinz=p,
                               art='ersetzt' if len(alt) >= 3 and alt[-2] in PROVINZEN else 'ergaenzt',
                               lat=f"{r['lat']:.4f}", lon=f"{r['lon']:.4f}"))
    json.dump(cache, open(CACHE, 'w'), ensure_ascii=False)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'alt', 'neu', 'provinz', 'art', 'lat', 'lon'])
        w.writeheader()
        w.writerows(zeilen)
    from collections import Counter
    print(f'-> {os.path.relpath(AUS, ROOT)}: {len(R)} Saetze, {len(zeilen)} Aenderungen',
          dict(Counter(z['art'] for z in zeilen)), f'| ohne OSM-Provinz: {len(offen)}')
    for r in offen:
        print(f"   offen: {r['name']} ({r['lat']:.3f},{r['lon']:.3f})")


if __name__ == '__main__':
    sys.exit(main())
