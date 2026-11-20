#!/usr/bin/env python3
"""
Wassertiefe fuer das Segel-Routing aus EMODnet Bathymetry (WCS, Europa, 1/16' ~115 m, Bezug LAT), 20.11.2026.

    hoehe = flachstes(sued, nord, west, ost, ny, nx)
        -> (ny, nx) float32: hoechster Grund je Rasterzelle in m ueber LAT (negativ = Tiefe, positiv = trockenfallend),
           NaN = keine Daten; None = Gebiet nicht abgedeckt / Dienst nicht erreichbar.
Je Zelle zaehlt der flachste EMODnet-Punkt (vorsichtig: eine schmale Untiefe faellt nicht durch das Raster).
Abrufe werden in quellen/routing/tiefe/ zwischengespeichert (Kachel = gerundetes Rechteck, hoechstens 300 MB).
"""
import hashlib
import io
import os

import numpy as np
import requests
from PIL import Image

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(BASIS, "quellen", "routing", "tiefe")
WCS = ("https://ows.emodnet-bathymetry.eu/wcs?service=WCS&version=2.0.1&request=GetCoverage&coverageId=emodnet__mean"
       "&subset=Lat({s},{n})&subset=Long({w},{e})&format=image/tiff{skala}")
AUFL = 1 / 960.0                                       # EMODnet-Rasterweite in Grad


def _abruf(s, n, w, e):
    os.makedirs(ORDNER, exist_ok=True)
    zellen = (n - s) / AUFL * (e - w) / AUFL
    skala = "" if zellen < 6e6 else "&scalefactor=%.3f" % (6e6 / zellen) ** 0.5
    url = WCS.format(s=s, n=n, w=w, e=e, skala=skala)
    pfad = os.path.join(ORDNER, hashlib.md5(url.encode()).hexdigest() + ".npy")
    if os.path.exists(pfad):
        return np.load(pfad)
    r = requests.get(url, timeout=120)
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/tiff"):
        return None
    a = np.array(Image.open(io.BytesIO(r.content)), dtype="f4")
    a[(a < -12000) | (a > 9000) | ~np.isfinite(a)] = np.nan
    np.save(pfad, a)
    _aufraeumen()
    return a


def _aufraeumen(grenze=300 * 2**20):
    """Zwischenspeicher hoechstens `grenze` Byte: die am laengsten nicht benutzten Kacheln fallen zuerst."""
    dateien = [os.path.join(ORDNER, f) for f in os.listdir(ORDNER) if f.endswith(".npy")]
    dateien.sort(key=lambda f: max(os.path.getatime(f), os.path.getmtime(f)), reverse=True)
    summe = 0
    for f in dateien:
        summe += os.path.getsize(f)
        if summe > grenze:
            os.remove(f)


def flachstes(s, n, w, e, ny, nx):
    # Rechteck auf 0,01° nach aussen runden (Zwischenspeicher trifft wiederholte Anfragen)
    S, N = np.floor(s * 100) / 100, np.ceil(n * 100) / 100
    W, E = np.floor(w * 100) / 100, np.ceil(e * 100) / 100
    try:
        a = _abruf(S, N, W, E)
    except Exception:                                  # noqa: BLE001 - ohne Tiefe weiterrechnen
        return None
    if a is None or not np.isfinite(a).any():
        return None
    hy, hx = a.shape
    la = N - (np.arange(hy) + 0.5) * (N - S) / hy      # Zeile 0 = Nord
    lo = W + (np.arange(hx) + 0.5) * (E - W) / hx
    ii = np.floor((n - la) / (n - s) * ny).astype(int)
    jj = np.floor((lo - w) / (e - w) * nx).astype(int)
    oki, okj = (ii >= 0) & (ii < ny), (jj >= 0) & (jj < nx)
    a = a[oki][:, okj]
    I, J = np.meshgrid(ii[oki], jj[okj], indexing="ij")
    aus = np.full(ny * nx, -np.inf, dtype="f4")
    v = a.ravel()
    m = np.isfinite(v)
    np.maximum.at(aus, (I.ravel() * nx + J.ravel())[m], v[m])
    aus[~np.isfinite(aus)] = np.nan
    aus = aus.reshape(ny, nx)
    # Zellen feiner als EMODnet ohne eigenen Punkt: vom naechsten Nachbarn
    if np.isnan(aus).any() and np.isfinite(aus).any():
        from scipy import ndimage
        idx = ndimage.distance_transform_edt(np.isnan(aus), return_distances=False, return_indices=True)
        aus = aus[tuple(idx)]
    return aus


if __name__ == "__main__":
    import sys
    import time
    s, n, w, e = (float(x) for x in sys.argv[1:5]) if len(sys.argv) > 4 else (53.67, 54.38, 7.55, 9.04)
    t = time.time()
    h = flachstes(s, n, w, e, 120, 240)
    print("%.1f s" % (time.time() - t), None if h is None else (np.nanmin(h), np.nanmax(h)))
    if h is not None:
        for r in h[::6]:
            print("".join("#" if v > 0 else ("w" if v > -2.3 else ("-" if v > -6 else ".")) for v in r[::3]))
