#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft die Stationskennungen der Datensaetze gegen die amtlichen Verzeichnisse.

Zweck ist ausdruecklich NICHT, Positionen zu uebernehmen, sondern die Kennungen
zu pruefen. Eine falsch vergebene Kennung ist gefaehrlicher als eine fehlende:
sie wuerde beim spaeteren Uebernehmen von Katalogpositionen eine Station quer
ueber die Erde verschieben, mit einer erstklassigen Quelle als Begruendung.
(Gefunden wurde genau das: "Mumbai (Colaba)" traegt die Kennungen von
Mumbles in Wales.)

Verzeichnisse in tide_tables/catalogues/, mit py/id_validate.py --laden zu holen:
  psmsl_rlr.txt, psmsl_met.txt   psmsl.org      Nummer; Breite; Laenge; Name
  uhslc_meta.geojson             uhslc.hawaii   uhslc_id, ssc_id, gloss_id
  chs_stations.json              api-iwls.dfo   code, latitude, longitude
  ioc_stations.json              ioc-sealevel   Code, Lat, Lon, GlossID

Usage: python3 py/id_validate.py [--laden] [--csv <datei>] [--km 5]
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, name_tokens                # noqa: E402
from id_match import read_tags                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.join(ROOT, 'tide_tables/catalogues')
SOURCES = {
    'psmsl_rlr.txt': 'https://psmsl.org/data/obtaining/rlr.annual.data/filelist.txt',
    'psmsl_met.txt': 'https://psmsl.org/data/obtaining/met.monthly.data/filelist.txt',
    'uhslc_meta.geojson': 'https://uhslc.soest.hawaii.edu/data/meta.geojson',
    'chs_stations.json': 'https://api-iwls.dfo-mpo.gc.ca/api/v1/stations',
    'ioc_stations.json': ('http://www.ioc-sealevelmonitoring.org/service.php'
                          '?query=stationlist&showall=all&output=json'),
}


def fetch():
    os.makedirs(CAT, exist_ok=True)
    for name, url in SOURCES.items():
        dest = os.path.join(CAT, name)
        subprocess.run(['curl', '-sS', '-L', '--max-time', '90', '-o', dest, url],
                       check=True)
        print(f'{os.path.getsize(dest):9d} B  {name}')


def load_catalogues():
    """-> {(art, kennung): (lat, lon, name)}"""
    cat = {}
    for fn in ('psmsl_rlr.txt', 'psmsl_met.txt'):
        p = os.path.join(CAT, fn)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8', errors='replace'):
            f = [x.strip() for x in line.split(';')]
            if len(f) < 4 or not f[0].isdigit():
                continue
            try:
                cat.setdefault(('psmsl_id', f[0]), (float(f[1]), float(f[2]), f[3]))
            except ValueError:
                pass
    p = os.path.join(CAT, 'uhslc_meta.geojson')
    if os.path.exists(p):
        for ft in json.load(open(p))['features']:
            pr = ft['properties']
            lon, lat = ft['geometry']['coordinates'][:2]
            nm = pr.get('name', '')
            if pr.get('uhslc_id') is not None:
                cat[('uhslc_id', str(pr['uhslc_id']))] = (lat, lon, nm)
            if pr.get('ssc_id'):
                cat[('ssc_id', str(pr['ssc_id']).lower())] = (lat, lon, nm)
            if pr.get('gloss_id') is not None:
                cat[('gloss_id', str(pr['gloss_id']))] = (lat, lon, nm)
    p = os.path.join(CAT, 'chs_stations.json')
    if os.path.exists(p):
        for st in json.load(open(p)):
            if st.get('code') and st.get('latitude') is not None:
                cat[('chs_id', str(st['code']).lower())] = (
                    st['latitude'], st['longitude'], st.get('officialName', ''))
    p = os.path.join(CAT, 'ioc_stations.json')
    if os.path.exists(p):
        for st in json.load(open(p)):
            code = (st.get('Code') or '').lower()
            lat, lon = st.get('Lat'), st.get('Lon')
            if not code or lat is None or lon is None:
                continue
            cat.setdefault(('ioc_code', code), (lat, lon, st.get('Location', '')))
            cat.setdefault(('ptwc_code', code), (lat, lon, st.get('Location', '')))
            if st.get('GlossID'):
                cat.setdefault(('gloss_id', str(st['GlossID'])),
                               (lat, lon, st.get('Location', '')))
    return {k: (la, wrap_lon(lo), nm) for k, (la, lo, nm) in cat.items()}


def wrap_lon(lon):
    """UHSLC fuehrt Laengen teils im Bereich 0..360 -- auf -180..180 bringen."""
    while lon > 180:
        lon -= 360
    while lon < -180:
        lon += 360
    return lon


