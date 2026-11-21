#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verkehrstrennungsgebiete (VTG/TSS) fuer das Segel-Routing (Oliver 21.11.2026), KVR Regel 10 vereinfacht.

Daten: OpenSeaMap/OSM (quellen/routing/tss_osm.json, Overpass 21.11.2026: seamark:type separation_zone 367,
separation_lane 964 (Linie, Zeichenrichtung = Verkehrsrichtung), separation_line/boundary).

    T = regeln(LAT2, LON2, peil) -> None oder (erlaubt[32, ny, nx], n_vtg, n_zone, richtung[ny, nx], zone[ny, nx])
Je Knoten:
  * in einer Trennzone (Flaeche): nur Queren, Kurs 90° +- 25° zur Verkehrsrichtung des naechsten Fahrstreifens;
  * in einem Fahrstreifen (<= 8 km von der Streifenlinie, ohne Trennzone/-linie/Grenze dazwischen, nicht hinter dem
    Linienende): mit dem Verkehr (+- 35°) oder queren (90° +- 25°);
    gegen den Verkehr und schraeg queren verboten.
Kuestenverkehrszonen bleiben frei (Sportboote duerfen sie nutzen).
"""
import json
import math
import os

import numpy as np

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(BASIS, "quellen", "routing", "tss_osm.json")
MIT, QUER = 35.0, 25.0
MAX_KM = 8.0
_D = {}


def _daten():
    if "e" not in _D:
        _D["e"] = json.load(open(DATEI))["elements"] if os.path.exists(DATEI) else []
    return _D["e"]


def regeln(LAT2, LON2, peil):
    from shapely.geometry import LineString, Point, Polygon
    from shapely.strtree import STRtree
    s, n, w, e = LAT2.min() - 0.1, LAT2.max() + 0.1, LON2.min() - 0.15, LON2.max() + 0.15
    zonen, streifen, grenzen = [], [], []
    for el in _daten():
        g = el.get("geometry") or []
        if len(g) < 2:
            continue
        la = [p["lat"] for p in g]
        lo = [p["lon"] for p in g]
        if max(la) < s or min(la) > n or max(lo) < w or min(lo) > e:
            continue
        t = el["tags"].get("seamark:type")
        xy = list(zip(lo, la))
        if t == "separation_zone" and len(xy) >= 4 and xy[0] == xy[-1]:
            zonen.append(Polygon(xy).buffer(0))
        elif t == "separation_lane":
            streifen.append(LineString(xy))
        elif t in ("separation_line", "separation_boundary", "separation_zone"):
            grenzen.append(LineString(xy))
    if not streifen and not zonen:
        return None
    kx = math.cos(math.radians((s + n) / 2))
    km = lambda d: d * 111.2                                          # noqa: E731  (Grad -> km grob, Breite)
    trenner = [z.exterior for z in zonen if z.geom_type == "Polygon"] + grenzen
    from shapely.ops import unary_union
    from shapely.prepared import prep
    wand = prep(unary_union(trenner)) if trenner else None
    ny, nx = LAT2.shape
    richt = np.full((ny, nx), np.nan)
    zone = np.zeros((ny, nx), bool)
    baum_s = STRtree(streifen) if streifen else None
    baum_z = STRtree(zonen) if zonen else None
    for i in range(ny):
        for j in range(nx):
            p = Point(LON2[i, j], LAT2[i, j])
            in_zone = baum_z is not None and any(zonen[q].contains(p) for q in baum_z.query(p))
            if baum_s is None:
                continue
            q = int(baum_s.nearest(p))
            L = streifen[q]
            a = L.project(p)
            if not in_zone:
                # im Streifen: hoechstens MAX_KM von der Streifenlinie, nicht hinter deren Ende, und keine Trennlinie/
                # Trennzone/Grenze zwischen Punkt und Linie (Streifen reicht bis zur Begrenzung, nicht symmetrisch)
                if km(L.distance(p)) > MAX_KM or a <= 0 or a >= L.length:
                    continue
                if wand is not None and wand.intersects(LineString([(p.x, p.y), L.interpolate(a).coords[0]])):
                    continue
            # Verkehrsrichtung: Peilung des naechsten Streifenabschnitts (Zeichenrichtung)
            p1, p2 = L.interpolate(max(0, a - 0.002)), L.interpolate(min(L.length, a + 0.002))
            richt[i, j] = math.degrees(math.atan2((p2.x - p1.x) * kx, p2.y - p1.y)) % 360
            zone[i, j] = in_zone
    hat = np.isfinite(richt)
    if not hat.any():
        return None
    diff = np.abs(((peil[:, None, None] - richt[None]) + 180) % 360 - 180)        # 0..180
    mit = diff <= MIT
    quer = np.abs(diff - 90) <= QUER
    erlaubt = np.where(hat[None], np.where(zone[None], quer, mit | quer), True)
    return erlaubt, int(hat.sum()), int(zone.sum()), richt, zone
