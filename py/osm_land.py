#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genaue Land/Wasser-Abfrage mit den OSM-Landpolygonen (osmdata.openstreetmap.de, split 4326).

Anlass 16.10.2026: Die GLOBE-Landmaske (~1 km) macht enge Fahrwasser (Puget Sound, Deception
Pass) und Tidefluesse zu Land -- 828 von 4981 Stroemungen standen dort "an Land". Die OSM-Kueste
folgt Aestuaren und Engen auf wenige Meter.

Daten: harmonics/help/osm/landpolygone/land-polygons-split-4326/land_polygons.shp (~1 GB entpackt;
nicht im Git). Laden: curl -L -O https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip

    L = Land(punkte)              # nur Polygone im Umkreis der Punkte (Grad-Kacheln) werden geladen
    L.ist_land(lat, lon)
    L.kueste_km(lat, lon)         # Abstand zur Kueste (Polygonrand) in km
    L.breite_km(lat, lon, grad)   # Wasserbreite quer zu einer Richtung (bis 10 km je Seite)
"""
import math
import os

import shapefile
from shapely.geometry import LineString, Point, shape
from shapely.ops import nearest_points, unary_union
from shapely.strtree import STRtree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHP = os.path.join(ROOT, 'harmonics/help/osm/landpolygone/land-polygons-split-4326/land_polygons.shp')


def km(la1, lo1, la2, lo2):
    return math.hypot((la2 - la1) * 111.2, (lo2 - lo1) * 111.2 * math.cos(math.radians((la1 + la2) / 2)))


class Land:
    def __init__(self, punkte, rand=0.15):
        kacheln = {(math.floor(la), math.floor(lo)) for la, lo in punkte}
        r = shapefile.Reader(SHP)
        geo = []
        for sh in r.iterShapes():
            x0, y0, x1, y1 = sh.bbox
            if any((a, b) in kacheln for a in range(math.floor(y0 - rand), math.floor(y1 + rand) + 1)
                   for b in range(math.floor(x0 - rand), math.floor(x1 + rand) + 1)):
                geo.append(shape(sh.__geo_interface__))
        self.geo = geo
        self.baum = STRtree(geo)

    def _treffer(self, g):
        return [self.geo[i] for i in self.baum.query(g)]

    def ist_land(self, la, lo):
        p = Point(lo, la)
        return any(g.contains(p) for g in self._treffer(p))

    def kueste_km(self, la, lo, rmax=10.0):
        """Abstand zum naechsten Polygonrand (Kueste) in km, hoechstens rmax."""
        p = Point(lo, la)
        best = rmax
        box = p.buffer(rmax / 111.2 / max(0.2, math.cos(math.radians(la))))
        teile = self._treffer(box)
        if not teile:
            return best
        # Schnittkanten der geteilten Polygone liegen im Land: erst vereinigen, dann den Rand messen
        rand = unary_union(teile).boundary
        if rand.is_empty:
            return best
        q = nearest_points(p, rand)[1]
        return min(best, km(la, lo, q.y, q.x))

    def breite_km(self, la, lo, richtung, rmax=10.0):
        """Wasserstrecke quer zur Richtung (Grad) bis zum ersten Land je Seite, je Seite hoechstens rmax."""
        if richtung is None:
            return None
        p, w = Point(lo, la), 0.0
        for seite in (90, -90):
            a = math.radians(richtung + seite)
            q = (lo + rmax * math.sin(a) / (111.2 * math.cos(math.radians(la))), la + rmax * math.cos(a) / 111.2)
            strahl = LineString([(lo, la), q])
            d = rmax
            for g in self._treffer(strahl):
                x = g.intersection(strahl)
                if not x.is_empty:
                    n = nearest_points(p, x)[1]
                    d = min(d, km(la, lo, n.y, n.x))
            w += d
        return w
