#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht Ortsnamen fuer die NP203-Stromstationen -- und urteilt nicht.

NP203 Part IIIa fuehrt keine Ortsnamen: die Tabelle hat Nummer, Position,
Richtungen und Konstanten, und der einzige Text sind kursive
Gebietsueberschriften. Deshalb heissen die Saetze "Off Borneo Current"
oder "Philippine Islands Current".

Die Einleitung zu Part IIIa sagt aber: "The numbers used in Part IIIa are
the first three digits of the port numbers in the same area." Damit
verweist das Buch auf seine eigenen benannten Haefen. Als Namensquelle
taugt das nicht -- gemessen liegt der naechste Hafen mit passendem
Praefix im Median 24.8 km entfernt, im schlimmsten Fall 1410 km. Als
GEGENPROBE taugt es: liegt der Buchhafen neben dem gefundenen Feature,
passt der Vorschlag zum Gebiet, liegt er 120 km weg, ist Vorsicht
geboten.

Gefragt wird OpenStreetMap ueber Overpass, kachelweise statt punktweise.
Das ist die Lehre aus py/lage_gewaesser.py: eine Abfrage kostet rund
fuenfzig Sekunden, unabhaengig davon, wie gross sie ist -- 70 Stationen
liegen in etwa zwanzig Gradfeldern. Antworten werden zwischengespeichert,
ein zweiter Lauf fragt nicht noch einmal.

Gesucht werden benannte Seegebietsmerkmale: Meerengen, Buchten, Kaps,
Riffe, Untiefen, Inseln, Kanaele und Seezeichen (OpenSeaMap ist kein
eigener Dienst, sondern OSM mit seamark-Tags -- dieselbe Abfrage).

Geschrieben wird nur eine Vorschlagsliste. Uebernommen wird nichts:
eine Stromstation steht auf offener See, und der naechste benannte Punkt
kann eine Sandbank in der falschen Bucht sein. Das entscheidet ein
Mensch.

Usage: python3 py/stroemungsnamen_overpass.py [--umkreis 15]
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, active_files, MERIDIAN, ROOT, km  # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
CACHE = os.path.join(HELP, 'overpass_cache')
ZIEL = os.path.join(HELP, 'stroemungsnamen_vorschlag.csv')
SPIEGEL = ['https://overpass-api.de/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter']
AGENT = ('xtide-harmonics-pflege/1.0 (Abgleich von Stromstationen mit OSM; '
         'Kontakt ueber github.com/oliver-k73)')
PAUSE = 5.0
UMKREIS = 15.0

ABFRAGE = """[out:json][timeout:180];
(
  nwr["name"]["natural"~"^(strait|bay|cape|reef|shoal|peninsula|channel)$"]({bbox});
  nwr["name"]["place"~"^(island|islet|archipelago)$"]({bbox});
  nwr["name"]["waterway"="channel"]({bbox});
  nwr["name"]["seamark:type"]({bbox});
);
out center tags;"""


def kopfdaten():
    """-> {(Datei, Zeile): {Kommentarfeld: Wert}} fuer die NP203-Dateien."""
    out = {}
    for path in active_files():
        if 'np203' not in path:
            continue
        lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
        for k, l in enumerate(lines):
            if (not l or l.startswith('#') or k + 1 >= len(lines)
                    or not MERIDIAN.match(lines[k + 1])):
                continue
            d, j = {}, k - 1
            while j >= 0 and lines[j].startswith('#'):
                m = re.match(r'#\s*([a-z0-9_]+):\s*(.+?)\s*$', lines[j])
                if m:
                    d[m.group(1)] = m.group(2)
                j -= 1
            out[(path, k + 1)] = d
    return out


def kachel(lat, lon):
    return int(math.floor(lat)), int(math.floor(lon))


