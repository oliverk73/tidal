#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hochaufgeloeste Gezeitenstromfelder fuer die Kartenebene (Oliver 19.11.2026: Schwachstromzonen in Starkstrom-
revieren sind fuer die Wegwahl wichtig -> Feld der feinen Modelle statt TPXO, wo vorhanden).

Quellen (Konstanten je Modellpunkt, tiefengemittelt):
  - SSW-RS (FVCOM NW-Schelf, Zellen an Kuesten ~0,7 km): Jahresfit 2018, quellen/tidal_streams/UK_SSWRS/fit_*.npz (kn)
  - AUSTEn (CSIRO COMPAS Australien): Ellipsen CSIRO_tidal_const_v12.nc (m/s)
`bauen` schreibt quellen/tidal_streams/feinfeld.npz: lat, lon, abstand_km (Nachbarpunkt), U_k/V_k komplex m/s
(c = a*e^{-ig}, Greenwich, wie TPXO in tpxo_strom_karte).

In tpxo_strom_karte.feld: Liegt eine Ausgabezelle im Gebiet eines feinen Modells (naechster Punkt < DECKT x
Punktabstand), bestimmt das feine Modell Wert (inverse Distanz der 3 naechsten Punkte) oder Land; sonst TPXO.

Usage: venv/bin/python py/strom_feinfeld.py bauen
"""
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'quellen/tidal_streams/feinfeld.npz')
KS = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4')
DECKT = 3.0
_S = {}


def _xy(la, lo):
    """Kugel-Einheitsvektoren (fuer KD-Baum ueber Laengengrade hinweg)."""
    a, b = np.radians(la), np.radians(lo)
    return np.c_[np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)]


def bauen():
    from scipy.spatial import cKDTree
    teile = []
    # SSW-RS
    D = os.path.join(ROOT, 'quellen/tidal_streams/UK_SSWRS')
    F = np.load(os.path.join(D, 'fit_20180101_20181231.npz'))
    g = np.load(os.path.join(D, 'gitter.npz'))
    la, lo = g['latc'].astype(float), ((g['lonc'].astype(float) + 180) % 360) - 180
    uv = {k: (F['U_' + k].astype(np.complex64) * np.float32(0.514444), F['V_' + k].astype(np.complex64) * np.float32(0.514444))
          for k in KS if 'U_' + k in F.files}
    teile.append(('SSW-RS', la, lo, uv))
    # AUSTEn
    import netCDF4
    A = netCDF4.Dataset(os.path.join(ROOT, 'quellen/tidal_streams/Australia_AusTEn/CSIRO_tidal_const_v12.nc'))
    ks = [''.join(c.decode() if isinstance(c, bytes) else str(c) for c in x).strip() for x in A['constituent_name'][:]]
    mj, mn, inc, ph = [A[v][:].filled(np.nan).astype(float) for v in ('u_maj', 'u_min', 'u_inc', 'u_pha')]
    la2, lo2 = A['Mesh2_face_y'][:].astype(float), A['Mesh2_face_x'][:].astype(float)
    ok = np.isfinite(mj[:, ks.index('M2')])
    uv2 = {}
    for k in KS:
        if k not in ks:
            continue
        j = ks.index(k)
        e = np.exp(-1j * np.radians(ph[:, j]))
        p = np.radians(inc[:, j])
        U = e * (mj[:, j] * np.cos(p) - 1j * mn[:, j] * np.sin(p))
        V = e * (mj[:, j] * np.sin(p) + 1j * mn[:, j] * np.cos(p))
        uv2[k] = (np.nan_to_num(U[ok]).astype(np.complex64), np.nan_to_num(V[ok]).astype(np.complex64))
    teile.append(('AUSTEn', la2[ok], lo2[ok], uv2))
    out = dict(lat=[], lon=[], quelle=[])
    for k in KS:
        out['U_' + k], out['V_' + k] = [], []
    for q, (name, a, b, uv) in enumerate(teile):
        out['lat'].append(a.astype(np.float32))
        out['lon'].append(b.astype(np.float32))
        out['quelle'].append(np.full(len(a), q, np.int8))
        for k in KS:
            z = np.zeros(len(a), np.complex64)
            out['U_' + k].append(uv[k][0] if k in uv else z)
            out['V_' + k].append(uv[k][1] if k in uv else z)
        print('%-7s %7d Punkte, Tiden %s' % (name, len(a), ','.join(k for k in KS if k in uv)))
    out = {k: np.concatenate(v) for k, v in out.items()}
    d, _ = cKDTree(_xy(out['lat'], out['lon'])).query(_xy(out['lat'], out['lon']), k=2)
    out['abstand_km'] = (d[:, 1] * 6371).astype(np.float32)
    out['quellen'] = np.array([t[0] for t in teile])
    np.savez(AUS, **out)
    print('->', AUS, '%.0f MB' % (os.path.getsize(AUS) / 1e6), ' Abstand Median %.2f km' % np.median(out['abstand_km']))


def _laden():
    if not _S and os.path.exists(AUS):
        from scipy.spatial import cKDTree
        F = np.load(AUS)
        _S.update({k: F[k] for k in F.files})
        _S['baum'] = cKDTree(_xy(_S['lat'].astype(float), _S['lon'].astype(float)))
    return _S


def einsetzen(lat, lon, u, v, t_rel_h, kopf, jahr):
    """lat (ny), lon (nx) der Ausgabezellen, u/v (ny, nx) m/s aus TPXO -> u/v mit feinem Feld, wo es deckt.
    t_rel_h: Stunden seit Jahresbeginn (UTC)."""
    S = _laden()
    if not S:
        return u, v, 0
    LA, LO = np.meshgrid(lat, lon, indexing='ij')
    d, i = S['baum'].query(_xy(LA.ravel(), LO.ravel()), k=3, distance_upper_bound=0.02)   # ~127 km
    d = d * 6371
    gut = np.isfinite(d[:, 0])
    if not gut.any():
        return u, v, 0
    i0 = np.where(gut, i[:, 0], 0)
    deckt = gut & (d[:, 0] < DECKT * np.maximum(S['abstand_km'][i0], 0.3))
    if not deckt.any():
        return u, v, 0
    # Zellweite der Ausgabe: Wasser, wenn ein Punkt naeher als halbe Zelldiagonale oder 1,5 x Punktabstand liegt
    zelle = abs(lat[1] - lat[0]) * 111 if len(lat) > 1 else 1.0
    wasser = deckt & (d[:, 0] < np.maximum(1.5 * S['abstand_km'][i0], 0.75 * zelle))
    idx = np.where(wasser)[0]
    ii = i[idx]
    dd = d[idx]
    w = np.where(np.isfinite(dd), 1.0 / np.maximum(dd, 0.05) ** 2, 0.0)
    w /= w.sum(1, keepdims=True)
    ii = np.where(np.isfinite(dd), ii, ii[:, :1])
    uu = np.zeros(len(idx))
    vv = np.zeros(len(idx))
    for k in KS:
        E = math.radians(kopf['arg'][jahr][k] + kopf['speeds'][k] * t_rel_h)
        f = kopf['fak'][jahr][k]
        rot = f * complex(math.cos(E), math.sin(E))
        uu += ((S['U_' + k][ii] * rot).real * w).sum(1)
        vv += ((S['V_' + k][ii] * rot).real * w).sum(1)
    uf, vf = u.ravel().copy(), v.ravel().copy()
    uf[deckt], vf[deckt] = np.nan, np.nan
    uf[idx], vf[idx] = uu, vv
    return uf.reshape(u.shape), vf.reshape(v.shape), int(deckt.sum())


if __name__ == '__main__':
    if sys.argv[1:2] == ['bauen']:
        bauen()
    else:
        print(__doc__)
