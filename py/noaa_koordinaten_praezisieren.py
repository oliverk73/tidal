#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Koordinaten der NOAA-Buchsaetze in Alaska und Hawaii praezisieren (Oliver 27.10.2026).

Das NOAA-Buch nennt die Positionen auf die ganze Bogenminute (~1,8 km). Zwei Quellen sind genauer:

1. NOAA CO-OPS Metadata API (stations.json?type=tidepredictions): in Alaska/Hawaii meist auf 0,1'.
   Nur genommen, wenn die API-Koordinate wirklich feiner als die ganze Minute ist, der Name passt
   (gemeinsames Wort ausser Gattungswoertern) und sie mindestens 0,2 km von unserer abweicht.
   Geeicht an Olivers 20 US-Korrekturen seit 18.10.: 5x naeher an Olivers Position, 1x gleich, nie
   schlechter (San Simeon 0,94 -> 0,11 km, Ano Nuevo Island 0,90 -> 0,13 km).
2. GNIS (USGS DomesticNames): nur Kap/Spitze (Klasse Cape) und Flussmuendung ("X River entrance",
   Klasse Stream = Muendungspunkt), gleicher Bundesstaat, hoechstens 5 km. Buchten, Haefen und Inseln
   gibt GNIS als Mittelpunkt -- dort war es bei der Eichung schlechter als das Buch.

