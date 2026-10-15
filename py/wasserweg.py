#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kuerzester Weg zwischen zwei Pegeln durchs Wasser (nicht Luftlinie).

Oliver 15.10.2026: "nicht reine Luftlinie, sondern den Verlauf des Wassers an der Kueste zwischen den
Stationen beruecksichtigen". Die Tide braucht von Pegel zu Pegel so lange, wie sie durchs Wasser
laeuft -- um eine Insel herum (Labuha/Babang auf Bacan), einen Fluss hinauf (Palembang), durch eine
Buchteinfahrt (Klabat).

Verfahren: Raster (~220 m) um beide Punkte; Zelle ist Wasser, wenn sie nach der OSM-Kuestenlinie auf
der Seeseite liegt oder in einer OSM-Gewaesserflaeche (Fluss, Becken). Dann Dijkstra mit 8 Nachbarn.
Kein Weg -> None (getrennte Gewaesser, z. B. ein Damm). Ohne OSM-Auszug des Landes -> None.

Braucht pruefe_namen_positionen mit dem Auszug des Landes (PRUEF_LAND).
"""
import heapq
import math

ZELLE = 0.002          # Grad, ~220 m
RAND = 0.06            # Grad Rand um die beiden Punkte, plus halber Abstand
_P = None
_CACHE = {}


def _p():
    global _P
    if _P is None:
        import pruefe_namen_positionen as P
        _P = P
    return _P


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians((a[0] + b[0]) / 2)))


def wasserweg_km(a, b, max_faktor=6.0, rand_extra=None, zelle_grad=None):
    """a, b = (lat, lon) -> Wasserweg in km oder None (kein Weg / kein Auszug)."""
    key = (round(a[0], 4), round(a[1], 4), round(b[0], 4), round(b[1], 4))
    if key in _CACHE:
        return _CACHE[key]
    try:
        P = _p()
    except Exception:  # noqa: BLE001
        return None
    luft = km(a, b)
    ZELLE = zelle_grad or globals()['ZELLE']
    rand = (RAND if rand_extra is None else rand_extra) + 0.5 * max(abs(a[0] - b[0]), abs(a[1] - b[1]))
    la0, la1 = min(a[0], b[0]) - rand, max(a[0], b[0]) + rand
    lo0, lo1 = min(a[1], b[1]) - rand, max(a[1], b[1]) + rand
    ny, nx = int((la1 - la0) / ZELLE) + 1, int((lo1 - lo0) / ZELLE) + 1
    wasser = {}

    def ist_wasser(i, j):
        k = (i, j)
        if k not in wasser:
            lat, lon = la0 + i * ZELLE, lo0 + j * ZELLE
            d, seite = P.kueste(lat, lon)
            wasser[k] = seite == 'wasser' or bool(P.im_gewaesser(lat, lon))
        return wasser[k]

    zelle = lambda p: (int(round((p[0] - la0) / ZELLE)), int(round((p[1] - lo0) / ZELLE)))
    s, z = zelle(a), zelle(b)
    wasser[s] = wasser[z] = True                       # Pegel stehen am Wasser
    dy = ZELLE * 111.2
    dx = ZELLE * 111.2 * math.cos(math.radians((a[0] + b[0]) / 2))
    schritte = [(di, dj, math.hypot(di * dy, dj * dx)) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj]
    dist = {s: 0.0}
    heap = [(km(a, b), 0.0, s)]                         # A*: Luftlinie als Schaetzung
    ziel_ll = b
    grenze = max(luft * max_faktor, luft + 15)
    while heap:
        f, g, c = heapq.heappop(heap)
        if c == z:
            _CACHE[key] = g
            return g
        if g > dist.get(c, 1e18) or g > grenze:
            continue
        for di, dj, w in schritte:
            n = (c[0] + di, c[1] + dj)
            if not (0 <= n[0] < ny and 0 <= n[1] < nx) or not ist_wasser(*n):
                continue
            ng = g + w
            if ng < dist.get(n, 1e18):
                dist[n] = ng
                h = km((la0 + n[0] * ZELLE, lo0 + n[1] * ZELLE), ziel_ll)
                heapq.heappush(heap, (ng + h, ng, n))
    if rand_extra is None:
        # kein Weg im engen Fenster: weiter ausholen (um eine Insel herum, Labuha/Babang auf Bacan)
        r = wasserweg_km(a, b, max_faktor, rand_extra=0.4, zelle_grad=0.008)   # grob (~900 m), aber weit
        _CACHE[key] = r
        return r
    _CACHE[key] = None
    return None


if __name__ == '__main__':
    import os
    import sys
    os.environ.setdefault('PRUEF_LAND', sys.argv[1])
    a = tuple(map(float, sys.argv[2].split(',')))
    b = tuple(map(float, sys.argv[3].split(',')))
    print('Luftlinie %.1f km, Wasserweg %s km' % (km(a, b), wasserweg_km(a, b)))
