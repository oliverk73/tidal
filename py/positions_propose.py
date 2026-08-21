#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sammelt Positionsvorschlaege -- und schreibt nichts in die Daten.

  katalog   Die Kennungen des Datensatzes sind geprueft (py/id_validate.py),
            aber die Katalogposition weicht ab. Stimmen mehrere Verzeichnisse
            untereinander ueberein, ist das ein starker Hinweis.
Positionsvorschlaege kommen ausschliesslich aus geprueften Verzeichnis-
eintraegen. Namensdubletten (gleicher Name, aehnliche Kurve, weit aus-
einander) sind KEINE Positionsvorschlaege -- sie gehen als Frageliste
nach harmonics/help/namensdubletten.csv.

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
DUBL = os.path.join(ROOT, 'harmonics/help/namensdubletten.csv')
TAGS = ('psmsl_id', 'uhslc_id', 'gloss_id', 'ssc_id', 'ioc_code',
        'ptwc_code', 'chs_id')


def gridsize_deg(lat, lon):
    """Schaetzt, auf welches Raster eine Koordinate gerundet ist.

    Verzeichnisse fuehren Positionen teils nur auf Bogenminuten oder gar
    halbe Grad genau. Ein solcher Wert ist groeber als eine von Hand
    gesetzte Position -- ihn zu uebernehmen waere ein Rueckschritt.
    """
    # Absolute Toleranz, keine relative: "21.8333" ist die abgeschnittene
    # Schreibweise von 21 Grad 50 Minuten (21.833333) und faellt bei einem
    # exakten Teilbarkeitstest durch.
    for g in (1.0, 0.5, 1 / 6, 0.1, 1 / 60, 0.01, 1 / 3600):
        if all(abs(v / g - round(v / g)) * g < 2e-4 for v in (lat, lon)):
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
        # Unabhaengig davon festhalten, wie genau das Ziel ueberhaupt ist:
        # ein Katalogwert auf 10 Bogenminuten sagt zwar, DASS die heutige
        # Position falsch ist, aber nur ungefaehr, wohin.
        if g < 9 and (not own or own < g):
            grob = f'Ziel nur auf {g:.4g} Grad genau (~{g*111:.1f} km)'
            hinweis = f'{hinweis}; {grob}' if hinweis else grob
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

    # ---- Kanal B: Namensdubletten, KEINE Positionsvorschlaege ----------
    # Zwei Datensaetze gleichen Namens mit aehnlicher Kurve weit auseinander
    # heissen nicht, dass einer an die Stelle des anderen gehoert. Es kann
    # derselbe Pegel doppelt sein -- oder schlicht derselbe Ortsname an zwei
    # Kuesten. Das entscheidet kein Skript. Hier steht nur die Gegenueber-
    # stellung, mit Land, Quelle, Datum und Konfidenz beider Seiten.
    def meta(r, k):
        return '; '.join(r['tags'].get(k, []))

    def land(r):
        # Nur ein ausdruecklicher country-Eintrag zaehlt. Der letzte Teil des
        # Namens ist kein Land -- "Florida (5)" und "Florida (4)" sind sonst
        # zwei verschiedene Staaten.
        return meta(r, 'country').strip()

    dubl = []
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
                l1, l2 = land(r1), land(r2)
                if l1 and l2 and l1.lower() != l2.lower():
                    urteil = f'verschiedene Laender ({l1} / {l2})'
                elif not (l1 and l2):
                    urteil = 'pruefen: Land nicht angegeben'
                elif meta(r1, 'source') != meta(r2, 'source'):
                    urteil = 'pruefen: gleiches Land, zwei Ableitungen'
                else:
                    urteil = 'pruefen: gleiches Land, gleiche Quelle'
                row = {'urteil': urteil, 'abstand_km': f'{d:.1f}',
                       'kurve_prozent': f'{rel*100:.0f}'}
                for tag, r in (('a', r1), ('b', r2)):
                    row.update({
                        f'station_{tag}': r['name'],
                        f'land_{tag}': land(r) or '(nicht angegeben)',
                        f'datei_{tag}': r['file'].split('/')[-1],
                        f'lat_{tag}': r['lat'], f'lon_{tag}': r['lon'],
                        f'herkunft_{tag}': prov.get(r['fp'], '?'),
                        f'quelle_{tag}': meta(r, 'source'),
                        f'datum_{tag}': meta(r, 'datum'),
                        f'konfidenz_{tag}': meta(r, 'confidence'),
                        f'fingerprint_{tag}': r['fp'],
                    })
                dubl.append(row)

    dubl.sort(key=lambda r: (r['urteil'], -float(r['abstand_km'])))
    if dubl:
        with open(DUBL, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(dubl[0].keys()))
            w.writeheader()
            w.writerows(dubl)

    rows.sort(key=lambda r: (r['quelle'], -float(r['abstand_m'])))
    with open(OUT, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    c = collections.Counter(r['herkunft'] for r in rows)
    print(f'{len(rows)} Positionsvorschlaege -> {OUT}')
    print('   Herkunft der heutigen Position: '
          + '  '.join(f'{v} {k}' for k, v in c.most_common()))
    cd = collections.Counter(r['urteil'] for r in dubl)
    print(f'\n{len(dubl)} Namensdubletten -> {DUBL}   (keine Positionsvorschlaege)')
    for k, v in cd.most_common():
        print(f'   {v:4d}  {k}')
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
