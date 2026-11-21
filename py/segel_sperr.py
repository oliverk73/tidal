#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sperrgebiete fuer das Segel-Routing (Oliver 21.11.2026).

Daten: OpenSeaMap/OSM seamark:type=restricted_area mit Einschraenkung (quellen/routing/sperr_osm.json, Overpass
21.11.2026, 3616 Gebiete). Gesperrt: restriction enthaelt no_entry oder to_be_avoided (1436). restricted_entry
(Zutritt mit Auflagen, saisonal/Genehmigung) wird nur gemeldet. Anker-/Fischerei-/Geschwindigkeitsregeln betreffen
die Durchfahrt nicht.

    gesperrt, auflagen = raster(s, n, w, e, ny, nx)   -> bool-Raster (True = Einfahrt verboten), Namen mit Auflagen
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(BASIS, "quellen", "routing", "sperr_osm.json")
SPERRE = ("no_entry", "to_be_avoided")
_D = {}


def _flaechen():
    """-> Liste (art, name, [Ringe als (lon, lat)-Listen], bbox)."""
    if "f" in _D:
        return _D["f"]
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    out = []
    els = json.load(open(DATEI))["elements"] if os.path.exists(DATEI) else []
    for e in els:
        t = e.get("tags", {})
        r = t.get("seamark:restricted_area:restriction", "")
        art = "sperre" if any(x in r for x in SPERRE) else ("auflage" if "restricted_entry" in r else None)
        if art is None:
            continue
        name = t.get("seamark:name") or t.get("name") or t.get("seamark:restricted_area:category", "restricted area")
        ringe = []
        if e["type"] == "way":
            g = e.get("geometry") or []
            xy = [(p["lon"], p["lat"]) for p in g]
            if len(xy) >= 4 and xy[0] == xy[-1]:
                ringe.append(xy)
        else:
            linien = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in e.get("members", [])
                      if m.get("role") == "outer" and len(m.get("geometry") or []) >= 2]
            for poly in polygonize(unary_union(linien)) if linien else []:
                ringe.append(list(poly.exterior.coords))
        if not ringe:
            continue
        a = np.array([p for r_ in ringe for p in r_])
        out.append((art, name, ringe, (a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max())))
    _D["f"] = out
    return out


def raster(s, n, w, e, ny, nx):
    img = Image.new("1", (nx, ny), 0)
    dr = ImageDraw.Draw(img)
    sx, sy = nx / (e - w), ny / (n - s)
    auflagen = []
    for art, name, ringe, (x0, y0, x1, y1) in _flaechen():
        if x1 < w or x0 > e or y1 < s or y0 > n:
            continue
        if art == "auflage":
            auflagen.append(name)
            continue
        for r in ringe:
            dr.polygon([((x - w) * sx, (n - y) * sy) for x, y in r], fill=1)
    return np.array(img, dtype=bool), sorted(set(auflagen))
