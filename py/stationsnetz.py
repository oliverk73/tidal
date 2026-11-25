#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Amtliche Wetterstationen fuer die Karte: METAR-Flughaefen + WMO-SYNOP-Stationen (25.11.2026, Oliver).

Quellen (amtlich, frei):
  METAR  NOAA Aviation Weather Center, https://aviationweather.gov/data/cache/stations.cache.json.gz
         (siteType enthaelt 'METAR')
  SYNOP  WMO OSCAR/Surface, https://oscar.wmo.int/surface/rest/api/search/station?stationClass=synopLand
         (nur Stationen mit klassischer WMO-Nummer 0-20000-0-NNNNN, Status operational/partlyOperational/unknown)
Beide Listen werden ueber die WMO-Nummer verbunden (aviationweather.gov fuehrt sie bei ~3900 Flughaefen).

    venv/bin/python py/stationsnetz.py [--laden]
      -> static/wind_stations/stationsnetz.json
Spalten je Station: [lat, lon, name, icao, wmo, hoehe_m, art, wdqms]
  art: 1 = METAR, 2 = SYNOP, 3 = beides;  wdqms: WMO-Bewertung, ob Meldungen tatsaechlich ankommen (o/p/n/u)
"""
import gzip
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, 'quellen', 'thermik', 'stationsnetz')
AUS = os.path.join(ROOT, 'static', 'wind_stations', 'stationsnetz.json')
UA = {'User-Agent': 'weather-tides/1.0'}
URL_METAR = 'https://aviationweather.gov/data/cache/stations.cache.json.gz'
URL_SYNOP = 'https://oscar.wmo.int/surface/rest/api/search/station?stationClass=synopLand'
WDQMS = {'operational': 'o', 'partlyOperational': 'p', 'notOperational': 'n'}


def laden():
    os.makedirs(Q, exist_ok=True)
    for url, datei in ((URL_METAR, 'stations.cache.json.gz'), (URL_SYNOP, 'oscar_synop.json')):
        r = requests.get(url, headers=UA, timeout=600)
        r.raise_for_status()
        open(os.path.join(Q, datei), 'wb').write(r.content)
        print(datei, len(r.content) // 1024, 'KB')


def titel(s):
    """OSCAR-Namen stehen meist in Grossbuchstaben."""
    s = ' '.join((s or '').split())
    return s.title() if s.isupper() else s


def main(argv):
    if '--laden' in argv or not os.path.exists(os.path.join(Q, 'oscar_synop.json')):
        laden()
    stationen = {}
    nach_wmo = {}
    for x in json.load(gzip.open(os.path.join(Q, 'stations.cache.json.gz'))):
        if 'METAR' not in (x.get('siteType') or []) or x.get('lat') is None or abs(x['lat']) > 90 or abs(x['lon']) > 180:
            continue
        icao = x.get('icaoId') or x['id']
        s = [round(x['lat'], 4), round(x['lon'], 4), ' '.join((x.get('site') or icao).split()), icao,
             x.get('wmoId') or '', x.get('elev'), 1, '']
        stationen[('m', icao)] = s
        if x.get('wmoId'):
            nach_wmo[x['wmoId']] = s
    n_synop = 0
    for x in json.load(open(os.path.join(Q, 'oscar_synop.json')))['stationSearchResults']:
        if x.get('stationStatusCode') not in ('operational', 'partlyOperational', 'unknown') or x.get('latitude') is None:
            continue
        wmo = ''
        for w in x.get('wigosStationIdentifiers') or []:
            t = w['wigosStationIdentifier'].split('-')
            if len(t) == 4 and t[1] == '20000' and t[3].isdigit() and len(t[3]) == 5:
                wmo = t[3]
                if w.get('primary'):
                    break
        if not wmo:
            continue
        n_synop += 1
        bew = WDQMS.get(x.get('stationAssessedStatusCode'), 'u')
        if wmo in nach_wmo:                                   # Flughafen mit SYNOP: Position/Name vom AWC
            s = nach_wmo[wmo]
            s[6] = 3
            s[7] = bew
            continue
        stationen[('s', wmo)] = [round(x['latitude'], 4), round(x['longitude'], 4), titel(x['name']), '', wmo,
                                 x.get('elevation'), 2, bew]
    liste = sorted(stationen.values(), key=lambda s: (s[0], s[1]))
    for s in liste:
        if isinstance(s[5], float):
            s[5] = round(s[5])
    aus = dict(stand=__import__('datetime').date.today().isoformat(),
               quellen=['NOAA Aviation Weather Center (METAR sites)', 'WMO OSCAR/Surface (synoptic land stations)'],
               spalten=['lat', 'lon', 'name', 'icao', 'wmo', 'elev_m', 'type', 'wdqms'],
               stationen=liste)
    with open(AUS, 'w', encoding='utf-8') as f:
        json.dump(aus, f, ensure_ascii=False, separators=(',', ':'))
    art = [s[6] for s in liste]
    print('%d Stationen: %d nur METAR, %d nur SYNOP, %d beides (SYNOP gesamt %d) -> %s, %d KB'
          % (len(liste), art.count(1), art.count(2), art.count(3), n_synop, os.path.relpath(AUS, ROOT),
             os.path.getsize(AUS) // 1024))


if __name__ == '__main__':
    main(sys.argv[1:])