def norm_key(tag, raw):
    v = raw.strip().lower()
    if tag == 'ssc_id':
        v = re.sub(r'^ssc[-_]', '', v)
    if tag in ('psmsl_id', 'uhslc_id', 'gloss_id'):
        v = re.sub(r'[^0-9]', '', v)
    return v


def metres(la1, lo1, la2, lo2):
    return 6371000 * math.hypot(math.radians(la1 - la2),
                                math.radians(lo1 - lo2) * math.cos(math.radians(la1)))


def main():
    if '--laden' in sys.argv:
        fetch()
    cat = load_catalogues()
    by_tag = collections.Counter(k[0] for k in cat)
    print('Verzeichniseintraege: ' + ', '.join(f'{v} {k}' for k, v in by_tag.most_common()))

    recs = load_records()
    read_tags(recs)
    tide = [r for r in recs if not r['current'] and r['lat'] is not None
            and r['lon'] is not None]

    thr = 5000.0
    if '--km' in sys.argv:
        thr = float(sys.argv[sys.argv.index('--km') + 1]) * 1000

    checked = ok = unknown = 0
    rows = []
    per_rec = collections.defaultdict(list)
    for r in tide:
        for tag in ('psmsl_id', 'uhslc_id', 'gloss_id', 'ssc_id', 'ioc_code',
                    'ptwc_code', 'chs_id'):
            for raw in r['tags'].get(tag, []):
                for tok in re.split(r'[,;]\s*', raw):
                    v = norm_key(tag, tok)
                    if not v:
                        continue
                    hit = cat.get((tag, v))
                    if hit is None:
                        unknown += 1
                        continue
                    checked += 1
                    d = metres(r['lat'], r['lon'], hit[0], hit[1])
                    per_rec[id(r)].append((d, tag, v, hit))
                    if d <= thr:
                        ok += 1
    print(f'\n{checked} Kennungen im Verzeichnis gefunden, {unknown} unbekannt')
    print(f'   Position stimmt (unter {thr/1000:.0f} km): {ok}  ({100*ok/max(1,checked):.1f} %)')

    # Jede einzelne Kennung wird bewertet, nicht nur der beste Treffer je
    # Datensatz: eine richtige Kennung darf eine falsche nicht zudecken.
    # (Fort-de-France traegt neben seiner eigenen uhslc_id 271 noch vier
    # Kennungen von Le Robert.)
    for r in tide:
        for d, tag, v, hit in sorted(per_rec.get(id(r), [])):
            if d <= thr:
                continue
            tk = {t for t in re.split(r'[^a-z0-9]+', hit[2].lower()) if len(t) > 2}
            shared = bool(tk & r['toks'])
            others = [h for h in per_rec[id(r)] if h[0] <= thr]
            # Entfernung entscheidet, nicht der Name: gleiche Ortsnamen kommen
            # weltweit mehrfach vor. "San Jose, Mindoro" mit ssc_id sanjs zeigt
            # auf San Jose in Guatemala -- Name passt, Kennung trotzdem falsch.
            if d > 50000:
                befund = 'Kennung falsch'
            elif shared:
                befund = 'Position pruefen (Name passt)'
            elif others:
                befund = 'Nachbarpegel -- Kennung pruefen'
            else:
                befund = 'Kennung pruefen (Name passt nicht)'
            rows.append([f'{d/1000:.1f}', tag, v, r['name'], r['lat'], r['lon'],
                         hit[2], f'{hit[0]:.4f}', f'{hit[1]:.4f}', befund,
                         r['file'], len(per_rec[id(r)])])
    rows.sort(key=lambda x: -float(x[0]))
    print(f'\n{len(rows)} einzelne Kennungen weichen von ihrer Katalogposition ab:')
    kinds = collections.Counter(x[9] for x in rows)
    for k, n in kinds.most_common():
        print(f'   {n:5d}  {k}')
    print()
    for x in rows[:25]:
        print(f'   {float(x[0]):8.1f} km  {x[1]:9} {x[2]:10} {x[3][:34]:34} '
              f'{float(x[4]):8.3f} {float(x[5]):9.3f}')
        print(f'   {"":11}  {"Katalog:":9} {"":10} {x[6][:34]:34} '
              f'{float(x[7]):8.3f} {float(x[8]):9.3f}   {x[9]}')
    if '--csv' in sys.argv:
        out = sys.argv[sys.argv.index('--csv') + 1]
        with open(out, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['abstand_km', 'kennung_art', 'kennung', 'station', 'lat', 'lon',
                        'katalog_name', 'katalog_lat', 'katalog_lon', 'befund',
                        'datei', 'n_kennungen'])
            w.writerows(rows)
        print(f'\nCSV -> {out}')


if __name__ == '__main__':
    main()
