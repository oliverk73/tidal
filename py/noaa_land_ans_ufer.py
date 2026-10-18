#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ungepruefte NOAA-Buchsaetze, die an Land stehen, ans Ufer holen (Oliver 18.10.2026).

Anlass "Red Cliff Bay, Shark Bay": NOAA-Koordinaten sind oft auf die Minute gerundet und
landen an Land. Am Ufer findet py/noaa_nachbar_abgleich.py dann das passende Duplikat.

Ungeprueft wie dort: NOAA-Satz (amtt/eutt/cptt/pacif/carib/censam), den positions_locked.csv
nicht als 'manual' fuehrt. Land/Wasser nach den OSM-Landpolygonen (py/osm_land.py).

  an Land, Kueste <= MAX_KM:  auf den naechsten Uferpunkt und UEBER_KM weiter ins Wasser
  an Land, Kueste >  MAX_KM:  nur Liste (Tidefluss oder grob falsch -- Memory positionen-an-land)

Jede Verschiebung steht in harmonics/help/noaa_auto_verschoben.csv; py/build_tide_station_markers.py
zeigt diese Saetze in einer eigenen Markergruppe, bis Oliver sie geprueft hat.

Usage: venv/bin/python py/noaa_land_ans_ufer.py [--schreiben]
"""
import csv
import math
import os
import sys
from datetime import date

from shapely.geometry import Point
from shapely.ops import nearest_points, unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import osm_land                                                    # noqa: E402
import sicher_schreiben                                            # noqa: E402
from health_check import load_records                              # noqa: E402
from noaa_nachbar_abgleich import ungeprueft                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTE = os.path.join(ROOT, 'harmonics/help/noaa_auto_verschoben.csv')
MAX_KM = 3.0
UEBER_KM = (0.1, 0.2, 0.4)


def ufer(L, la, lo):
    """-> (lat, lon) knapp im Wasser am naechsten Uferpunkt, oder None."""
    p = Point(lo, la)
    box = p.buffer(MAX_KM * 1.5 / 111.2 / max(0.2, math.cos(math.radians(la))))
    teile = L._treffer(box)
    if not teile:
        return None
    q = nearest_points(p, unary_union(teile).boundary)[1]
    dy, dx = (q.y - la) * 111.2, (q.x - lo) * 111.2 * math.cos(math.radians(la))
    n = math.hypot(dx, dy)
    if n == 0:
        return None
    for u in UEBER_KM:
        ny = q.y + dy / n * u / 111.2
        nx = q.x + dx / n * u / (111.2 * math.cos(math.radians(la)))
        if not L.ist_land(ny, nx):
            return round(ny, 4), round(nx, 4)
    return None


def main(argv):
    prov = {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/positions_locked.csv'), encoding='utf-8')):
        prov[(r['fingerprint'], r['name'])] = r['provenance']
    offen = ungeprueft([r for r in load_records() if not r['current'] and r['lat'] is not None], prov)
    L = osm_land.Land([(r['lat'], r['lon']) for r in offen])
    zeilen, schieben = [], {}
    for r in offen:
        if not L.ist_land(r['lat'], r['lon']):
            continue
        kk = L.kueste_km(r['lat'], r['lon'])
        neu = ufer(L, r['lat'], r['lon']) if kk <= MAX_KM else None
        z = dict(datei=r['file'], name=r['name'], alt_lat=r['lat'], alt_lon=r['lon'], kueste_km=round(kk, 2),
                 neu_lat=neu[0] if neu else '', neu_lon=neu[1] if neu else '',
                 aktion='verschoben' if neu else 'liste', datum=date.today().strftime('%Y%m%d'))
        zeilen.append(z)
        if neu:
            schieben.setdefault(r['file'], []).append(z)
    print('%d ungepruefte NOAA-Saetze, %d an Land: %d verschoben, %d nur Liste' % (
        len(offen), len(zeilen), sum(len(v) for v in schieben.values()), sum(1 for z in zeilen if z['aktion'] == 'liste')))
    if '--schreiben' not in argv:
        return
    for f, zs in schieben.items():
        T = open(os.path.join(ROOT, f), encoding='iso-8859-1').read().split('\n')
        for z in zs:
            i = T.index(z['name'])
            j = i - 1
            while not T[j].startswith('# !latitude'):
                j -= 1
            T[j] = '# !latitude: %.4f' % z['neu_lat']
            assert T[j - 1].startswith('# !longitude')
            T[j - 1] = '# !longitude: %.4f' % z['neu_lon']
            T.insert(i, '# note: %s an Land, automatisch ans Ufer (vorher %.4f/%.4f, Kueste %.2f km) (Oliver).'
                     % (date.today().isoformat(), z['alt_lat'], z['alt_lon'], z['kueste_km']))
        sicher_schreiben.schreiben(os.path.join(ROOT, f), '\n'.join(T))
    alt = []
    if os.path.exists(LISTE):
        alt = list(csv.DictReader(open(LISTE, encoding='utf-8')))
    with open(LISTE, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(alt + zeilen)
    print('->', os.path.relpath(LISTE, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
