#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sammelt Positionsvorschlaege -- und schreibt nichts in die Daten.

Zwei Quellen:
  katalog   Die Kennungen des Datensatzes sind geprueft (py/id_validate.py),
            aber die Katalogposition weicht ab. Stimmen mehrere Verzeichnisse
            untereinander ueberein, ist das ein starker Hinweis.
  kanal_b   Zwei Datensaetze gleichen Namens mit gleicher Gezeitenkurve stehen
            weit auseinander; einer der beiden Orte ist falsch.

Jede Zeile traegt die Herkunft der heutigen Position aus
positions_locked.csv. "manual" heisst: von Hand gesetzt, der Vorschlag
widerspricht also einer bereits getroffenen Entscheidung und braucht
menschliche Pruefung. "source" heisst: unveraendert vom Lieferanten.

Usage: python3 py/positions_propose.py [--km 5]
"""
from __future__ import annotations

import collections
import csv
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, curve_diff                # noqa: E402
from id_match import read_tags                                       # noqa: E402
from id_validate import load_catalogues, norm_key, metres            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, 'harmonics/help/positions_locked.csv')
OUT = os.path.join(ROOT, 'harmonics/help/positions_proposed.csv')
TAGS = ('psmsl_id', 'uhslc_id', 'gloss_id', 'ssc_id', 'ioc_code',
        'ptwc_code', 'chs_id')


def gridsize_deg(lat, lon):
    """Schaetzt, auf welches Raster eine Koordinate gerundet ist.

    Verzeichnisse fuehren Positionen teils nur auf Bogenminuten oder gar
    halbe Grad genau. Ein solcher Wert ist groeber als eine von Hand
    gesetzte Position -- ihn zu uebernehmen waere ein Rueckschritt.
    """
    for g in (1.0, 0.5, 1 / 6, 0.1, 1 / 60, 0.01, 1 / 3600, 0.0001):
        if all(abs(v / g - round(v / g)) < 1e-6 for v in (lat, lon)):
            return g
    return 0.0


def main():
    thr = 5000.0
    if '--km' in sys.argv:
        thr = float(sys.argv[sys.argv.index('--km') + 1]) * 1000

    prov = {}
    if os.path.exists(LOCK):
        with open(LOCK, encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                prov[row['fingerprint']] = row['provenance']

    cat = load_catalogues()
    recs = load_records()
    read_tags(recs)
    tide = [r for r in recs if not r['current'] and r['lat'] is not None
            and r['lon'] is not None]

    rows = []

    # ---- Quelle katalog ------------------------------------------------
    for r in tide:
        hits = []
        for tag in TAGS:
            for raw in r['tags'].get(tag, []):
                for tok in re.split(r'[,;]\s*', raw):
                    v = norm_key(tag, tok)
                    h = cat.get((tag, v))
                    if h:
                        hits.append((metres(r['lat'], r['lon'], h[0], h[1]),
                                     tag, v, h))
        if not hits:
            continue
        far = [h for h in hits if h[0] > thr]
        if not far or any(h[0] <= thr for h in hits):
            # mindestens eine Kennung bestaetigt die heutige Position
            continue
        lats = [h[3][0] for h in far]
        lons = [h[3][1] for h in far]
        spread = max(metres(lats[0], lons[0], a, b) for a, b in zip(lats, lons))
        g = min(gridsize_deg(a, b) or 9 for a, b in zip(lats, lons))
        gm = g * 111000 if g < 9 else 0.0
        own = gridsize_deg(r['lat'], r['lon'])
        if gm and min(h[0] for h in far) < gm and (not own or own < g):
            hinweis = f'Katalog nur auf {g:.4g} Grad gerundet -- groeber als der eigene Wert'
        elif gm and min(h[0] for h in far) < 1.5 * gm:
            hinweis = f'Abstand in der Groessenordnung der Katalogrundung ({g:.4g} Grad)'
        else:
            hinweis = ''
        rows.append({
            'quelle': 'katalog',
            'fingerprint': r['fp'],
            'station': r['name'],
            'datei': r['file'],
            'lat': r['lat'], 'lon': r['lon'],
            'vorschlag_lat': f'{statistics.median(lats):.4f}',
            'vorschlag_lon': f'{statistics.median(lons):.4f}',
            'abstand_m': f'{min(h[0] for h in far):.0f}',
            'streuung_m': f'{spread:.0f}',
            'herkunft': prov.get(r['fp'], '?'),
            'hinweis': hinweis,
            'beleg': '; '.join(sorted({f'{h[1]} {h[2]} = {h[3][2][:24]}'
                                       for h in far}))[:180],
        })

    # ---- Quelle kanal_b ------------------------------------------------
    byname = collections.defaultdict(list)
    for i, r in enumerate(tide):
        if len(r['key']) >= 5:
            byname[r['key']].append(i)
    seen = set()
    for _k, idx in byname.items():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                r1, r2 = tide[idx[a]], tide[idx[b]]
                d = km(r1, r2)
                if d <= 25:
                    continue
                if not (r1['toks'] <= r2['toks'] or r2['toks'] <= r1['toks']):
                    continue
                _x, rel = curve_diff(r1, r2)
                if rel > 0.10:
                    continue
                key = tuple(sorted((r1['fp'], r2['fp'])))
                if key in seen:
                    continue
                seen.add(key)
                same = (r1['name'].split(',')[-1].strip()
                        == r2['name'].split(',')[-1].strip())
                for x, y in ((r1, r2), (r2, r1)):
                    rows.append({
                        'quelle': 'kanal_b',
                        'fingerprint': x['fp'],
                        'station': x['name'],
                        'datei': x['file'],
                        'lat': x['lat'], 'lon': x['lon'],
                        'vorschlag_lat': f'{y["lat"]:.4f}',
                        'vorschlag_lon': f'{y["lon"]:.4f}',
                        'abstand_m': f'{d*1000:.0f}',
                        'streuung_m': '',
                        'herkunft': prov.get(x['fp'], '?'),
                        'hinweis': '',
                        'beleg': (f'gleicher Name und Kurve ({rel*100:.0f} %) wie '
                                  f'{y["name"]} [{y["file"].split("/")[-1]}]'
                                  + ('' if same else ' -- verschiedene Laender, '
                                     'moeglicherweise nur Namensgleichheit')),
                    })

    rows.sort(key=lambda r: (r['quelle'], -float(r['abstand_m'])))
    with open(OUT, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f'{len(rows)} Vorschlaege -> {OUT}\n')
    for q in ('katalog', 'kanal_b'):
        sub = [r for r in rows if r['quelle'] == q]
        c = collections.Counter(r['herkunft'] for r in sub)
        print(f'{q:8}  {len(sub):4d}   ' + '  '.join(f'{v} {k}' for k, v in c.most_common()))
    print('\nKatalogvorschlaege ueber 20 km, nach Herkunft der heutigen Position:')
    for r in [x for x in rows if x['quelle'] == 'katalog'][:18]:
        print(f'   {float(r["abstand_m"])/1000:7.1f} km  [{r["herkunft"]:6}]  '
              f'{r["station"][:36]:36} {float(r["lat"]):8.3f} {float(r["lon"]):9.3f}'
              f'  ->  {r["vorschlag_lat"]:>9} {r["vorschlag_lon"]:>10}')
        if r['hinweis']:
            print(f'   {"":11}          ACHTUNG: {r["hinweis"]}')
        print(f'   {"":11}          {r["beleg"][:96]}')


if __name__ == '__main__':
    main()