def hole(kz, km_):
    """-> Overpass-Antwort fuer ein Gradfeld, aus dem Puffer oder vom Netz."""
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'{kz}_{km_}.json'.replace('-', 'm'))
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    # Etwas Rand, damit ein Merkmal knapp ausserhalb der Kachel mitkommt.
    bbox = f'{kz - 0.3},{km_ - 0.3},{kz + 1.3},{km_ + 1.3}'
    daten = urllib.parse.urlencode({'data': ABFRAGE.format(bbox=bbox)}).encode()
    letzter = None
    for url in SPIEGEL:
        try:
            req = urllib.request.Request(url, data=daten,
                                         headers={'User-Agent': AGENT})
            with urllib.request.urlopen(req, timeout=240) as f:
                antwort = json.load(f)
            json.dump(antwort, open(p, 'w', encoding='utf-8'))
            time.sleep(PAUSE)
            return antwort
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            letzter = e
            time.sleep(PAUSE)
    print(f'   Kachel {kz}/{km_}: {letzter}', file=sys.stderr)
    return {'elements': []}


def merkmale(antwort):
    """-> [(Name, Art, lat, lon)] aus einer Overpass-Antwort."""
    out = []
    for e in antwort.get('elements', []):
        t = e.get('tags', {})
        name = t.get('name')
        if not name:
            continue
        art = (t.get('natural') or t.get('place') or t.get('waterway')
               or t.get('seamark:type') or '?')
        la = e.get('lat', (e.get('center') or {}).get('lat'))
        lo = e.get('lon', (e.get('center') or {}).get('lon'))
        if la is None or lo is None:
            continue
        out.append((name, art, float(la), float(lo)))
    return out


def main(argv):
    import csv
    umkreis = float(argv[argv.index('--umkreis') + 1]) if '--umkreis' in argv else UMKREIS
    info = kopfdaten()
    recs = {(r['file'], r['line']): r for r in load_records()}
    strom = [(v['np203_no'], recs[k]) for k, v in info.items()
             if 'np203_no' in v and k in recs and recs[k]['lat'] is not None]
    haefen = [(v['att_number'], recs[k]) for k, v in info.items()
              if 'att_number' in v and k in recs and recs[k]['lat'] is not None]
    kacheln = sorted({kachel(s['lat'], s['lon']) for _n, s in strom})
    print(f'{len(strom)} Stromstationen in {len(kacheln)} Gradfeldern', file=sys.stderr)

    gefunden = {}
    for i, (kz, km_) in enumerate(kacheln, 1):
        gefunden[(kz, km_)] = merkmale(hole(kz, km_))
        print(f'  {i:3}/{len(kacheln)}  {kz:+03d}/{km_:+04d}  '
              f'{len(gefunden[(kz, km_)]):5} benannte Merkmale', file=sys.stderr)

    zeilen = []
    for no, s in sorted(strom, key=lambda t: t[0]):
        nahe = []
        for dz in (-1, 0, 1):
            for dm in (-1, 0, 1):
                for name, art, la, lo in gefunden.get(
                        (kachel(s['lat'], s['lon'])[0] + dz,
                         kachel(s['lat'], s['lon'])[1] + dm), []):
                    d = km(s, {'lat': la, 'lon': lo})
                    if d <= umkreis:
                        nahe.append((d, name, art))
        nahe.sort()
        p = re.match(r'(\d{3})', no).group(1)
        hk = [(km(s, h), n, h) for n, h in haefen if n.startswith(p)]
        hd, hn, hr = min(hk) if hk else (None, '', None)
        for d, name, art in nahe[:3]:
            zeilen.append(dict(
                np203_no=no, name_alt=s['name'], lat=f'{s["lat"]:.4f}',
                lon=f'{s["lon"]:.4f}', kandidat=name, art=art, km=f'{d:.2f}',
                buchhafen=hr['name'] if hr else '', buchhafen_nr=hn,
                buchhafen_km=f'{hd:.1f}' if hd is not None else '',
                name_neu=''))
        if not nahe:
            zeilen.append(dict(
                np203_no=no, name_alt=s['name'], lat=f'{s["lat"]:.4f}',
                lon=f'{s["lon"]:.4f}', kandidat='', art='', km='',
                buchhafen=hr['name'] if hr else '', buchhafen_nr=hn,
                buchhafen_km=f'{hd:.1f}' if hd is not None else '',
                name_neu=''))
    with open(ZIEL, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader()
        w.writerows(zeilen)
    ohne = sum(1 for z in zeilen if not z['kandidat'])
    print(f'\n{len(zeilen)} Zeilen fuer {len(strom)} Stationen, '
          f'{ohne} ohne Fund im Umkreis von {umkreis:.0f} km')
    print(f'-> {ZIEL}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
