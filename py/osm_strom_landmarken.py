#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OSM-Landmarken fuer Stromsatznamen: Fahrwasser-Linien, kleine Meerengen, Offshore-Windparks, Plattformen (16.11.2026).

Anlass (Oliver 16.11.): "Dwarsloch" (GeoNames-Punkt 1,6 km) statt der Piep, auf deren OSM-Fahrwasserlinie der Satz liegt
(0,1 km) -- GeoNames hat je Rinne nur einen Punkt. Und Stromsaetze in/an Windparks (Liverpool Bay) bekamen ferne Orte.
Abstand zur Linie bzw. zum Flaechenrand (0 = drin) statt zu einem Mittelpunkt.

Holen in zwei Schritten (Overpass-Kacheln waeren ~21 h):
  1. weltweit nur bb/center der benannten Objekte (scratchpad/osm/*.json, Schritt im Aufruf --holen)
  2. Objekte mit bb bis 15 km an einem Stromsatz -> Geometrie per ID -> quellen/tidal_streams/strom_landmarken_osm.json

Usage: venv/bin/python py/osm_strom_landmarken.py --geometrie ORDNER   (ORDNER mit fairway/seamark/strait/platform/wind.json)
"""
import json
import math
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'quellen/tidal_streams/strom_landmarken_osm.json')
OVERPASS = 'https://overpass-api.de/api/interpreter'
UA = 'tide-research-client/1.0'           # ohne User-Agent antwortet overpass-api.de mit 406
UMKREIS_KM = 15.0
STRAIT_MAX_KM = 40.0                      # grosse Meerengen (Aermelkanal) sagen als Name nichts


def _art(t):
    if t.get('power') == 'plant':
        return 'wind'
    if t.get('man_made') == 'offshore_platform':
        return 'platform'
    if t.get('natural') == 'strait':
        return 'strait'
    return 'fairway'


def _weg(t):
    """stillgelegt/geplant/abgebaut -> True."""
    if any(k.split(':')[0] in ('disused', 'abandoned', 'demolished', 'removed', 'razed', 'proposed', 'construction', 'planned')
           and k.endswith(('man_made', 'power')) for k in t):
        return True
    if t.get('disused') == 'yes' or t.get('abandoned') == 'yes' or t.get('operational_status') in ('closed', 'decommissioned'):
        return True
    return bool(re.search(r'\((disused|abandoned|removed|decommissioned)\)', t.get('name', ''), re.I))


def plattform_name(n):
    """Codes ('110/3', 'DP') sind keine Namen (namen-ohne-codes) -> None; sonst 'Douglas' -> 'Douglas Platform'."""
    if re.search(r'\d', n) or not re.search(r'[A-Za-zÀ-ɏ]{4,}', n):
        return None
    return n if re.search(r'platform|plattform', n, re.I) else n + ' Platform'


def windpark_name(n):
    """'Gwynt y Môr Offshore Wind Farm' -> 'Gwynt y Môr Wind Farm' (libtcd-Namen <= 90 Zeichen)."""
    n = re.sub(r'\s+Offshore(?=\s+Wind)', '', n, flags=re.I)
    return n if re.search(r'wind', n, re.I) else n + ' Wind Farm'


def vorfilter(ordner):
    import health_check as H
    R = [(r['lat'], r['lon']) for r in H.load_records() if r['current'] and r['lat'] is not None]
    zellen = {}
    for la, lo in R:
        zellen.setdefault((math.floor(la * 5), math.floor(lo * 5)), []).append((la, lo))
    pad = UMKREIS_KM / 111.2
    wahl = []
    for datei in ('fairway', 'seamark', 'strait', 'platform', 'wind'):
        p = os.path.join(ordner, datei + '.json')
        if not os.path.exists(p):
            print('fehlt', p)
            continue
        E = json.load(open(p))['elements']
        n0, vorher = len(E), len(wahl)
        for e in E:
            t = e.get('tags', {})
            if not t.get('name') or _weg(t):
                continue
            art = _art(t)
            if art == 'platform' and not plattform_name(t['name']):
                continue
            if 'bounds' in e:
                b = e['bounds']
                s, w, n, o = b['minlat'], b['minlon'], b['maxlat'], b['maxlon']
            elif 'lat' in e or 'center' in e:
                c = e if 'lat' in e else e['center']
                s = n = c['lat']
                w = o = c['lon']
            else:                                   # Relation ohne Mitglieder-Geometrie (Spiegelserver)
                continue
            if art == 'strait' and 111.2 * math.hypot(n - s, (o - w) * math.cos(math.radians((n + s) / 2))) > STRAIT_MAX_KM:
                continue
            k = math.cos(math.radians((n + s) / 2)) or 0.01
            nah = False
            for i in range(math.floor((s - pad) * 5), math.floor((n + pad) * 5) + 1):
                for j in range(math.floor((w - pad / k) * 5), math.floor((o + pad / k) * 5) + 1):
                    for la, lo in zellen.get((i, j), ()):
                        if s - pad <= la <= n + pad and w - pad / k <= lo <= o + pad / k:
                            nah = True
                            break
                    if nah:
                        break
                if nah:
                    break
            if nah:
                wahl.append((e['type'], e['id'], art, t['name']))
        print('%-9s %6d Objekte, %d an Stromsaetzen' % (datei, n0, len(wahl) - vorher))
    return sorted(set(wahl))


SPIEGEL = ('https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter')


def overpass(q, versuche=4):
    for v in range(versuche):
        for url in (OVERPASS,) + SPIEGEL:   # Hauptserver oft ueberlastet (502): Spiegel reihum
            r = subprocess.run(['curl', '-s', '-m', '900', '-A', UA, '--data-urlencode', 'data=' + q, url], capture_output=True, text=True)
            if r.stdout.startswith('{'):
                try:
                    return json.loads(r.stdout)
                except ValueError:
                    pass
            print('  Overpass-Fehler, Versuch', v + 1, url.split('/')[2], r.stdout[:80].replace('\n', ' '))
        time.sleep(60 * (v + 1))
    raise RuntimeError('Overpass')


def geometrie(ordner):
    wahl = vorfilter(ordner)
    alt = {}
    if os.path.exists(ZIEL):
        alt = {(x['typ'], x['id']): x for x in json.load(open(ZIEL, encoding='utf-8'))}
    offen = [w for w in wahl if (w[0], w[1]) not in alt]
    print(len(wahl), 'Objekte,', len(offen), 'ohne Geometrie')
    art = {(t, i): a for t, i, a, _n in wahl}
    for k in range(0, len(offen), 150):
        teil = offen[k:k + 150]
        q = '[out:json][timeout:600];(' + ''.join('%s(id:%s);' % (t, ','.join(str(i) for tt, i, _a, _n in teil if tt == t))
                                                for t in ('node', 'way', 'relation') if any(x[0] == t for x in teil)) + ');out geom;'
        for e in overpass(q)['elements']:
            g = None
            if e['type'] == 'node':
                g = [[e['lat'], e['lon']]]
            elif e['type'] == 'way':
                g = [[[p['lat'], p['lon']] for p in e.get('geometry', [])]]
            else:
                g = [[[p['lat'], p['lon']] for p in m['geometry']] for m in e.get('members', [])
                     if m.get('type') == 'way' and m.get('geometry') and m.get('role', 'outer') in ('outer', '', 'main_stream')]
                if not g:   # Relation aus Knoten (Plattformgruppe): Knoten als Punkte
                    g = [[[m['lat'], m['lon']]] for m in e.get('members', []) if m.get('type') == 'node' and 'lat' in m]
            if g:
                alt[(e['type'], e['id'])] = dict(typ=e['type'], id=e['id'], art=art.get((e['type'], e['id']), _art(e.get('tags', {}))),
                                                 name=e.get('tags', {}).get('name', ''), geom=g)
        print('  %d/%d' % (min(k + 150, len(offen)), len(offen)), flush=True)
        json.dump(list(alt.values()), open(ZIEL, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    _land_aussortieren(alt)
    json.dump(list(alt.values()), open(ZIEL, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(len(alt), '->', os.path.relpath(ZIEL, ROOT))


def _land_aussortieren(alt):
    """Windparks an Land (Mittelpunkt auf Land) markieren: sie benennen keine Stroemung."""
    import osm_land
    W = [x for x in alt.values() if x['art'] == 'wind']
    mitte = []
    for x in W:
        P = [p for ring in x['geom'] for p in ring]
        mitte.append((sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P)))
    if not W:
        return
    L = osm_land.Land(mitte)
    n = 0
    for x, (la, lo) in zip(W, mitte):
        x['land'] = bool(L.ist_land(la, lo))
        n += x['land']
    print('Windparks: %d an Land, %d offshore' % (n, len(W) - n))


# ------------------------------------------------------------------------------------------------ Abfrage
_O = []
_GRID = {}


def laden():
    if not _O and os.path.exists(ZIEL):
        for x in json.load(open(ZIEL, encoding='utf-8')):
            if x.get('land'):
                continue
            if x['geom'] and not isinstance(x['geom'][0][0], list):
                x['geom'] = [x['geom']]                                  # Knoten: [[la, lo]] -> ein Ring mit einem Punkt
            if not x['geom'] or not x['geom'][0]:
                continue
            _O.append(x)
            P = [p for ring in x['geom'] for p in ring]
            s, n = min(p[0] for p in P), max(p[0] for p in P)
            w, o = min(p[1] for p in P), max(p[1] for p in P)
            x['bb'] = (s, w, n, o)
            x['km'] = math.hypot((n - s) * 111.2, (o - w) * 111.2 * math.cos(math.radians((s + n) / 2)))   # Ausdehnung (Diagonale)
            for i in range(math.floor(s * 5) - 1, math.floor(n * 5) + 2):
                for j in range(math.floor(w * 5) - 2, math.floor(o * 5) + 3):
                    _GRID.setdefault((i, j), []).append(x)
        groesse = {}
        for x in _O:                                                     # Knoten erben die Ausdehnung gleichnamiger Flaechen/Linien
            groesse[x['name']] = max(groesse.get(x['name'], 0), x['km'])
        for x in _O:
            x['km'] = groesse[x['name']]
    return _O


def nah(la, lo, max_km=12.0):
    """-> [(km, name, art, drin, lat_naechster, lon_naechster)] nach Abstand (Linie/Flaechenrand; Flaeche drin -> 0)."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import nearest_points, polygonize, unary_union
    laden()
    k = math.cos(math.radians(la))
    xy = lambda p: ((p[1] - lo) * k * 111.2, (p[0] - la) * 111.2)  # noqa: E731
    ll = lambda x, y: (la + y / 111.2, lo + x / (k * 111.2))          # noqa: E731
    gesehen, out = set(), []
    for x in _GRID.get((math.floor(la * 5), math.floor(lo * 5)), []):
        if id(x) in gesehen:
            continue
        gesehen.add(id(x))
        s, w, n, o = x['bb']
        if la < s - max_km / 111.2 or la > n + max_km / 111.2 or lo < w - max_km / (111.2 * k) or lo > o + max_km / (111.2 * k):
            continue
        linien = [[xy(p) for p in r] for r in x['geom']]
        P0 = Point(0, 0)
        if x['art'] in ('wind', 'strait'):
            flaechen = [Polygon(r) for r in linien if len(r) >= 4 and r[0] == r[-1]]
            if not flaechen:
                flaechen = list(polygonize([LineString(r) for r in linien if len(r) >= 2]))
            if flaechen:
                F = unary_union([f.buffer(0) for f in flaechen])
                if F.contains(P0):
                    out.append((0.0, x['name'], x['art'], True, la, lo, x['km']))
                    continue
                q = nearest_points(F.boundary, P0)[0]
                out.append((P0.distance(q), x['name'], x['art'], False) + ll(q.x, q.y) + (x['km'],))
                continue
        geo = [LineString(r) if len(r) >= 2 else Point(r[0]) for r in linien if r]
        if not geo:
            continue
        G = unary_union(geo)
        q = nearest_points(G, P0)[0]
        out.append((P0.distance(q), x['name'], x['art'], False) + ll(q.x, q.y) + (x['km'],))
    return sorted(z for z in out if z[0] <= max_km)


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if '--geometrie' in sys.argv:
        geometrie(sys.argv[sys.argv.index('--geometrie') + 1])
    elif '--probe' in sys.argv:
        la, lo = map(float, sys.argv[sys.argv.index('--probe') + 1:sys.argv.index('--probe') + 3])
        for z in nah(la, lo):
            print('%5.2f km  %-40s %-8s %s' % (z[0], z[1], z[2], 'drin' if z[3] else ''))
    else:
        print(__doc__)
