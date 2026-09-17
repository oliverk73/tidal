#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bessere Namen und Positionen fuer die NMDIS-Saetze vorschlagen.

Die Namen im Bestand stammen aus der Umschrift des NMDIS-Portals
(py/fit_nmdis_stations.py display_name): NAOZHOUDAO(BEIGANG) ->
"Naozhoudao (Beigang)". Das ist Pinyin ohne Wortgrenzen; Google Maps
findet solche Namen meist nicht. Die Position liefert das Portal nur auf
ganze Bogenminuten (20 54 N 110 33 E), also bis 1,2 km unscharf.

Besser ist der chinesische Originalname: GeoNames fuehrt ihn samt
amtlicher Umschrift und genauer Lage. Dazu kommen aus OpenStreetMap die
Hafenanlagen im Umkreis -- ein Pegel steht am Kai, nicht im Ortszentrum.

Ausgelassen werden Saetze, die schon von Hand berichtigt wurden (Name
weicht vom erzeugten Portalnamen ab, Position nicht mehr auf der
Bogenminute, oder der Vermerk nennt eine Korrektur).

Ergebnis: harmonics/help/nmdis_namen_vorschlag.json  (Grundlage der
Vorschlagsseite, py/nmdis_seite_bauen.py)

Usage: python3 py/nmdis_namen_vorschlag.py [--ohne-osm] [--alle]
       --alle  auch schon bearbeitete Saetze (Oliver 17.09.2026: alle Namen
               noch einmal von Hand durchgehen)
