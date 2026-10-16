#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Positionsvorschlaege fuer Stroemungsstationen an Engstellen: Mitte des Fahrwassers (nur lesen).

Oliver 16.10.2026: Die Stroemung an einer Engstelle haengt stark von der genauen Position ab.
Die Pruefliste (py/stroemungen_pruefen.py) fand Stationen an Land (LAND) und Bogenminuten-
Positionen an Engen unter 4 km (RASTER). Hier wird je Station im Umkreis der Unsicherheit
(1.5 km, Bogenminute ~1.8 km) der beste Wasserpunkt gesucht: Uferabstand (bis hoechstens 0.4 km
gezaehlt) minus 0.5 x Verschiebung. Ein Punkt an Land wandert so ins naechste freie Wasser, einer
in einer schmalen Enge in deren Mitte; im offenen Wasser bleibt er (erster Versuch mit reinem
Uferabstand schob alles bis an den Suchrand hinaus).

Grundlage: OSM-Landpolygone (py/osm_land.py). Tidefluesse liegen ausserhalb der OSM-Kueste
(Hudson, Cape Fear) -- dort kein Vorschlag.

Usage: venv/bin/python py/stroemung_fahrwasser.py [pruefliste.json]
       -> harmonics/help/vorschlaege_fahrwasser_<datum>.html/.json
"""
import datetime as dt
import glob
import html
import json
import math
import os
import sys

import numpy as np
import shapely
from shapely.geometry import Point, box
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import osm_land                                                    # noqa: E402

ROOT = osm_land.ROOT
RADIUS = 1.5
SCHRITT = 0.05
ABSCHLAG = 0.5
DECKEL = 0.4                 # Uferabstand zaehlt nur bis 0.4 km: offenes Wasser zieht nicht weiter


def main(argv):
    quelle = argv[0] if argv else sorted(glob.glob(os.path.join(ROOT, 'harmonics/help/pruefliste_stroemungen_*.json')))[-1]
    Z = json.load(open(quelle))
    kand = [z for z in Z if any(b.startswith(('LAND', 'RASTER')) for b in z['befunde'])]
    print(len(kand), 'Stationen aus', os.path.basename(quelle), flush=True)
    L = osm_land.Land([(z['lat'], z['lon']) for z in kand])
    out = []
    for z in kand:
        la, lo = z['lat'], z['lon']
        cosl = math.cos(math.radians(la))
        dla, dlo = (RADIUS + 3) / 111.2, (RADIUS + 3) / (111.2 * cosl)
        teile = L._treffer(box(lo - dlo, la - dla, lo + dlo, la + dla))
        if not teile:
            out.append(dict(z, vorschlag=None, grund='kein Land in der Naehe'))
            continue
        land = unary_union(teile)
        rand = land.boundary
        n = int(RADIUS / SCHRITT)
        xs, ys, off = [], [], []
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                d = math.hypot(i, j) * SCHRITT
                if d <= RADIUS:
                    ys.append(la + i * SCHRITT / 111.2)
                    xs.append(lo + j * SCHRITT / (111.2 * cosl))
                    off.append(d)
        pts = shapely.points(np.array(xs), np.array(ys))
        nass = ~shapely.contains(land, pts)
        if not nass.any():
            out.append(dict(z, vorschlag=None, grund='im Umkreis kein Wasser laut OSM-Kueste (Tidefluss?)'))
            continue
        # Uferabstand in km (Grad -> km grob mit cos(Breite) fuer die Laenge)
        dgrad = shapely.distance(rand, pts)
        ukm = dgrad * 111.2 * (0.5 + 0.5 * cosl)
        score = np.where(nass, np.minimum(ukm, DECKEL) - ABSCHLAG * np.array(off), -1e9)
        k = int(np.argmax(score))
        jetzt_land = L.ist_land(la, lo)
        jetzt_ufer = L.kueste_km(la, lo)
        out.append(dict(z, vorschlag=[round(ys[k], 4), round(xs[k], 4)], verschiebung_km=round(off[k], 2),
                        ufer_neu_km=round(float(ukm[k]), 2), ufer_alt_km=round(jetzt_ufer, 2), alt_an_land=jetzt_land,
                        grund=''))
    heute = dt.date.today().strftime('%Y%m%d')
    stem = os.path.join(ROOT, 'harmonics/help/vorschlaege_fahrwasser_%s' % heute)
    json.dump(out, open(stem + '.json', 'w'), ensure_ascii=False, indent=0)
    zeilen = []
    for z in sorted(out, key=lambda z: (z['vorschlag'] is None, -(z.get('verschiebung_km') or 0))):
        b = '; '.join(x for x in z['befunde'] if x.startswith(('LAND', 'RASTER')))
        gm = 'https://www.google.com/maps?q=%.5f,%.5f' % (z['lat'], z['lon'])
        if z['vorschlag']:
            v = z['vorschlag']
            neu = '<a href="https://www.google.com/maps?q=%.5f,%.5f">%.4f / %.4f</a><br><small>%.2f km verschoben, Ufer %.2f km (vorher %s%.2f km)</small>' % (
                v[0], v[1], v[0], v[1], z['verschiebung_km'], z['ufer_neu_km'], 'an Land, ' if z['alt_an_land'] else '', z['ufer_alt_km'])
        else:
            neu = '<small>%s</small>' % html.escape(z['grund'])
        zeilen.append('<tr><td>%s<br><small>%s</small></td><td><a href="%s">%.4f / %.4f</a></td><td>%s</td><td><small>%s</small></td></tr>' % (
            html.escape(z['satz']), os.path.basename(z['datei']), gm, z['lat'], z['lon'], neu, html.escape(b)))
    H = ('<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         '<title>Fahrwasser Vorschlaege</title><style>:root{--bg:#fff;--fg:#1d2430;--mut:#5b6575;--li:#d8dee8;--hd:#eef2f7}'
         '@media (prefers-color-scheme:dark){:root{--bg:#14181f;--fg:#e4e8ef;--mut:#9aa4b4;--li:#2c3440;--hd:#1d232c}}'
         'body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}a{color:inherit}'
         'table{border-collapse:collapse;width:100%}td,th{border:1px solid var(--li);padding:4px 6px;vertical-align:top;text-align:left}'
         'th{background:var(--hd)}small{color:var(--mut)}</style></head><body>'
         '<h1>Stroemungen an Engstellen: Positionsvorschlaege (HEUTE)</h1>'
         '<p>Nichts umgesetzt. Vorschlag = Wasserpunkt bis 1.5 km um die heutige Position: Uferabstand (bis 0.4 km gezaehlt) '
         'minus 0.5 x Verschiebung. Bitte auf der Karte pruefen: bei Stationen "off X Point" oder "0.5 mi N of" ist nicht '
         'immer die Fahrwassermitte gemeint. Ohne Vorschlag: Tidefluesse ausserhalb der OSM-Kueste.</p>'
         '<table><tr><th>Satz</th><th>heute</th><th>Vorschlag</th><th>Befund</th></tr>ZEILEN</table></body></html>'
         ).replace('HEUTE', heute).replace('ZEILEN', '\n'.join(zeilen))
    open(stem + '.html', 'w', encoding='utf-8').write(H)
    print(sum(1 for z in out if z['vorschlag']), 'Vorschlaege,', sum(1 for z in out if not z['vorschlag']), 'ohne')
    print(os.path.relpath(stem + '.html', ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
