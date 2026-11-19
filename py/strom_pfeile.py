#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strompfeile an den Harmonics-Stromsaetzen fuer die Kartenebene "Tidal Currents" (Oliver 18.11.2026).

pfeile(s, n, w, e, z, t0, schritte, dt) -> Liste je Satz: Name, Datei, Position, Rang und Ost-/Nord-Komponente
in Knoten zu den Zeiten t0 + i*dt. Je Rasterzelle von ZELLE_PX Bildpunkten (Web-Mercator, Zoom z) bleibt nur
der beste Satz (kleinster Rang), damit die Karte nicht zugekleistert wird.

Richtung:
- Saetze mit Ellipsenkonstanten (NOAA harcon, eigene Fits; strom_ellipsen.fuer_satz): voller Vektor
- sonst Wert entlang der Achse: positiv -> flood_dir / max_direction / major_axis_deg_true,
  negativ -> ebb_dir / min_direction / Flutrichtung + 180
- ohne jede Richtungsangabe: nicht gezeigt

Rang (kleiner = bevorzugt): Messfit 0, NOAA-Hauptstrom/Ellipse 1, Tafeln/Atlanten/DWF 2, ATT 3, NOAA-Nebenstrom 4.

Test: venv/bin/python py/strom_pfeile.py 50.5 51 -1.6 -0.9 10
"""
import math
import os
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strom_ellipsen as E                                          # noqa: E402
import tiden_dienst as TD                                           # noqa: E402

ZELLE_PX = 56
MAX_SAETZE = 600
_sperre = threading.Lock()
_index = {'stand': None, 'liste': []}


def _rang(pfad, ellipse):
    b = os.path.basename(pfad)
    if 'current_observations' in b or 'oceancurrent' in b:
        return 0
    if 'nebenstroeme' in b:
        return 4
    if ellipse or 'noaa_currents' in b:
        return 1
    if '_att_' in b:
        return 3
    return 2


def _richtung(h, *keys):
    for k in keys:
        v = h.get(k)
        if v not in (None, ''):
            try:
                return float(v.split()[0])
            except ValueError:
                pass
    return None


def index():
    """[(lat, lon, rang, pfad, name, flut, ebbe, ellipse)] aller Stromsaetze; neu, wenn sich Dateien aendern."""
    pfade = TD._aktive()
    stand = tuple((p, os.path.getmtime(p)) for p in pfade if os.path.exists(p))
    with _sperre:
        if _index['stand'] == stand:
            return _index['liste']
    liste = []
    for p in pfade:
        D = TD.datei(p)
        for name, s in D.saetze.items():
            if not s.strom:
                continue
            try:
                lat, lon = float(s.hot['!latitude']), float(s.hot['!longitude'])
            except (KeyError, ValueError):
                continue
            try:
                ell = E.fuer_satz(D, name)
            except Exception:  # noqa: BLE001
                ell = None
            flut = _richtung(s.hot, 'flood_dir', 'max_direction', 'major_axis_deg_true')
            ebbe = _richtung(s.hot, 'ebb_dir', 'min_direction')
            if ell is None and flut is None:
                continue
            if ebbe is None and flut is not None:
                ebbe = (flut + 180) % 360
            liste.append((lat, lon, _rang(p, ell), p, name, flut, ebbe, ell))
    with _sperre:
        _index['stand'], _index['liste'] = stand, liste
    return liste


def _merc(lat, lon, z):
    s = 256 * 2 ** z
    x = (lon + 180) / 360 * s
    la = math.radians(max(-85, min(85, lat)))
    y = (1 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2 * s
    return x, y


_URL = {}


def detail_url(name, datei):
    """Link zur Detailseite wie die Kartenmarker (static/js/leaflet_markers.js): /prediction/<slug>[?source=<tcd>].
    Aus static/js/leaflet_markers_data.json, neu gelesen, wenn sich die Datei aendert (19.11.2026)."""
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static/js/leaflet_markers_data.json')
    try:
        mt = os.path.getmtime(pfad)
    except OSError:
        return None
    if _URL.get('mt') != mt:
        import json
        d = json.load(open(pfad, encoding='utf-8'))
        m = {}
        for st in d['stations']:
            if st[5] != 1:
                continue
            url = '/prediction/%s?source=%s' % (st[6], st[3]) if st[7] == 1 else '/prediction/%s' % st[6]
            for nm in (st[8], st[0]):
                m.setdefault((nm, st[3].rsplit('.', 1)[0]), url)
                m.setdefault((nm, None), url)
        _URL.clear()
        _URL.update(mt=mt, m=m)
    m = _URL['m']
    return m.get((name, datei)) or m.get((name, None))


def pfeile(s, n, w, e, z, t0, schritte=97, dt=1800):
    t = t0 + np.arange(schritte) * dt
    breit = (e - w) >= 360
    wahl = {}
    for r in index():
        lat, lon = r[0], r[1]
        if not (s <= lat <= n):
            continue
        if not breit:
            lo = lon
            while lo < w:
                lo += 360
            if lo > e:
                continue
        x, y = _merc(lat, lon, z)
        zelle = (int(x // ZELLE_PX), int(y // ZELLE_PX))
        alt = wahl.get(zelle)
        if alt is None or r[2] < alt[2]:
            wahl[zelle] = r
    aus = []
    for r in sorted(wahl.values(), key=lambda r: r[2])[:MAX_SAETZE]:
        lat, lon, rang, p, name, flut, ebbe, ell = r
        D = TD.datei(p)
        try:
            if ell is not None:
                st, ri, _h, _n = E.vektor(D, name, t, ell)
                ost, nord = st * np.sin(np.radians(ri)), st * np.cos(np.radians(ri))
            else:
                v = D.wert(name, t)
                ri = np.where(v >= 0, flut, ebbe)
                st = np.abs(v)
                ost, nord = st * np.sin(np.radians(ri)), st * np.cos(np.radians(ri))
        except Exception:  # noqa: BLE001
            continue
        aus.append({'n': name, 'f': os.path.basename(p)[:-4], 'la': lat, 'lo': lon, 'r': rang,
                    'url': detail_url(name, os.path.basename(p)[:-4]),
                    'u': [round(float(x), 2) for x in ost], 'v': [round(float(x), 2) for x in nord]})
    return {'t0': int(t0), 'dt': int(dt), 'pfeile': aus}


if __name__ == '__main__':
    s, n, w, e, z = (float(x) for x in sys.argv[1:6])
    a = time.time()
    index()
    b = time.time()
    r = pfeile(s, n, w, e, int(z), time.time() // 1800 * 1800)
    print('Index %.1f s, Pfeile %.2f s, %d Saetze' % (b - a, time.time() - b, len(r['pfeile'])))
    for p in r['pfeile'][:8]:
        print('%-60s r%d %4.1f kn' % (p['n'][:60], p['r'], math.hypot(p['u'][0], p['v'][0])))
