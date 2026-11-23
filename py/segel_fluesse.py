#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flussflaechen fuer das Segel-Routing (23.11.2026).

Die OSM-Landpolygone (segel_land) beruhen nur auf der Kuestenlinie. Die schliesst Muendungen irgendwo ab (Loire an der
Bruecke Saint-Nazaire, Themse bei Gravesend, Elbe vor Hamburg, Saint-Laurent ab Ile d'Orleans ...), dahinter ist alles
"Land". Hier: OSM-Wasserflaechen der Tidefluesse aus Overpass, als Wasser ueber die Landmaske gelegt.

Welche Gebiete: 0,5-Grad-Kacheln um die Pegel/Stromsaetze des Bestands, die hinter der OSM-Kuestenlinie liegen
(dort gibt es Tide, also Schiffsverkehr). Abfrage je Kachel einmal, streng nacheinander (Overpass ist ein
Gemeinschaftsdienst), Ergebnis als Ringe in quellen/routing/fluesse/<lat2>_<lon2>.json. Der Router liest nur diese
Dateien und fragt nie live.

Tags: natural=water mit water=river|canal|tidal_channel|lagoon|harbour|dock|basin|lock|oxbow|ditch? nein (zu klein),
waterway=riverbank|dock|canal(Flaeche). Seen nicht (vom Meer aus nicht erreichbar, und sehr viele Daten).

    laden [--max N]            fehlende Kacheln holen (Liste aus dem Bestand)
    raster(s, n, w, e, ny, nx) -> bool (ny, nx), True = Flusswasser (Zeile 0 = Nord, wie segel_land)
"""
import json
import math
import os
import sys
import time

import numpy as np
import requests
from PIL import Image, ImageDraw

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASIS, 'quellen', 'routing', 'fluesse')
API = os.environ.get('OVERPASS_API', 'https://overpass-api.de/api/interpreter')
WASSER = 'river|canal|tidal_channel|lagoon|harbour|dock|basin|lock|oxbow|estuary'
_K = {}


def _datei(i, j):
    return os.path.join(D, '%d_%d.json' % (i, j))


def kacheln_bestand():
    """0,5-Grad-Kacheln (i = floor(lat*2), j = floor(lon*2)) mit Saetzen hinter der OSM-Kuestenlinie."""
    sys.path.insert(0, os.path.join(BASIS, 'py'))
    import health_check as H
    import segel_land as L
    R = [r for r in H.load_records() if r['lat'] is not None]
    kach = {}
    for r in R:
        kach.setdefault((int(math.floor(r['lat'] * 2)), int(math.floor(r['lon'] * 2))), []).append(r)
    aus = {}
    for (i, j), rs in kach.items():
        s, w = i / 2, j / 2
        m = L.raster(s, s + 0.5, w, w + 0.5, 100, 100)
        for r in rs:
            a = min(max(int((s + 0.5 - r['lat']) / 0.005), 0), 99)
            b = min(max(int((r['lon'] - w) / 0.005), 0), 99)
            if m[a, b] and m[max(a - 2, 0):a + 3, max(b - 2, 0):b + 3].all():   # mindestens ~1 km im "Land"
                aus[(i, j)] = aus.get((i, j), 0) + 1
    return sorted(aus, key=lambda k: -aus[k])          # Kacheln mit vielen Flusspegeln zuerst (Hauptstroeme)


def _ringe_bauen(el):
    """Overpass-JSON (out geom) -> [(punkte [[lon, lat], ...], aussen)]."""
    ringe = []
    for e in el:
        if e['type'] == 'way' and e.get('geometry'):
            g = [(p['lon'], p['lat']) for p in e['geometry']]
            if len(g) >= 4 and g[0] == g[-1]:
                ringe.append((g, True))
        elif e['type'] == 'relation':
            for rolle in ('outer', 'inner'):
                stuecke = [[(p['lon'], p['lat']) for p in m['geometry']] for m in e.get('members', [])
                           if m.get('type') == 'way' and m.get('role', 'outer') in ((rolle,) if rolle == 'inner' else ('outer', ''))
                           and m.get('geometry')]
                for r in _verbinden(stuecke):
                    if len(r) >= 4:
                        ringe.append((r, rolle == 'outer'))
    return ringe


def _verbinden(stuecke):
    """Offene Wege eines Multipolygons an gemeinsamen Endpunkten zu Ringen verbinden."""
    fertig, offen = [], []
    for s in stuecke:
        (fertig if s[0] == s[-1] else offen).append(list(s))
    while offen:
        r = offen.pop()
        weiter = True
        while weiter and r[0] != r[-1]:
            weiter = False
            for q, s in enumerate(offen):
                if s[0] == r[-1]:
                    r += s[1:]
                elif s[-1] == r[-1]:
                    r += s[::-1][1:]
                elif s[-1] == r[0]:
                    r = s[:-1] + r
                elif s[0] == r[0]:
                    r = s[::-1][:-1] + r
                else:
                    continue
                offen.pop(q)
                weiter = True
                break
        if r[0] == r[-1]:
            fertig.append(r)
    return fertig


def kachel_holen(i, j):
    s, w = i / 2, j / 2
    bb = '%.2f,%.2f,%.2f,%.2f' % (s, w, s + 0.5, w + 0.5)
    q = ('[out:json][timeout:180];(way["natural"="water"]["water"~"^(%s)$"](%s);'
         'relation["natural"="water"]["water"~"^(%s)$"](%s);way["waterway"~"^(riverbank|dock|canal)$"](%s);'
         'relation["waterway"~"^(riverbank|dock)$"](%s););out geom;' % (WASSER, bb, WASSER, bb, bb, bb))
    for versuch in range(4):
        try:
            r = requests.post(API, data={'data': q}, timeout=240, headers={'User-Agent': 'tide-research-script'})
            if r.status_code == 200 and r.text.lstrip().startswith('{'):
                ringe = _ringe_bauen(r.json().get('elements', []))
                os.makedirs(D, exist_ok=True)
                json.dump([[[[round(x, 6), round(y, 6)] for x, y in g], a] for g, a in ringe], open(_datei(i, j), 'w'),
                          separators=(',', ':'))
                return len(ringe)
            print('  %d_%d HTTP %d' % (i, j, r.status_code), flush=True)
        except Exception as e:                       # noqa: BLE001
            print('  %d_%d Fehler %s' % (i, j, str(e)[:120]), flush=True)
        time.sleep(60 * (versuch + 1))
    return None


def laden(argv):
    mx = int(argv[argv.index('--max') + 1]) if '--max' in argv else 10 ** 9
    liste = kacheln_bestand()
    fehlt = [k for k in liste if not os.path.exists(_datei(*k))]
    print('%d Kacheln, %d fehlen' % (len(liste), len(fehlt)), flush=True)
    for n, (i, j) in enumerate(fehlt[:mx]):
        t0 = time.time()
        z = kachel_holen(i, j)
        print('%4d/%d  %d_%d  %s Ringe  %.0f s' % (n + 1, len(fehlt), i, j, z, time.time() - t0), flush=True)
        time.sleep(3)


def _kachel(i, j):
    if (i, j) not in _K:
        p = _datei(i, j)
        _K[(i, j)] = [(np.asarray(g, float), a) for g, a in json.load(open(p))] if os.path.exists(p) else None
    return _K[(i, j)]


def raster(sued, nord, west, ost, ny, nx, min_px=0):
    """True = Flusswasser laut OSM (nur gespeicherte Kacheln). Pixelmitte wie segel_land.raster.
    min_px > 0 (23.11.2026, Nord-Ostsee-Kanal ~100 m breit, Routerknoten ~1 km): schmale Stellen (schmaler als min_px
    Pixel) auf etwa min_px + 2 Pixel verbreitern, damit der Router dort durchgehend Knoten und Kanten hat."""
    img = Image.new('1', (nx, ny), 0)
    dr = ImageDraw.Draw(img)
    sx, sy = nx / (ost - west), ny / (nord - sued)
    gefunden = False
    for i in range(int(math.floor(sued * 2)), int(math.floor(nord * 2)) + 1):
        for j in range(int(math.floor(west * 2)), int(math.floor(ost * 2)) + 1):
            K = _kachel(i, j)
            if not K:
                continue
            gefunden = True
            for aussen in (True, False):              # erst Flaechen, dann Inseln darin ausschneiden
                for g, a in K:
                    if a != aussen:
                        continue
                    px = list(zip(((g[:, 0] - west) * sx).tolist(), ((nord - g[:, 1]) * sy).tolist()))
                    dr.polygon(px, fill=1 if a else 0, outline=1 if a else None)
    if not gefunden:
        return np.zeros((ny, nx), bool)
    m = np.array(img, dtype=bool)
    if min_px > 0 and m.any():
        from scipy import ndimage
        st = np.ones((min_px, min_px), bool)
        schmal = m & ~ndimage.binary_opening(m, structure=st)
        if schmal.any():
            r = min_px // 2 + 1
            m |= ndimage.binary_dilation(schmal, structure=np.ones((2 * r + 1, 2 * r + 1), bool))
    return m


if __name__ == '__main__':
    if sys.argv[1:2] == ['laden']:
        laden(sys.argv[2:])
    else:
        print(__doc__)
