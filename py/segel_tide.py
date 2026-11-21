#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tidenhoehe ueber LAT fuer das Segel-Routing (Oliver 21.11.2026: Watt/Barren bei Hochwasser befahrbar).

    H = hoehe_ueber_lat(LAT2, LON2, zeiten)  -> (len(zeiten), ny, nx) m ueber LAT, oder None (kein Pegel in Reichweite)

Je Pegel (Wasserstandssatz im Bestand, <= REICHWEITE km vom Gebiet): Gezeitenkurve aus den eigenen Konstanten, auf
LAT bezogen ueber das Minimum eines Jahres (stuendlich 2026) -- damit ist das Datum der Harmonics-Datei (MLLW, NAP, PNP,
Seekartennull ...) gleichgueltig. EMODnet-Tiefen beziehen sich ebenfalls auf LAT. Je Knoten inverse Distanz der
3 naechsten Pegel (bis REICHWEITE); ohne Pegel 0 (= wie bisher bei LAT, vorsichtig).
Windstau und Luftdruck fehlen; der Router behaelt die Tiefenreserve.
"""
import datetime as dt
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REICHWEITE = 30.0
_KURVE = {}


def _pegel(s, n, w, e):
    import health_check as H
    rand = REICHWEITE / 111.2
    return [r for r in H.load_records() if not r['current'] and r['lat'] is not None
            and s - rand < r['lat'] < n + rand and w - rand / math.cos(math.radians(r['lat'])) < r['lon'] < e + rand / math.cos(math.radians(r['lat']))]


def _ueber_lat(r, zeiten):
    """Hoehe ueber dem Jahresminimum (≈ LAT) zu den Zeiten; None bei unbrauchbarem Satz."""
    import xtide_modell as X
    k = (r['file'], r['name'])
    if k not in _KURVE:
        try:
            z0, w, einheit, mer = X.satz_lesen(r['file'], r['name'])
            namen, speeds, arg, fak = X.kopf_lesen(r['file'])
        except Exception:
            _KURVE[k] = None
            return None
        f = 0.3048 if str(einheit).startswith('f') else 1.0
        g = {c: (a, X.greenwich(p, speeds[c], mer)) for c, (a, p) in w.items() if c in speeds}
        if 'M2' not in g:
            _KURVE[k] = None
            return None
        jahr = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp() + 3600.0 * np.arange(365 * 24)
        lat = float(np.min(X.kurve(jahr, 0.0, g, namen, speeds, arg, fak))) * f
        _KURVE[k] = (g, f, lat, (namen, speeds, arg, fak))
    if _KURVE[k] is None:
        return None
    g, f, lat, kopf = _KURVE[k]
    import xtide_modell as X
    return X.kurve(np.asarray(zeiten, float), 0.0, g, *kopf) * f - lat


def hoehe_ueber_lat(LAT2, LON2, zeiten):
    s, n, w, e = LAT2.min(), LAT2.max(), LON2.min(), LON2.max()
    P = _pegel(s, n, w, e)
    kurven, la, lo = [], [], []
    for r in P:
        c = _ueber_lat(r, zeiten)
        if c is not None and np.all(np.isfinite(c)) and np.ptp(c) > 0.05:
            kurven.append(c)
            la.append(r['lat'])
            lo.append(r['lon'])
    if not kurven:
        return None, 0
    K = np.array(kurven)                                     # (pegel, zeit)
    la, lo = np.array(la), np.array(lo)
    kx = 111.2 * math.cos(math.radians((s + n) / 2))
    d = np.hypot((LAT2[..., None] - la) * 111.2, (LON2[..., None] - lo) * kx)        # (ny, nx, pegel)
    m = min(3, len(la))
    idx = np.argsort(d, axis=-1)[..., :m]
    dd = np.take_along_axis(d, idx, -1)
    gew = np.where(dd <= REICHWEITE, 1.0 / np.maximum(dd, 0.5) ** 2, 0.0)
    summe = gew.sum(-1)
    out = np.zeros((len(zeiten),) + LAT2.shape, np.float32)
    for q in range(m):
        out += (K[idx[..., q]].transpose(2, 0, 1) * (gew[..., q] / np.maximum(summe, 1e-9))[None])
    out[:, summe == 0] = 0.0
    return out, len(la)
