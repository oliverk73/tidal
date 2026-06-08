#!/usr/bin/env python3
"""
Download gemessener Wasserstands-Zeitreihen von der Channel Coastal Observatory
(coastalmonitoring.org) API für die CCO-eigenen Pegel (numerische sensor-IDs).

API: /observations/tides/<END-TS>.geojson?key=..&sensor=<id>&duration=<stunden>
  - Timestamp ist das ENDE; duration (max 8760h = 1 Jahr/Single-Sensor) geht
    rückwärts. Werte = Wasserstand in m über Chart Datum, 10-min-Takt.
  - Dev-Key braucht passenden Referer-Header.

Cacht pro (sensor, jahr) als JSON unter water_levels/cco/.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import requests

KEY = '6cefd36d8e12a4dead4cf06d4dbd09c0'
REF = 'https://coastalmonitoring.org/realtimedata/'
BASE = 'https://coastalmonitoring.org/observations/tides'
HEAD = {'User-Agent': 'Mozilla/5.0', 'Referer': REF}
OUT = Path('/home/oliver/water_levels/cco')

# CCO-eigene Pegel (numerische ID): Name -> sensor-id
SENSORS = {
    'Arun Platform': 86, 'Lymington': 87, 'Brighton': 88, 'Herne Bay': 89,
    'Deal Pier': 90, 'Sandown Pier': 92, 'Swanage Pier': 93, 'West Bay Harbour': 95,
    'Port Isaac': 102, 'Second Severn Crossing': 106, 'Scarborough': 111,
    'Whitby Harbour': 112, 'Exmouth': 117, 'Penarth': 119, 'Hastings Pier': 126,
}


def fetch_year(sensor_id, year, force=False):
    """Jahr <year> (01-01 00:00 .. 12-31 23:50) holen via END-TS = (year+1)-01-01."""
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / f'sensor{sensor_id}_{year}.json'
    if cache.exists() and not force:
        return json.loads(cache.read_text())
    end = f'{year + 1}0101000000'
    url = f'{BASE}/{end}.geojson?key={KEY}&sensor={sensor_id}&duration=8760'
    r = requests.get(url, headers=HEAD, timeout=120)
    r.raise_for_status()
    d = r.json()
    feats = d.get('features', [])
    pts = []
    for f in feats:
        p = f['properties']
        v = p.get('value')
        ds = p.get('date')
        if v in (None, '') or not ds:
            continue
        pts.append({'date': ds, 'value': float(v), 'qc': p.get('QCflag')})
    cache.write_text(json.dumps(pts))
    return pts


def fetch_station(sensor_id, years):
    allpts = []
    for y in years:
        try:
            pts = fetch_year(sensor_id, y)
            allpts.extend(pts)
            print(f"  {y}: {len(pts)} Punkte")
        except Exception as e:
            print(f"  {y}: FEHLER {e}")
        time.sleep(0.5)
    return allpts


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'West Bay Harbour'
    yrs = [int(x) for x in sys.argv[2:]] or list(range(2015, 2025))
    sid = SENSORS[name]
    print(f"{name} (sensor {sid}), Jahre {yrs[0]}-{yrs[-1]}")
    pts = fetch_station(sid, yrs)
    print(f"Gesamt: {len(pts)} Punkte")
