#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kartenebene "Tidal Currents": Gezeitenstrom aus TPXO10-atlas-v2 fuer einen Kartenausschnitt und eine Zeit
(Oliver 13.11.2026: "Baue die Stroemungslayer!").

Gerechnet wird beim Abruf (app.py /api/tidal_current), nichts vorberechnet: die u-Dateien (U/V-Transporte, m^2/s) werden
als memmap mit Schrittweite gelesen, durch die Tiefe hz geteilt und mit Knotenfaktor f und Argument V0+u des Jahres
(xtide_modell.kopf_lesen, wie die Tidenrechnung) zur Zeit t summiert:  u(t) = sum f * Re(c * e^{i(V0+u + w*t)}),
c = re + i*im = a*e^{-ig}.  Ausgabe im leaflet-velocity-Format (wie static/ocean_currents), Land = null.

Pruefung (py/tpxo_strom.py, 664 Messsaetze): Kurvenfehler Median 8 % auf offener See/Schelf, an Kaps, Engstellen
und Buchten 20-36 %. Die Ebene zeigt deshalb Zellen, deren Nachbarn mehr als UNSICHER % abweichen, nicht an.

Test: venv/bin/python py/tpxo_strom_karte.py 50 52 0 3 2026-11-13T12:00
"""
import datetime as dt
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'tide_models/TPXO10_atlas_v2')
NX, NY = 10800, 5401
KS = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4')
MAX_ZELLEN = 240            # je Achse; feiner als 1/30 Grad geht nicht
UNSICHER = 50.0             # Nachbarzellen-Unterschied M2 in %, ab dem die Zelle ausgeblendet wird
MIN_TIEFE = 2.0
FEIN_DX = 1 / 240.0         # feinstes Ausgaberaster, wo ein feines Modell deckt (~460 m)
_F, _K = {}, {}


def _u(k):
    if k not in _F:
        _F[k] = np.memmap(os.path.join(D, 'u_%s_tpxo10_atlas_30_v2' % k.lower()), dtype='>f4', mode='r', offset=44, shape=(NY, NX, 4))
    return _F[k]


def _hz():
    if 'hz' not in _F:
        _F['hz'] = np.memmap(os.path.join(D, 'grid_tpxo10_atlas_30_v2'), dtype='>f4', mode='r', offset=56, shape=(NY, NX))
    return _F['hz']


def _kopf():
    if not _K:
        namen, speeds, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
        _K.update(speeds=speeds, arg=arg, fak=fak)
    return _K


def _lesen(arr, ii, jj):
    """arr[ii][:, jj] ohne ganze Zeilen zu laden: Zeilen und Spalten als Schritt-Slices (Spalten ggf. ueber 0/360)."""
    s_i = ii[1] - ii[0] if len(ii) > 1 else -1
    zeilen = slice(ii[0], ii[-1] + (1 if s_i > 0 else -1) if ii[-1] + (1 if s_i > 0 else -1) >= 0 else None, s_i)
    s_j = int(jj[1] - jj[0]) % NX if len(jj) > 1 else 1
    teile, k = [], 0
    while k < len(jj):
        a = int(jj[k])
        n = min(len(jj) - k, (NX - 1 - a) // s_j + 1)
        teile.append(np.asarray(arr[zeilen, a:a + (n - 1) * s_j + 1:s_j]))
        k += n
    return np.concatenate(teile, axis=1) if len(teile) > 1 else teile[0]


def feld(la_s, la_n, lo_w, lo_e, t, max_zellen=MAX_ZELLEN, ozean=False, kueste=False, roh=False):
    """-> leaflet-velocity-Liste [u, v] in m/s fuer den Ausschnitt zur Zeit t (datetime UTC).
    ozean=True: Ozeanstrom ohne Gezeiten (Copernicus GLO12, py/ozeanstrom.py) dazu = „Total current“ (20.11.2026).
    kueste=True (nur Karte): Feld auf Bildschirmaufloesung verfeinern, bis an die OSM-Kueste auffuellen; drittes Feld
    'filled' (1 = aus dem naechsten gueltigen Wert geschaetzt, Karte zeichnet blasser), Oliver 21.11.2026."""
    la_s, la_n = max(-89.0, min(la_s, la_n)), min(89.0, max(la_s, la_n))
    if lo_e <= lo_w:
        lo_e += 360.0
    breite = min(360.0, lo_e - lo_w)
    s = max(1, int(math.ceil(max((la_n - la_s) * 30 / max_zellen, breite * 30 / max_zellen))))
    i_s, i_n = int(math.floor((la_s + 90) * 30)), int(math.ceil((la_n + 90) * 30))
    ii = np.arange(i_n, i_s - 1, -s)                               # Nord -> Sued
    ii = ii[(ii > 0) & (ii < NY - 1)]
    j0 = int(math.floor((lo_w % 360.0) * 30 - 1))
    nj = int(math.ceil(breite * 30 / s)) + 1
    jj = (j0 + np.arange(nj) * s) % NX
    hz = _lesen(_hz(), ii, jj).astype('f8')
    kopf = _kopf()
    jahr = t.year
    th = (t - dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc)).total_seconds() / 3600.0
    u = np.zeros(hz.shape)
    v = np.zeros(hz.shape)
    m2 = None
    for k in KS:
        F = _u(k)
        blk = _lesen(F, ii, jj).astype('f8')                         # (ny, nx, 4)
        E = math.radians(kopf['arg'][jahr][k] + kopf['speeds'][k] * th)
        f = kopf['fak'][jahr][k]
        u += f * (blk[..., 0] * math.cos(E) - blk[..., 1] * math.sin(E))
        v += f * (blk[..., 2] * math.cos(E) - blk[..., 3] * math.sin(E))
        if k == 'M2':
            m2 = blk
    with np.errstate(divide='ignore', invalid='ignore'):
        u, v = u / hz, v / hz
    land = ~(hz >= MIN_TIEFE)
    # Unsichere Zellen (Kap, Engstelle, Bucht): M2-Vektor weicht von den Nachbarn um > UNSICHER % ab
    if m2 is not None:
        with np.errstate(divide='ignore', invalid='ignore'):
            c = m2 / hz[..., None]
        n = np.sqrt((c ** 2).sum(-1))
        g = np.zeros(hz.shape)
        for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            d = np.sqrt(((c - np.roll(np.roll(c, a, 0), b, 1)) ** 2).sum(-1))
            g = np.maximum(g, np.where(np.isfinite(d), d, 0))
        with np.errstate(divide='ignore', invalid='ignore'):
            unsicher = (s == 1) & (100 * g / n > UNSICHER)
        land |= unsicher
    u[land] = np.nan
    v[land] = np.nan
    lo1 = ((j0 + 1) / 30.0 + 180) % 360 - 180
    dx = s / 30.0
    la1 = -90 + ii[0] / 30.0
    la2 = -90 + ii[-1] / 30.0
    # Feine Modelle (SSW-RS, AUSTEn; py/strom_feinfeld.py, 19.11.2026): wo sie decken, ersetzen sie TPXO. Beim
    # Hineinzoomen wird das Ausgaberaster dann feiner als TPXO (bis FEIN_DX), TPXO wird dafuer naechstwertig verfeinert.
    try:
        import strom_feinfeld as FF
        S = FF._laden()
    except Exception:                                              # noqa: BLE001 - Ebene soll ohne Feinfeld weiterlaufen
        S = None
    fein_wasser = None
    if S:
        im_box = ((S['lat'] >= la_s) & (S['lat'] <= la_n) & (((S['lon'] - lo_w) % 360) <= breite))
        if im_box.any():
            wunsch = max((la_n - la_s) / max_zellen, breite / max_zellen, FEIN_DX)
            if wunsch < dx:
                f = int(round(dx / wunsch))
                ny, nx = (len(ii) - 1) * f + 1, (nj - 1) * f + 1
                u = np.repeat(np.repeat(u, f, 0), f, 1)[:ny, :nx]
                v = np.repeat(np.repeat(v, f, 0), f, 1)[:ny, :nx]
                dx = dx / f
                nj = nx
                ii = ii[0] - np.arange(ny) * (s / f)                 # nur fuer la1/la2 und Zeilenzahl
                la2 = la1 - dx * (ny - 1)
            lat = la1 - dx * np.arange(len(ii))
            lon = lo1 + dx * np.arange(nj)
            u, v, _n, fein_wasser = FF.einsetzen(lat, lon, u, v, th, kopf, jahr, maske=True)
    if ozean:
        import ozeanstrom
        la_g = la1 - dx * np.arange(u.shape[0])
        lo_g = lo1 + dx * np.arange(u.shape[1])
        LA, LO = np.meshgrid(la_g, lo_g, indexing='ij')
        r = ozeanstrom.uv(LA, LO, t.timestamp())
        if r is not None:                                          # ausserhalb des Vorhersagezeitraums: nur Gezeit
            u, v = u + r[0], v + r[1]
    gefuellt = None
    if kueste:
        r_ = _kueste(u, v, la1, lo1, dx, max((la_n - la_s) / max_zellen, breite / max_zellen), fein_wasser)
        if r_ is not None:
            u, v, gefuellt, dx = r_
            nj, la2 = u.shape[1], la1 - dx * (u.shape[0] - 1)
            ii = np.arange(u.shape[0])
    kopfz = dict(lo1=round(lo1, 5), lo2=round(lo1 + dx * (nj - 1), 5), la1=round(la1, 5), la2=round(la2, 5),
                 dx=round(dx, 6), dy=round(dx, 6), nx=int(nj), ny=int(len(ii)), refTime=t.strftime('%Y-%m-%dT%H:%M:%SZ'),
                 forecastTime=0, scanMode=0, parameterCategory=2, parameterUnit='m.s-1')

    if roh:                                  # 23.11.2026: Binaerformat der Karte (app.py fmt=bin), ohne Python-Listen
        return dict(header=kopfz, u=u, v=v, f=gefuellt)

    def liste(a):
        return [None if not np.isfinite(x) else round(float(x), 3) for x in a.ravel()]
    out = [dict(header=dict(kopfz, parameterNumber=2, parameterNumberName='eastward_tidal_current'), data=liste(u)),
           dict(header=dict(kopfz, parameterNumber=3, parameterNumberName='northward_tidal_current'), data=liste(v))]
    if gefuellt is not None:
        out.append(dict(header=dict(kopfz, parameterNumber=0, parameterNumberName='filled'), data=gefuellt.astype(int).ravel().tolist()))
    return out


_LAND = {}
import threading as _threading
_LAND_SPERRE = _threading.Lock()
FUELL_KM = 15.0          # Kuestenstreifen, der aus dem naechsten gueltigen Wert gefuellt wird
KUESTE_MAX_GRAD = 6.0    # nur bis zu diesem Ausschnitt (Landmaske je Anfrage)


def _kueste(u, v, la1, lo1, dx, wunsch, fein_wasser=None):
    """Fransen an der Kueste (Oliver 21.11.2026): Die Karte interpolierte bilinear und zeichnete, solange die
    gueltigen Ecken >= 30 % Gewicht hatten -> Boegen im TPXO-Zellabstand. Jetzt: Feld NaN-bewusst bilinear auf
    Bildschirmaufloesung, OSM-Landmaske (py/segel_land.py) dieser Aufloesung, Wasser ohne Modellwert aus dem
    naechsten gueltigen Punkt (bis FUELL_KM), Land leer. -> (u, v, gefuellt, dx) oder None."""
    from scipy import ndimage
    ny, nx = u.shape
    if (ny - 1) * dx > KUESTE_MAX_GRAD or (nx - 1) * dx > KUESTE_MAX_GRAD:
        return None
    f = max(1, int(round(dx / max(wunsch, 1e-6))))
    if f > 1:                                                     # NaN-bewusst bilinear verfeinern
        yi = np.arange((ny - 1) * f + 1) / f
        xi = np.arange((nx - 1) * f + 1) / f
        j0 = np.minimum(np.floor(yi).astype(int), ny - 2); fy = (yi - j0)[:, None]
        i0 = np.minimum(np.floor(xi).astype(int), nx - 2); fx = (xi - i0)[None, :]
        su, sv, sw = 0.0, 0.0, 0.0
        for dj, di, w in ((0, 0, (1 - fy) * (1 - fx)), (0, 1, (1 - fy) * fx), (1, 0, fy * (1 - fx)), (1, 1, fy * fx)):
            uu = u[np.ix_(j0 + dj, i0 + di)]
            vv = v[np.ix_(j0 + dj, i0 + di)]
            ok = np.isfinite(uu)
            su = su + np.where(ok, w * uu, 0.0)
            sv = sv + np.where(ok, w * vv, 0.0)
            sw = sw + np.where(ok, w, 0.0)
        with np.errstate(divide='ignore', invalid='ignore'):
            u, v = np.where(sw > 1e-6, su / sw, np.nan), np.where(sw > 1e-6, sv / sw, np.nan)
        if fein_wasser is not None:
            fein_wasser = fein_wasser[np.ix_(np.rint(yi).astype(int), np.rint(xi).astype(int))]
        dx = dx / f
        ny, nx = u.shape
    try:
        import segel_land
        sch = (round(la1, 6), round(lo1, 6), round(dx, 8), ny, nx)
        with _LAND_SPERRE:                   # gleichzeitige Anfragen desselben Ausschnitts rechnen sie nur einmal
            land = _LAND.get(sch)
            if land is None:                 # je Ausschnitt einmal (alle Zeitschritte gleich), 23.11.2026
                land = segel_land.raster(la1 - dx * (ny - 0.5), la1 + dx / 2, lo1 - dx / 2, lo1 + dx * (nx - 0.5), ny, nx)
                if len(_LAND) >= 16:
                    _LAND.pop(next(iter(_LAND)))
                _LAND[sch] = land
    except Exception:                                              # noqa: BLE001 - ohne Landmaske wie bisher
        return None
    # Feinfeld-Wasser bleibt Wasser (23.11.2026): die OSM-Kuestenlinie schliesst Muendungen ab (Loire an der Bruecke
    # Saint-Nazaire, Saint-Laurent ab Ile d'Orleans ...), dahinter waere alles "Land" -> Loire-3D-Feld bei Paimboeuf weg
    if fein_wasser is not None and fein_wasser.shape == land.shape:
        land = land & ~fein_wasser
    gueltig = np.isfinite(u)
    if not gueltig.any():
        return None
    dist, (ji, ii) = ndimage.distance_transform_edt(~gueltig, return_indices=True)
    km_je = dx * 111.2 * max(0.2, math.cos(math.radians(la1 - dx * ny / 2)))
    fuell = ~gueltig & ~land & (dist * km_je <= FUELL_KM)
    u = np.where(fuell, u[ji, ii], u)
    v = np.where(fuell, v[ji, ii], v)
    u[land] = np.nan
    v[land] = np.nan
    return u, v, fuell & ~land, dx


if __name__ == '__main__':
    la_s, la_n, lo_w, lo_e = (float(x) for x in sys.argv[1:5])
    t = dt.datetime.fromisoformat(sys.argv[5]).replace(tzinfo=dt.timezone.utc) if len(sys.argv) > 5 else dt.datetime.now(dt.timezone.utc)
    import time
    a = time.time()
    r = feld(la_s, la_n, lo_w, lo_e, t)
    h = r[0]['header']
    sp = [math.hypot(x, y) for x, y in zip(r[0]['data'], r[1]['data']) if x is not None]
    print('%dx%d dx %.4f  Wasser %d  max %.2f m/s  %.2f s' % (h['nx'], h['ny'], h['dx'], len(sp), max(sp), time.time() - a))
