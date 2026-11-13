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


def feld(la_s, la_n, lo_w, lo_e, t, max_zellen=MAX_ZELLEN):
    """-> leaflet-velocity-Liste [u, v] in m/s fuer den Ausschnitt zur Zeit t (datetime UTC)."""
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
    kopfz = dict(lo1=round(lo1, 5), lo2=round(lo1 + dx * (nj - 1), 5), la1=round(la1, 5), la2=round(la2, 5),
                 dx=round(dx, 6), dy=round(dx, 6), nx=int(nj), ny=int(len(ii)), refTime=t.strftime('%Y-%m-%dT%H:%M:%SZ'),
                 forecastTime=0, scanMode=0, parameterCategory=2, parameterUnit='m.s-1')

    def liste(a):
        return [None if not np.isfinite(x) else round(float(x), 3) for x in a.ravel()]
    return [dict(header=dict(kopfz, parameterNumber=2, parameterNumberName='eastward_tidal_current'), data=liste(u)),
            dict(header=dict(kopfz, parameterNumber=3, parameterNumberName='northward_tidal_current'), data=liste(v))]


if __name__ == '__main__':
    la_s, la_n, lo_w, lo_e = (float(x) for x in sys.argv[1:5])
    t = dt.datetime.fromisoformat(sys.argv[5]).replace(tzinfo=dt.timezone.utc) if len(sys.argv) > 5 else dt.datetime.now(dt.timezone.utc)
    import time
    a = time.time()
    r = feld(la_s, la_n, lo_w, lo_e, t)
    h = r[0]['header']
    sp = [math.hypot(x, y) for x, y in zip(r[0]['data'], r[1]['data']) if x is not None]
    print('%dx%d dx %.4f  Wasser %d  max %.2f m/s  %.2f s' % (h['nx'], h['ny'], h['dx'], len(sp), max(sp), time.time() - a))
