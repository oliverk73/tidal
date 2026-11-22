#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tidenhoehe ueber LAT fuer das Segel-Routing (Oliver 21.11.2026: Watt/Barren bei Hochwasser befahrbar).

    H = hoehe_ueber_lat(LAT2, LON2, zeiten)  -> (len(zeiten), ny, nx) m ueber LAT, oder None (kein Pegel in Reichweite)

Je Pegel (Wasserstandssatz im Bestand, <= REICHWEITE km vom Gebiet): Gezeitenkurve aus den eigenen Konstanten, auf
LAT bezogen ueber das Minimum eines Jahres (stuendlich 2026) -- damit ist das Datum der Harmonics-Datei (MLLW, NAP, PNP,
Seekartennull ...) gleichgueltig. EMODnet-Tiefen beziehen sich ebenfalls auf LAT. Je Knoten inverse Distanz der
3 naechsten Pegel (bis REICHWEITE); ohne Pegel 0 (= wie bisher bei LAT, vorsichtig).
Windstau (22.11.2026): je Pegel die Windstau-Vorhersage der Tidenseite (windstau.fuer_satz: Copernicus Ostsee/
Mittelmeer/Schwarzes Meer/Nordsee, sonst NOAA STOFS <= 5 km) zur Zeit addiert; ausserhalb des Vorhersagefensters 0.
Positiver Stau (mehr Wasser) nur bis 48 h nach dem Modelllauf, negativer immer (Sicherheitsseite).
Der Router behaelt trotzdem die Tiefenreserve (Modellfehler, Seegang).

    H, n_pegel, stau = hoehe_ueber_lat(LAT2, LON2, zeiten, windstau=True)
    stau = dict(n=Pegel mit Windstau, min/max [m], quellen, lauf) oder None
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


def _stau(r, zeiten):
    """Windstau [m] zu den Zeiten (0 ausserhalb der Vorhersage) + Quelle/Lauf, oder None."""
    try:
        import windstau
        w = windstau.fuer_satz(r['file'], r['name'], r['lat'], r['lon'])
    except Exception:  # noqa: BLE001
        return None
    if not w:
        return None
    t, z = np.asarray(w['t'], float), np.asarray(w['z'], float)
    ok = np.isfinite(z) & (np.abs(z) < 5)
    if ok.sum() < 6:
        return None
    t, z = t[ok], z[ok]
    zt = np.asarray(zeiten, float)
    if zt.max() < t[0] or zt.min() > t[-1]:
        return None
    v = np.nan_to_num(np.interp(zt, t, z, left=np.nan, right=np.nan), nan=0.0)
    # Sicherheitsseite: Hochwasser durch Stau nur bis 48 h nach dem Modelllauf anrechnen (die Laeufe werden von Hand
    # geholt und koennen Tage alt sein), Niedrigwasser durch Stau immer
    try:
        lauf = dt.datetime.fromisoformat(str(w.get('lauf', ''))[:16]).replace(tzinfo=dt.timezone.utc).timestamp()
    except ValueError:
        lauf = None
    if lauf is None:
        v = np.minimum(v, 0.0)
    else:
        v = np.where(zt - lauf > 48 * 3600.0, np.minimum(v, 0.0), v)
    return v, w.get('quelle', 'stofs'), w.get('lauf', '')


def hoehe_ueber_lat(LAT2, LON2, zeiten, windstau=True):
    s, n, w, e = LAT2.min(), LAT2.max(), LON2.min(), LON2.max()
    P = _pegel(s, n, w, e)
    kurven, la, lo = [], [], []
    stau = dict(n=0, quellen=set(), lauf=set(), min=0.0, max=0.0)
    for r in P:
        c = _ueber_lat(r, zeiten)
        if c is not None and np.all(np.isfinite(c)) and np.ptp(c) > 0.05:
            st = _stau(r, zeiten) if windstau else None
            if st is not None:
                c = c + st[0]
                stau['n'] += 1
                stau['quellen'].add(st[1])
                stau['lauf'].add(str(st[2])[:16])
                stau['min'] = min(stau['min'], float(st[0].min()))
                stau['max'] = max(stau['max'], float(st[0].max()))
            kurven.append(c)
            la.append(r['lat'])
            lo.append(r['lon'])
    if not kurven:
        return None, 0, None
    stau = (dict(stau, quellen=sorted(stau['quellen']), lauf=sorted(stau['lauf']), min=round(stau['min'], 2),
                 max=round(stau['max'], 2)) if stau['n'] else None)
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
    return out, len(la), stau
