#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Leser fuer TPXO-Atlas im OTIS-Binaerformat (tide_models/TPXO9_atlas_v3, TPXO10_atlas_v2), ohne pyTMD.

h-Datei: Fortran-Records big-endian. Kopf (nx, ny, nc, lat_lim[2], lon_lim[2]), Name, dann (ny, nx) komplexe float32
(re, im). Gitter 1/30 Grad: Breite -90..90, Laenge 1/30..360. Einheit mm? -> per Probe (Tema M2 0.47 m) festgestellt.
Phase nach OTIS-Konvention: g = atan2(-im, re) (Greenwich-Phasennacheilung).
Land: h = 0. naechste_wasserzelle sucht die naechste Zelle mit h != 0 bis RAD Zellen.
Usage: venv/bin/python py/tpxo.py <lat> <lon> [modell]   (modell = 9 | 10, Standard beide)
"""
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELLE = {
    '9': (os.path.join(ROOT, 'tide_models/TPXO9_atlas_v3'), 'h_%s_tpxo9_atlas_30_v3'),
    '10': (os.path.join(ROOT, 'tide_models/TPXO10_atlas_v2'), 'h_%s_tpxo10_atlas_30_v2'),
}
NX, NY = 10800, 5401
KOPF = 4 + 32 + 4 + 4                                         # Record 1 (nx, ny, nc, Grenzen, Name) mit Markern + Marker Datenrecord
SKALA = 1.0
_cache = {}


def feld(modell, k):
    """memmap (ny, nx, 2) des Konstituenten k (klein geschrieben), oder None."""
    key = (modell, k)
    if key not in _cache:
        d, muster = MODELLE[modell]
        p = os.path.join(d, muster % k.lower())
        _cache[key] = np.memmap(p, dtype='>f4', mode='r', offset=KOPF, shape=(NY, NX, 2)) if os.path.exists(p) else None
    return _cache[key]


def konstituenten(modell):
    d, muster = MODELLE[modell]
    vor, nach = muster.split('%s')
    return [f[len(vor):-len(nach)].upper() for f in sorted(os.listdir(d)) if f.startswith(vor) and f.endswith(nach)]


def zelle(lat, lon):
    return int(round((lat + 90.0) * 30)), int(round((lon % 360.0) * 30 - 1)) % NX


def naechste_wasserzelle(modell, lat, lon, rad=30):
    """(i, j, km) der naechsten Zelle mit M2 != 0."""
    m = feld(modell, 'm2')
    i0, j0 = zelle(lat, lon)
    for r in range(rad + 1):
        ii = np.arange(max(0, i0 - r), min(NY, i0 + r + 1))
        jj = np.arange(j0 - r, j0 + r + 1) % NX
        blk = np.asarray(m[ii[0]:ii[-1] + 1][:, jj, 0]) != 0
        if blk.any():
            best = None
            for a, b in zip(*np.nonzero(blk)):
                la, lo = -90 + ii[a] / 30.0, (jj[b] + 1) / 30.0
                dk = 6371 * math.hypot(math.radians(la - lat), math.radians(((lo - lon + 180) % 360) - 180) * math.cos(math.radians(lat)))
                if best is None or dk < best[2]:
                    best = (int(ii[a]), int(jj[b]), dk)
            return best
    return None


def konstanten(modell, lat, lon, rad=30):
    """{K: (amp_m, phase_grad)} an der naechsten Wasserzelle, plus Abstand km."""
    z = naechste_wasserzelle(modell, lat, lon, rad)
    if z is None:
        return {}, None
    i, j, dk = z
    out = {}
    for k in konstituenten(modell):
        re, im = (float(x) for x in feld(modell, k)[i, j])
        out[k] = (SKALA * math.hypot(re, im), math.degrees(math.atan2(-im, re)) % 360)
    return out, dk


if __name__ == '__main__':
    la, lo = float(sys.argv[1]), float(sys.argv[2])
    for m in (sys.argv[3:] or ['9', '10']):
        w, dk = konstanten(m, la, lo)
        print('TPXO%s  Zelle %.1f km  ' % (m, dk) + '  '.join('%s %.4f@%.1f' % (k, *w[k]) for k in ('M2', 'S2', 'K1', 'O1', 'N2') if k in w))
