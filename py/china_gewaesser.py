#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lage der chinesischen Saetze gegen OpenStreetMap-Gewaesser pruefen.

Die Portal- und Buchpositionen sind meist auf die Bogenminute gerundet
(bis ~1.5 km daneben); einzelne liegen grob falsch (Ruian 55 km draussen,
Hengmen 2.6 km an Land). py/lage_gewaesser.py fragte Overpass Punkt fuer
Punkt (50 s je Anfrage) -- hier kachelweise: je Gradfeld EINE Abfrage nach
Kuestenlinie, Fluessen/Kanaelen, Wasserflaechen und Anlegern, im Zwischen-
speicher tide_tables/osm_gewaesser/kacheln/ abgelegt. Danach laeuft alles
offline.

Je Satz:
  wasser_m    Abstand zum naechsten Wasser (Kuestenlinie, Flusslauf,
              Wasserflaechenrand)
  anleger_m   Abstand zum naechsten Anleger/Hafen (pier, harbour, ferry)
  vorschlag   bei 300 m < wasser_m <= 3 km: naechster Anleger im Umkreis
              von 1.5 km, sonst naechster Wasserpunkt
  klasse      ok | verschieben | verdacht (> 3 km vom Wasser)

Ausgabe: harmonics/help/china_gewaesser.csv (nur Vorschlag, aendert nichts)

Usage: python3 py/china_gewaesser.py [--nur-laden]
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT, load_records                       # noqa: E402

KACHELN = os.path.join(ROOT, 'tide_tables/osm_gewaesser/kacheln')
AUS = os.path.join(ROOT, 'harmonics/help/china_gewaesser.csv')
SERVER = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
          'https://overpass.private.coffee/api/interpreter']
ABFRAGE = """[out:json][timeout:300];
(way({s},{w},{n},{e})[natural=coastline];
 way({s},{w},{n},{e})[waterway~"^(river|canal|tidal_channel)$"];
 way({s},{w},{n},{e})[natural=water];
 relation({s},{w},{n},{e})[natural=water];
 way({s},{w},{n},{e})[waterway=riverbank];
 nwr({s},{w},{n},{e})[man_made~"^(pier|breakwater|groyne)$"];
 nwr({s},{w},{n},{e})[harbour];
 nwr({s},{w},{n},{e})[amenity=ferry_terminal];
);
out geom;"""


def kachel(la, lo):
    return math.floor(la), math.floor(lo)


def laden(k):
    pfad = os.path.join(KACHELN, f'{k[0]}_{k[1]}.json')
    if os.path.exists(pfad):
        return json.load(open(pfad))
    q = ABFRAGE.format(s=k[0], w=k[1], n=k[0] + 1, e=k[1] + 1)
    for runde in range(4):
        for srv in SERVER:
            try:
                d = urllib.request.urlopen(urllib.request.Request(
                    srv, data=urllib.parse.urlencode({'data': q}).encode(),
                    headers={'User-Agent': 'tide-lookup/1.0'}), timeout=400).read()
                j = json.loads(d)
                os.makedirs(KACHELN, exist_ok=True)
                json.dump(j, open(pfad, 'w'))
                return j
            except Exception as e:                      # naechster Server
                print(f'    {k} {srv.split("/")[2]}: {str(e)[:60]}', file=sys.stderr)
                time.sleep(10)
        time.sleep(60 * (runde + 1))
    return None


def punkte(el):
    """-> (Wasserpunkte, Anlegerpunkte) eines Overpass-Elements."""
    t = el.get('tags', {})
    anleger = bool(t.get('man_made') in ('pier', 'breakwater', 'groyne') or 'harbour' in t
                   or t.get('amenity') == 'ferry_terminal')
    g = el.get('geometry') or [p for m in el.get('members', []) for p in (m.get('geometry') or [])]
    if not g and 'lat' in el:
        g = [{'lat': el['lat'], 'lon': el['lon']}]
    if not g and 'center' in el:
        g = [el['center']]
    pts = [(p['lat'], p['lon']) for p in g if p]
    # Linien fein auffuellen (sonst liegen Stuetzpunkte bis km auseinander)
    dicht = []
    for (a1, o1), (a2, o2) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(a2 - a1, o2 - o1) / 0.001))
        dicht += [(a1 + (a2 - a1) * i / n, o1 + (o2 - o1) * i / n) for i in range(n)]
    dicht += pts[-1:]
    return (dicht, t.get('name', '')) if not anleger else ([], ''), (pts, t.get('name', '')) if anleger else ([], '')


def abstand(la, lo, a, o):
    return math.hypot((a - la) * 111.32, (o - lo) * 111.32 * math.cos(math.radians(la))) * 1000


def main(argv):
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']
            and r['name'].endswith('China')]
    ks = sorted({kachel(r['lat'], r['lon']) for r in recs})
    print(f'{len(recs)} Saetze in {len(ks)} Kacheln', file=sys.stderr)
    daten = {}
    for i, k in enumerate(ks):
        daten[k] = laden(k)
        print(f'  Kachel {i + 1}/{len(ks)} {k}: {"ok" if daten[k] else "FEHLT"}', file=sys.stderr)
    if '--nur-laden' in argv:
        return 0
    zeilen = []
    for r in recs:
        la, lo = r['lat'], r['lon']
        wasser, anleger = [], []
        for dk in (-1, 0, 1):                     # Nachbarkacheln (Randlagen)
            for dl in (-1, 0, 1):
                j = daten.get((kachel(la, lo)[0] + dk, kachel(la, lo)[1] + dl))
                if j is None and (dk, dl) == (0, 0):
                    break
                for el in (j or {}).get('elements', []):
                    (wp, wn), (ap, an) = punkte(el)
                    wasser += [(abstand(la, lo, a, o), a, o, wn) for a, o in wp
                               if abs(a - la) < 0.06 and abs(o - lo) < 0.06]
                    anleger += [(abstand(la, lo, a, o), a, o, an) for a, o in ap
                                if abs(a - la) < 0.06 and abs(o - lo) < 0.06]
        w = min(wasser) if wasser else None
        a = min(anleger) if anleger else None
        klasse, vor = 'ok', None
        if w is None or w[0] > 3000:
            klasse = 'verdacht'
        elif w[0] > 300:
            klasse = 'verschieben'
            vor = a if a and a[0] <= 1500 else w
        zeilen.append(dict(satz=r['name'], datei=os.path.basename(r['file']), lat=f'{la:.4f}', lon=f'{lo:.4f}',
                           wasser_m='' if w is None else round(w[0]), wasser_name='' if w is None else w[3],
                           anleger_m='' if a is None else round(a[0]), anleger_name='' if a is None else a[3],
                           klasse=klasse, neu_lat='' if not vor else f'{vor[1]:.5f}',
                           neu_lon='' if not vor else f'{vor[2]:.5f}'))
    zeilen.sort(key=lambda z: ({'verdacht': 0, 'verschieben': 1, 'ok': 2}[z['klasse']], z['satz']))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)
    from collections import Counter
    print(f'-> {os.path.relpath(AUS, ROOT)}:', dict(Counter(z['klasse'] for z in zeilen)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
