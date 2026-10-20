#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stroemungskonstanten aus den SHOM-Atlanten "courants de maree 2D netcdf" (Oliver 20.10.2026).

Die Atlanten (Licence Ouverte Etalab 2.0, Quelle: "Shom, 2026. Atlas de courants de maree 2D
au format netcdf, https://dx.doi.org/10.17183/ATLASCOURANTS2D_NETCDF") geben U/V der
Oberflaeche von -6 h bis +6 h um die Pleine Mer (bei Le Havre: Basse Mer) eines Bezugshafens,
je fuer Koeffizient 45 (morte-eau) und 95 (vive-eau). Modellwerte, keine Messung.

Umrechnung wie die SHOM-Gebrauchsanweisung der Atlanten:
  1. PM/BM des Bezugshafens fuer ein Jahr aus unserem Satz (REFMAR-Fit) vorausrechnen,
  2. Koeffizient jeder Tide aus dem Brester Tidenhub (U = 3,05 m),
  3. Strom zur Zeit t = Atlaswert zur Stunde (t - PM) bei diesem Koeffizienten, linear
     zwischen 45 und 95 inter-/extrapoliert,
  4. die so gebaute Jahresreihe wie eine Messreihe fitten (cmems_stroemung_nachholen.analyse).

Usage: venv/bin/python py/shom_atlas_stroemung.py ATLAS.nc LAT LON   (Probe eines Punkts)
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import netCDF4
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_observations.txt')
TAFELN = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
# Bezugshafen der Atlanten (Attribut Portref) -> unser Satz
HAFEN = {'CHERBOURG': (TAFELN, 'Cherbourg-en-Cotentin, France'),
         'CALAIS': (OBS, 'Calais, France'),
         'BOULOGNE': (TAFELN, 'Boulogne-sur-Mer, France'),
         'DUNKERQUE': (OBS, 'Dunkerque, France'),
         'SAINT-MALO': (OBS, 'Saint-Malo, France'),
         'ROSCOFF': (OBS, 'Roscoff, France'),
         'BREST': (OBS, 'Brest (Estuaire Penfeld), France'),
         'CONCARNEAU': (OBS, 'Concarneau, France'),
         'LE HAVRE': (OBS, 'Le Havre (Marégraphe), France')}
BREST = HAFEN['BREST']
U_BREST = 3.05            # Unite de hauteur Brest (m)
# Nur halbtaegige Familie und Obertiden: der Atlas kennt keine Eintagestiden.
KONST = ['M2', 'S2', 'N2', 'K2', '2N2', 'MU2', 'NU2', 'L2', 'T2', 'LDA2', 'EPS2', 'MSN2',
         'M4', 'MS4', 'MN4', 'MK4', 'S4', 'SN4', 'M6', '2MS6', '2MN6', 'MSN6', 'M8', 'MSF', 'MM']
_KOPF = {}


def _hafen_finden(name):
    """Datei des Satzes suchen (in OBS oder TAFELN)."""
    for pfad in (OBS, TAFELN):
        try:
            X.satz_lesen(pfad, name)
            return pfad
        except KeyError:
            pass
    raise KeyError(name)


def gezeit(pfad, name, zeiten):
    """Hoehe (m) zu UNIX-Zeiten nach XTide-Modell."""
    if pfad not in _KOPF:
        _KOPF[pfad] = X.kopf_lesen(pfad)
    namen, speeds, arg, fak = _KOPF[pfad]
    z0, werte, einheit, mer = X.satz_lesen(pfad, name)
    eigen = {k: (a, X.greenwich(kap, speeds[k], mer)) for k, (a, kap) in werte.items()}
    return X.kurve(zeiten, z0, eigen, namen, speeds, arg, fak, 0.3048 if einheit.startswith('f') else 1.0)


def scheitel(t, h, hoch=True, abstand_h=4.0):
    """Hoch- (oder Niedrig-)wasser: Maxima mit Parabelverfeinerung, mind. abstand_h auseinander."""
    y = h if hoch else -h
    i = np.where((y[1:-1] > y[:-2]) & (y[1:-1] >= y[2:]))[0] + 1
    dt_s = t[1] - t[0]
    tz, hz = [], []
    for k in i:
        a, b, c = y[k - 1], y[k], y[k + 1]
        d = a - 2 * b + c
        x = 0.5 * (a - c) / d if d else 0.0
        tz.append(t[k] + x * dt_s)
        hz.append(b - 0.25 * (a - c) * x)
    tz, hz = np.array(tz), np.array(hz)
    # Doppelscheitel (Stauwasser) zusammenfassen: hoechsten im Fenster behalten
    keep = []
    for k in np.argsort(-hz):
        if all(abs(tz[k] - tz[j]) > abs_h(abstand_h) for j in keep):
            keep.append(k)
    keep = sorted(keep)
    return tz[keep], (hz[keep] if hoch else -hz[keep])


def abs_h(h):
    return h * 3600.0


def koeffizient(jahr):
    """-> (Zeiten der Brester PM, Koeffizient) fuer das Jahr (+-2 Tage Rand)."""
    t0 = dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp() - 2 * 86400
    t = np.arange(t0, t0 + 370 * 86400, 300.0)
    p = _hafen_finden(BREST[1])
    h = gezeit(p, BREST[1], t)
    th, hh = scheitel(t, h, True)
    tl, hl = scheitel(t, h, False)
    lw = np.interp(th, tl, hl)        # mittleres NW um die PM
    return th, 100.0 * (hh - lw) / 2.0 / U_BREST


class Atlas:
    def __init__(self, pfad):
        self.pfad = pfad
        d = netCDF4.Dataset(pfad)
        self.port = d.getncattr('Portref').strip().upper().replace('-', ' ')
        if self.port == 'SAINT MALO':
            self.port = 'SAINT-MALO'
        self.bm = int(getattr(d, 'isBM', 0)) == 1
        self.lat = d['latitude'][:].astype(float)
        self.lon = d['longitude'][:].astype(float)
        self.coeff = [int(x) for x in d['coeff'][:]]
        self.tau = d['time'][:].astype(float) - 360.0          # Minuten zur PM/BM
        self.d = d

    def zelle(self, lat, lon, max_km=3.0):
        """Naechste Gitterzelle mit Werten -> (j, i, lat, lon) oder None."""
        jj = np.argsort(np.abs(self.lat - lat))[:12]
        ii = np.argsort(np.abs(self.lon - lon))[:12]
        best = None
        U = self.d['U']
        for j in jj:
            for i in ii:
                km = np.hypot((self.lat[j] - lat) * 111.2, (self.lon[i] - lon) * 111.2 * np.cos(np.radians(lat)))
                if km > max_km or (best and km >= best[0]):
                    continue
                if np.ma.is_masked(U[0, 0, 0, j, i]) or U[0, 0, 0, j, i] < -999:
                    continue
                best = (km, j, i)
        if not best:
            return None
        return best[1], best[2], float(self.lat[best[1]]), float(self.lon[best[2]])

    def zyklus(self, j, i):
        """-> u, v je (coeff, tau) in m/s."""
        u = np.asarray(self.d['U'][:, :, 0, j, i], dtype=float)
        v = np.asarray(self.d['V'][:, :, 0, j, i], dtype=float)
        return u, v


def reihe(atlas, j, i, jahr=2026, schritt_min=10, versatz_min=0.0):
    """Synthetische Jahresreihe nach der Atlas-Regel.

    versatz_min: Zeitkorrektur des Atlas (negativ = Strom kommt frueher als der Atlas sagt).
    """
    pfad = _hafen_finden(HAFEN[atlas.port][1])
    t0 = dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t = np.arange(t0 - 86400, t0 + 366 * 86400, 120.0)
    h = gezeit(pfad, HAFEN[atlas.port][1], t)
    tp, _ = scheitel(t, h, not atlas.bm)
    tp = tp + versatz_min * 60.0
    tb, kb = koeffizient(jahr)
    kp = np.interp(tp, tb, kb)
    ts = np.arange(t0, t0 + 365 * 86400, schritt_min * 60.0)
    k = np.searchsorted(tp, ts)
    k = np.clip(k, 1, len(tp) - 1)
    k -= (ts - tp[k - 1]) < (tp[k] - ts)                     # naechste PM
    tau = np.clip((ts - tp[k]) / 60.0, atlas.tau[0], atlas.tau[-1])
    w = (kp[k] - atlas.coeff[0]) / (atlas.coeff[1] - atlas.coeff[0])
    u, v = atlas.zyklus(j, i)
    uu = np.interp(tau, atlas.tau, u[0]) * (1 - w) + np.interp(tau, atlas.tau, u[1]) * w
    vv = np.interp(tau, atlas.tau, v[0]) * (1 - w) + np.interp(tau, atlas.tau, v[1]) * w
    idx = pd.to_datetime(ts, unit='s')
    return pd.DataFrame({'u': uu, 'v': vv}, index=idx)


def fit(atlas, lat, lon, jahr=2026, versatz_min=0.0, max_km=3.0):
    z = atlas.zelle(lat, lon, max_km)
    if not z:
        return None
    j, i, la, lo = z
    df = reihe(atlas, j, i, jahr, versatz_min=versatz_min)
    r = C.analyse(df, la, KONST)
    r['lat'], r['lon'] = la, lo
    return r


if __name__ == '__main__':
    a = Atlas(sys.argv[1])
    r = fit(a, float(sys.argv[2]), float(sys.argv[3]))
    print(a.port, 'BM' if a.bm else 'PM', r and {k: r[k] for k in ('lat', 'lon', 'achse', 'r2', 'm2', 's2')})
    if r:
        for k in ('M2', 'S2', 'N2', 'K2', 'M4', 'MS4'):
            print(' ', k, r['konst'].get(k))
