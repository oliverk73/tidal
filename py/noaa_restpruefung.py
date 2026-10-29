#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueflist fuer die noch ungeprueften NOAA-Buchsaetze (29.10.2026).

Ausgangspunkt: py/noaa_nachbar_abgleich.ungeprueft() (Stand 18.10.2026). Davon ab:
  - USA ohne Alaska/Hawaii (Oliver 27.10.: geprueft)
  - Hongkong (Oliver 29.10.: geprueft)
  - Saetze der Gruppe "NOAA verschoben" (noaa_auto_verschoben.csv, aktion geprueft)
  - Saetze, deren Position sich seit dem 18.10. geaendert hat (Oliver oder geprueft
    verschobene Automatik)
  - Saetze, deren Name in einem Oliver-Commit seit dem 18.10. gesetzt wurde (Umbenennung
    ohne Verschiebung, z. B. Islote Los Negritos 9e427d1)

Fuer den Rest drei Proben, keine aendert etwas:
  lage   an Land (OSM-Landpolygone) bzw. Kuestenabstand, Buchminute (ganze Bogenminute)
  name   Suchwort (vor Klammer/Komma) in GeoNames bis 25 km (umfeld.tsv)? sonst naechster Ort
  tide   naechster gepruefter Nachbar: Zeit (M2-Phase) und Hub (M2) gegen die Toleranz
         20 min + 1 min/km bzw. Grundrauschen (noaa-guete-probelauf, p90 je Abstand)
Punkte: Land 3, Kueste >3 km 1, Name unbekannt 2, Zeit ueber Toleranz 2, Hub ueber Toleranz 1.

Schreibt harmonics/help/noaa_restpruefung_<datum>.csv (sortiert, Auffaelligste zuerst).
Usage: venv/bin/python py/noaa_restpruefung.py
"""
from __future__ import annotations

import bisect
import cmath
import csv
import math
import os
import re
import sys
import unicodedata
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402
from noaa_nachbar_abgleich import ungeprueft                       # noqa: E402
import osm_land                                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
US_STAATEN = {'Alabama', 'California', 'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Louisiana', 'Maine',
              'Maryland', 'Massachusetts', 'Mississippi', 'New Hampshire', 'New Jersey', 'New York',
              'North Carolina', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'Texas', 'Virginia',
              'Washington', 'District of Columbia'}
RAUSCHEN = [(1, 0.155), (3, 0.189), (6, 0.214), (12, 0.32), (25, 0.479)]   # p90 Hubabweichung je Abstand


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]', ' ', s).split()


def suchwort(name):
    return name.split(',')[0].split('(')[0].strip()


def buchminute(x):
    return abs(x * 60 - round(x * 60)) < 0.01


def geonames(saetze):
    """-> {id(satz): (treffer, naechster Ort, km)}"""
    zellen = {}
    for r in saetze:
        zellen.setdefault((int(r['lat'] * 4), int(r['lon'] * 4)), []).append(r)
    aus = {id(r): [False, '', 99.0] for r in saetze}
    worte = {id(r): [w for w in norm(suchwort(r['name'])) if len(w) > 2 and w not in
                     ('point', 'island', 'bay', 'harbor', 'harbour', 'port', 'cape', 'entrance', 'river',
                      'isla', 'puerto', 'punta', 'bahia', 'rio', 'ile', 'pointe', 'the')] for r in saetze}
    for z in open(os.path.join(ROOT, 'tide_tables/catalogues/geonames/umfeld.tsv'), encoding='utf-8'):
        f = z.rstrip('\n').split('\t')
        try:
            la, lo = float(f[4]), float(f[5])
        except (ValueError, IndexError):
            continue
        ci, cj = int(la * 4), int(lo * 4)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for r in zellen.get((ci + di, cj + dj), ()):
                    d = km(r, {'lat': la, 'lon': lo})
                    if d > 25:
                        continue
                    a = aus[id(r)]
                    w = worte[id(r)]
                    if w and not a[0]:
                        namen = set(norm(f[1] + ' ' + f[2] + ' ' + f[3].replace(',', ' ')))
                        if all(x in namen for x in w):
                            a[0] = True
                    if f[6] == 'P' and d < a[2]:
                        a[1], a[2] = f[1], d
    return aus


def olivers_namen():
    """Namen, die Oliver seit dem 18.10. in den NOAA-Dateien gesetzt hat (Commits 'Oliver: ...')."""
    import subprocess
    log = subprocess.run(['git', '-C', ROOT, 'log', '--since=2026-10-18', '--grep=^Oliver', '-p', '--format=',
                          '--', 'harmonics/noaa/'], capture_output=True).stdout.decode('latin-1')
    return {z[1:].strip() for z in log.split('\n') if z.startswith('+') and not z.startswith(('++', '+#')) and ',' in z}


def main():
    recs = [r for r in load_records() if not r['current'] and r['lat'] is not None]
    offen = ungeprueft(recs)
    alt = {z['fingerprint']: z['name_morgen'] for z in csv.DictReader(open(os.path.join(HELP, 'noaa_ungeprueft_20261018.csv'), encoding='utf-8'))}
    ab = {z['name']: z for z in csv.DictReader(open(os.path.join(HELP, 'noaa_nachbar_abgleich_20261018.csv'), encoding='utf-8'))}
    gep = {z['name'] for z in csv.DictReader(open(os.path.join(HELP, 'noaa_auto_verschoben.csv'), encoding='utf-8'))
           if z['aktion'] == 'geprueft'}
    oliver = olivers_namen()
    rest = []
    for r in offen:
        teil = r['name'].split(', ')[-1]
        morgen = alt.get(r['fp'], '')
        z = ab.get(morgen)
        if teil in US_STAATEN or teil == 'Hong Kong' or r['name'] in gep or morgen in gep or r['name'] in oliver:
            continue
        if z and (abs(float(z['lat']) - r['lat']) > 0.0005 or abs(float(z['lon']) - r['lon']) > 0.0005):
            continue
        rest.append(r)
    ids = {id(r) for r in offen}
    nachbarn = sorted((r for r in recs if id(r) not in ids), key=lambda r: r['lat'])
    lats = [r['lat'] for r in nachbarn]
    L = osm_land.Land([(r['lat'], r['lon']) for r in rest])
    G = geonames(rest)
    out = []
    for r in rest:
        land = L.ist_land(r['lat'], r['lon'])
        kueste = L.kueste_km(r['lat'], r['lon'])
        treffer, ort, ort_km = G[id(r)]
        i, j = bisect.bisect_left(lats, r['lat'] - 0.5), bisect.bisect_right(lats, r['lat'] + 0.5)
        kand = sorted(((km(r, g), g) for g in nachbarn[i:j]), key=lambda x: x[0])
        d, g = kand[0] if kand else (None, None)
        dmin = hub = None
        zeit_auff = hub_auff = False
        if g is not None and abs(r['z']['M2']) > 0.05 and abs(g['z']['M2']) > 0.05:
            dmin = ((math.degrees(cmath.phase(r['z']['M2'] / g['z']['M2'])) + 180) % 360 - 180) / 28.984104 * 60
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
    ziel = os.path.join(HELP, 'noaa_restpruefung_%s.csv' % date.today().strftime('%Y%m%d'))
    with open(ziel, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print(len(offen), 'ungeprueft laut 18.10.,', len(rest), 'offen ->', os.path.relpath(ziel, ROOT))
    print('Punkte:', sorted(Counter(o['punkte'] for o in out).items(), reverse=True))


if __name__ == '__main__':
    main()