Ausgenommen: Stroemungen; Suedost-Alaska bis einschliesslich Copper Harbor (55,21 N) ist von Oliver geprueft;
Saetze, die Oliver verschoben hat (Commit mit 'Oliver'), und Saetze, die nicht mehr auf der ganzen
Buchminute stehen (schon bewusst gesetzt, z. B. Port Beauclerc).
Jede Verschiebung kommt nach harmonics/help/noaa_auto_verschoben.csv (Kartengruppe "NOAA verschoben
(pruefen)"), bis Oliver sie durchgesehen hat.

Usage: venv/bin/python py/noaa_koordinaten_praezisieren.py <coops_stations.json> <DomesticNames_National.txt> [--schreiben]
"""
import csv
import json
import math
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sicher_schreiben                                            # noqa: E402
from health_check import load_records                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTE = os.path.join(ROOT, 'harmonics/help/noaa_auto_verschoben.csv')
STAATEN = ('Alaska', 'Hawaii')
GEPRUEFT_SUEDOST = (55.22, -136.0)                                 # Alaska: lat <= 55.22 und lon > -136 = Oliver (mit Copper Harbor)
GATTUNG = set('island islands bay point river harbor harbour entrance creek inlet cove sound the of and north south '
              'east west new fort pt mouth channel side cape lagoon arm passage strait head port anchorage'.split())


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'\bft\.?\b', 'fort', s)
    s = re.sub(r'\bpt\.?\b', 'point', s)
    s = re.sub(r'\bst\.?\b', 'saint', s)
    return re.sub(r'[^a-z0-9 ]', ' ', s.replace('harbour', 'harbor')).split()


def km(a, b, c, d):
    return math.hypot((c - a) * 111.2, (d - b) * 111.2 * math.cos(math.radians(a)))


def raster(x):
    """0 = ganze Minute, 1 = 0,1 Minute, 2 = feiner."""
    m = abs(float(x)) * 60
    if abs(m - round(m)) < 0.004:
        return 0
    return 1 if abs(m * 10 - round(m * 10)) < 0.04 else 2


def api_treffer(r, api):
    tk = set(t for t in norm(r['name'].split(',')[0]) if len(t) > 2)
    best = None
    for a in api:
        d = km(r['lat'], r['lon'], a['lat'], a['lng'])
        if d > 10:
            continue
        ta = set(t for t in norm(a['name']) if len(t) > 2)
        if not (tk & ta) - GATTUNG:
            continue
        s = len(tk & ta) / len(tk | ta)
        if best is None or (s, -d) > (best[0], -best[1]):
            best = (s, d, a)
    return best


def gnis_laden(pfad):
    idx = defaultdict(list)
    for z in csv.reader(open(pfad, encoding='utf-8-sig'), delimiter='|'):
        if z[3] not in STAATEN or z[2] not in ('Cape', 'Stream'):
            continue
        try:
            la, lo = float(z[15]), float(z[16])
        except ValueError:
            continue
        if la:
            idx[' '.join(norm(z[1]))].append((z[1], z[2], z[3], la, lo))
    return idx


def gnis_treffer(r, idx):
    kopf = ' '.join(norm(r['name'].split(',')[0]))
    if re.search(r'\b(entrance|mouth)\b', kopf) and re.search(r'\b(river|creek|slough)\b', kopf):
        klasse = 'Stream'
    elif re.search(r'\b(point|cape|head|hook|spit)\b', kopf):
        klasse = 'Cape'
    else:
        return None
    teile = [re.sub(r'\s*\(.*\)', '', r['name'].split(',')[0])] + re.findall(r'\(([^)]*)\)', r['name'].split(',')[0])
    best = None
    for t in teile:
        n = ' '.join(norm(t))
        for k in {n, re.sub(r'\s+', ' ', re.sub(r'\b(entrance|mouth)\b', ' ', n)).strip()}:
            for g in idx.get(k, []):
                d = km(r['lat'], r['lon'], g[3], g[4])
                if g[1] == klasse and g[2] == r['name'].split(', ')[-1] and d <= 5 and (best is None or d < best[0]):
                    best = (d, g)
    return best


def von_oliver_verschoben(dateien):
    """Fingerabdruecke, deren Position in einem Commit mit 'Oliver' im Betreff geaendert wurde."""
    import subprocess
    import positions_lock as PL
    out = set()
    for f in dateien:
        log = subprocess.run(['git', 'log', '--format=%h %s', '--', f], cwd=ROOT, capture_output=True, text=True).stdout
        for c in [z.split()[0] for z in log.split('\n') if 'Oliver' in z]:
            try:
                a, b = (PL.parse(subprocess.run(['git', 'show', '%s:%s' % (v, f)], cwd=ROOT, capture_output=True,
                                                check=True).stdout.decode('iso-8859-1')) for v in (c + '^', c))
            except subprocess.CalledProcessError:
                continue
            for fp, lb in b.items():
                la = a.get(fp)
                if la and len(la) == len(lb) == 1 and la[0][1:3] != lb[0][1:3]:
                    out.add(fp)
    return out


def main(argv):
    api = json.load(open(argv[0]))['stations']
    idx = gnis_laden(argv[1])
    recs = [r for r in load_records() if '/noaa/' in r['file'] and not r['current'] and r['lat'] is not None
            and r['name'].split(', ')[-1] in STAATEN]
    oliver = von_oliver_verschoben(sorted({r['file'] for r in recs}))
    zeilen, schieben = [], defaultdict(list)
    for r in recs:
        if r['name'].endswith('Alaska') and r['lat'] <= GEPRUEFT_SUEDOST[0] and r['lon'] > GEPRUEFT_SUEDOST[1]:
            continue
        if r['fp'] in oliver:
            print('  (von Oliver verschoben, bleibt) %s' % r['name'])
            continue
        if max(raster(r['lat']), raster(r['lon'])) > 0:
            continue                                               # nicht mehr auf dem Buchraster: schon bewusst gesetzt
        neu = None
        a = api_treffer(r, api)
        if a and min(raster(a[2]['lat']), raster(a[2]['lng'])) >= 1 and a[1] >= 0.2:
            neu = (a[2]['lat'], a[2]['lng'], 'NOAA CO-OPS %s "%s"' % (a[2]['id'], a[2]['name']), a[1])
        else:
            g = gnis_treffer(r, idx)
            if g and g[0] >= 0.2:
                neu = (g[1][3], g[1][4], 'GNIS %s "%s"' % (g[1][1], g[1][0]), g[0])
        if not neu:
            continue
        z = dict(datei=r['file'], name=r['name'], alt_lat=r['lat'], alt_lon=r['lon'], kueste_km='',
                 neu_lat=round(neu[0], 4), neu_lon=round(neu[1], 4), aktion='verschoben',
                 datum=date.today().strftime('%Y%m%d'))
        zeilen.append(z)
        schieben[r['file']].append((z, neu[2], neu[3]))
        print('  %-50s %5.2f km  %s' % (r['name'][:50], neu[3], neu[2][:60]))
    print('%d Saetze in %s, %d verschoben (%d NOAA-API, %d GNIS)' % (
        len(recs), '/'.join(STAATEN), len(zeilen), sum(1 for v in schieben.values() for x in v if x[1].startswith('NOAA')),
        sum(1 for v in schieben.values() for x in v if x[1].startswith('GNIS'))))
    if '--schreiben' not in argv:
        return
    for f, zs in schieben.items():
        T = open(os.path.join(ROOT, f), encoding='iso-8859-1').read().split('\n')
        for z, quelle, d in zs:
            i = T.index(z['name'])
            j = i - 1
            while not T[j].startswith('# !latitude'):
                j -= 1
            T[j] = '# !latitude: %.4f' % z['neu_lat']
            assert T[j - 1].startswith('# !longitude')
            T[j - 1] = '# !longitude: %.4f' % z['neu_lon']
            note = '# note: %s Position nach %s (vorher %.4f/%.4f, %.2f km).' % (
                date.today().isoformat(), quelle, z['alt_lat'], z['alt_lon'], d)
            T.insert(i, note[:195])
        sicher_schreiben.schreiben(os.path.join(ROOT, f), '\n'.join(T))
    alt = list(csv.DictReader(open(LISTE, encoding='utf-8'))) if os.path.exists(LISTE) else []
    with open(LISTE, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(alt + zeilen)
    print('->', os.path.relpath(LISTE, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