"""
from __future__ import annotations

import collections
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_guete_probelauf as G                                    # noqa: E402
import pegel_dubletten                                              # noqa: E402
from health_check import ROOT, auf_raster, km, load_records         # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
AUS = os.path.join(HELP, 'nmdis_namen_vorschlag.json')
PLAN = os.path.join(ROOT, 'water_levels/CN_nmdis/batch_plan.json')
GEONAMES = os.path.join(ROOT, 'tide_tables/catalogues/geonames/umfeld.tsv')
OSM_CACHE = os.path.join(HELP, 'nmdis_osm_cache.json')
UA = 'oliver-weather-tides/1.0 (private tide station positions; oliver.k73@gmail.com)'
OVERPASS = 'https://overpass-api.de/api/interpreter'
HAND = re.compile(r'Oliver|HANDENTSCHEIDUNG|berichtigt|umbenannt|verschoben')

# Wie py/fit_nmdis_stations.display_name, nur ohne die Fix-Tabellen --
# gebraucht wird hier allein die Frage: steht noch der erzeugte Name da?
def portalname(enname):
    en = re.sub(r'〖[^〗]*〗', ' ', enname).strip()
    en = re.sub(r'\(', ' (', en)
    return re.sub(r'\s+', ' ', en).title().strip()


def geonames_index():
    """{chinesischer Name: [(Hauptname, lat, lon, Klasse, Code)]} fuer China."""
    idx = collections.defaultdict(list)
    with open(GEONAMES, encoding='utf-8') as fh:
        for line in fh:
            p = line.rstrip('\n').split('\t')
            if p[8] != 'CN':
                continue
            try:
                lat, lon = float(p[4]), float(p[5])
            except ValueError:
                continue
            for n in {p[1], p[2]} | {a for a in p[3].split(',') if a}:
                if any('一' <= c <= '鿿' for c in n):
                    idx[n].append((p[1], lat, lon, p[6], p[7]))
    return idx


def kandidaten(zh, lat, lon, idx, grenze=15.0):
    """GeoNames-Treffer zum chinesischen Namen, nach Abstand."""
    teile = [re.sub(r'[（(].*', '', zh)] + re.findall(r'[（(]([^）)]+)[）)]', zh)
    out, gesehen = [], set()
    for t in teile:
        for haupt, la, lo, kl, code in idx.get(t.strip(), ()):
            d = km({'lat': lat, 'lon': lon}, {'lat': la, 'lon': lo})
            if d > grenze or (haupt, round(la, 4), round(lo, 4)) in gesehen:
                continue
            gesehen.add((haupt, round(la, 4), round(lo, 4)))
            out.append(dict(name=haupt, teil=t.strip(), lat=round(la, 5), lon=round(lo, 5),
                            klasse=kl, code=code, km=round(d, 2)))
    return sorted(out, key=lambda x: x['km'])[:6]


def osm_haefen(stationen, cache):
    """Hafenanlagen je Station aus OSM; 10 Stationen je Anfrage, 2 s Pause."""
    offen = [s for s in stationen if s['code'] not in cache]
    for i in range(0, len(offen), 10):
        teil = offen[i:i + 10]
        bloecke = []
        for s in teil:
            d = 0.045                      # rund 5 km
            bb = f"{s['lat'] - d},{s['lon'] - d},{s['lat'] + d},{s['lon'] + d}"
            for t in ('node["man_made"="pier"]', 'way["man_made"="pier"]',
                      'way["harbour"]', 'node["harbour"]', 'way["man_made"="quay"]',
                      'node["amenity"="ferry_terminal"]', 'way["landuse"="harbour"]'):
                bloecke.append(f'{t}({bb});')
        q = '[out:json][timeout:120];(' + ''.join(bloecke) + ');out center tags;'
        try:
            req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({'data': q}).encode(),
                                         headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
        except Exception as e:
            print(f'  Overpass: {e}', file=sys.stderr)
            time.sleep(20)
            continue
        punkte = []
        for e in d['elements']:
            la = e.get('lat') or (e.get('center') or {}).get('lat')
            lo = e.get('lon') or (e.get('center') or {}).get('lon')
            if la is None:
                continue
            t = e.get('tags', {})
            punkte.append((la, lo, t.get('name') or t.get('name:zh') or '',
                           t.get('man_made') or t.get('harbour') or t.get('amenity') or t.get('landuse') or ''))
        for s in teil:
            cache[s['code']] = [dict(lat=round(la, 5), lon=round(lo, 5), name=n, art=a,
                                     km=round(km(s, {'lat': la, 'lon': lo}), 2))
                                for la, lo, n, a in punkte
                                if km(s, {'lat': la, 'lon': lo}) <= 5.0]
            cache[s['code']].sort(key=lambda x: x['km'])
        print(f'  OSM {i + len(teil)}/{len(offen)}', flush=True)
        json.dump(cache, open(OSM_CACHE, 'w'))
        time.sleep(2.0)
    return cache


def main(argv):
    plan = {s['code']: s for s in json.load(open(PLAN, encoding='utf-8'))}
    verm = pegel_dubletten.vermerke()
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    idx = geonames_index()
    pfad_ein = os.path.join(HELP, 'nmdis_eingetragen.json')
    eingetragen = json.load(open(pfad_ein)) if os.path.exists(pfad_ein) else {}
    print(f'{len(idx)} chinesische Namensschluessel', flush=True)

    faelle = []
    for r in recs:
        t = verm.get((r['file'], r['line']), '')
        m = re.search(r'# nmdis_site: (T\d+)', t)
        if not m:
            continue
        code = m.group(1)
        st = plan.get(code)
        if not st:
            continue
        erzeugt = portalname(st['enname'])
        heutiger = r['name'].split(',')[0].strip()
        schon = (HAND.search(t) or heutiger.lower() != erzeugt.lower()
                 or not auf_raster(r['lat'], r['lon']))
        if schon and '--alle' not in argv:
            continue
        faelle.append(dict(code=code, datei=os.path.basename(r['file']), name=r['name'],
                           lat=r['lat'], lon=r['lon'], zh=st['name'], portal=st['enname'],
                           provinz=st.get('province', ''), bearbeitet=bool(schon),
                           raster=auf_raster(r['lat'], r['lon']),
                           eingetragen=eingetragen.get(code, ''),
                           geonames=kandidaten(st['name'], r['lat'], r['lon'], idx)))
    print(f'{len(faelle)} NMDIS-Saetze' + ('' if '--alle' in argv else ' noch im Ursprungszustand'), flush=True)

    cache = json.load(open(OSM_CACHE)) if os.path.exists(OSM_CACHE) else {}
    if '--ohne-osm' not in argv:
        cache = osm_haefen(faelle, cache)
    for f in faelle:
        # Overpass liefert jeden Steg einzeln; acht namenlose "pier" derselben
        # Anlage sind keine acht Vorschlaege. Benanntes zuerst, Faehranleger vor
        # Kai vor Steg, und alles im selben 200-m-Feld gilt als ein Vorschlag.
        rang = {'ferry_terminal': 0, 'harbour': 1, 'quay': 2, 'pier': 3}
        gesehen, gefiltert = set(), []
        for o in sorted(cache.get(f['code'], []),
                        key=lambda o: (not o['name'], rang.get(o['art'], 4), o['km'])):
            schl = (round(o['lat'] * 500), round(o['lon'] * 500))
            if schl in gesehen:
                continue
            gesehen.add(schl)
            gefiltert.append(o)
        f['osm'] = gefiltert[:6]
        f['karte'] = G.kartenbild(f['lat'], f['lon'])

    json.dump(faelle, open(AUS, 'w', encoding='utf-8'), ensure_ascii=False)
    mit = sum(1 for f in faelle if f['geonames'])
    print(f'{mit} mit GeoNames-Vorschlag, {len(faelle) - mit} ohne -> {os.path.relpath(AUS, ROOT)}')


if __name__ == '__main__':
    main(sys.argv[1:])
