#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueflist fuer ATT-Saetze (NP201-208), deren Name und Position nie angefasst wurden (30.10.2026).

Oliver 30.10.2026: Die ATT-Saetze sind vermutlich nicht zu 100 % geprueft. Wie bei den
NOAA-Buchsaetzen (py/noaa_restpruefung.py) bekommt er eine Kartengruppe mit den
auffaelligsten -- es wird nichts verschoben.

Auswahl: Gezeitensaetze aus harmonics/att/, in positions_locked.csv mit provenance
'source' (Name und Position wie beim ersten Einchecken), ohne Notiz mit 'Oliver'.
Proben und Punkte wie in noaa_restpruefung.py:
  lage   an Land (OSM, mehr als 0,3 km vom Ufer) 3, Kueste > 3 km 1
  name   Suchwort nicht in GeoNames bis 25 km 2
  tide   naechster Nachbar ausserhalb dieser Auswahl: Zeit ueber 20 min + 1 min/km 2,
         Hub ueber dem Grundrauschen 1
Schreibt harmonics/help/att_pruefung_<datum>.csv; Punkte >= 3 erscheinen auf der Karte
als Gruppe "ATT auffällig (prüfen)".
Usage: venv/bin/python py/att_pruefung.py
"""
from __future__ import annotations

import bisect
import cmath
import csv
import math
import os
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402
from noaa_restpruefung import geonames, buchminute, oliver_notiz, RAUSCHEN, HELP, ROOT  # noqa: E402
import osm_land                                                    # noqa: E402


def main():
    recs = [r for r in load_records() if not r['current'] and r['lat'] is not None]
    lock = {(z['file'], z['name']): z['provenance']
            for z in csv.DictReader(open(os.path.join(HELP, 'positions_locked.csv'), encoding='utf-8'))}
    zeilen = {}
    rest = []
    for r in recs:
        rel = 'harmonics/' + r['file'].split('harmonics/', 1)[-1]
        if '/att/' not in rel or 'M2' not in r['z']:
            continue
        if lock.get((rel, r['name'])) != 'source' or oliver_notiz(r, zeilen):
            continue
        rest.append(r)
    ids = {id(r) for r in rest}
    nachbarn = sorted((r for r in recs if id(r) not in ids), key=lambda r: r['lat'])
    lats = [r['lat'] for r in nachbarn]
    L = osm_land.Land([(r['lat'], r['lon']) for r in rest])
    G = geonames(rest)
    out = []
    for r in rest:
        kueste = L.kueste_km(r['lat'], r['lon'])
        # Kai, Mole, Anleger: die OSM-Landflaeche reicht oft bis ans Wasser -- erst ab 0,3 km zaehlt "an Land"
        land = L.ist_land(r['lat'], r['lon']) and kueste is not None and kueste > 0.3
        treffer, ort, ort_km = G[id(r)]
        i, j = bisect.bisect_left(lats, r['lat'] - 0.5), bisect.bisect_right(lats, r['lat'] + 0.5)
        kand = sorted(((km(r, g), g) for g in nachbarn[i:j]), key=lambda x: x[0])
        d, g = kand[0] if kand else (None, None)
        dmin = hub = None
        zeit_auff = hub_auff = False
        if g is not None and abs(r['z']['M2']) > 0.05 and abs(g['z']['M2']) > 0.05:
            # z = a*exp(-i*g): Phase von z_r/z_g ist g_g - g_r; Minus, damit + = spaeter als der Nachbar
            dmin = -((math.degrees(cmath.phase(r['z']['M2'] / g['z']['M2'])) + 180) % 360 - 180) / 28.984104 * 60
            hub = abs(r['z']['M2']) / abs(g['z']['M2']) - 1
            zeit_auff = abs(dmin) > 20 + d
            hub_auff = d <= 25 and abs(hub) > next(p for k, p in RAUSCHEN if d <= k)
        punkte = (3 if land else 0) + (1 if not land and kueste and kueste > 3 else 0) + (0 if treffer else 2) \
            + (2 if zeit_auff else 0) + (1 if hub_auff else 0)
        gruende = [x for x, b in [('an Land', land), (('%.1f km' % kueste if kueste < 10 else '>= 10 km') + ' vor der Kueste' if kueste else '', not land and kueste and kueste > 3),
                                  ('Name nicht in GeoNames', not treffer),
                                  ('Zeit %+.0f min' % (dmin or 0), zeit_auff), ('Hub %+.0f %%' % (100 * (hub or 0)), hub_auff)] if b]
        out.append(dict(punkte=punkte, gruende='; '.join(gruende), datei=os.path.basename(r['file']), name=r['name'],
                        lat=r['lat'], lon=r['lon'], buchminute=int(buchminute(r['lat']) and buchminute(r['lon'])),
                        land=int(bool(land)), kueste_km=round(kueste, 2) if kueste is not None else '',
                        name_geonames=int(treffer), naechster_ort=ort, ort_km=round(ort_km, 1) if ort else '',
                        nachbar=g['name'] if g else '', nachbar_km=round(d, 1) if d is not None else '',
                        dzeit_min=round(dmin) if dmin is not None else '', dhub_proz=round(100 * hub) if hub is not None else ''))
    out.sort(key=lambda o: (-o['punkte'], o['name']))
    ziel = os.path.join(HELP, 'att_pruefung_%s.csv' % date.today().strftime('%Y%m%d'))
    with open(ziel, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(len(rest), 'ATT-Saetze unberuehrt ->', os.path.relpath(ziel, ROOT))
    print('Punkte:', sorted(Counter(o['punkte'] for o in out).items(), reverse=True))


if __name__ == '__main__':
    main()
