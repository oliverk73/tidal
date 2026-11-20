#!/usr/bin/env python3
"""
Ozeanstrom (Copernicus GLO12, ohne Gezeiten) an beliebigen Punkten/Zeiten – fuer „Total current“ = Gezeitenstrom +
Ozeanstrom (20.11.2026). Daten: py/download_ocean_cmems.py -> quellen/ozeanstrom/cmems_uv.i16 + cmems_meta.json.

uv(lat, lon, t) -> (u, v) in m/s: bilinear im Raum, linear in der Zeit (6-h-Schritte). Wo das Modell Land hat
(Kuestenzellen, Fjorde unter 1/12°), Ergebnis 0 – dort traegt allein der Gezeitenstrom. Ausserhalb des
Zeitraums -> None.
"""
import json
import os

import numpy as np

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(BASIS, "quellen", "ozeanstrom")
_C = {}


def _laden():
    """Meta + memmap; neu laden, wenn der Download die Datei ersetzt hat."""
    pfad = os.path.join(ORDNER, "cmems_meta.json")
    try:
        st = os.stat(pfad).st_mtime
    except OSError:
        return None
    if _C.get("st") != st:
        with open(pfad) as f:
            m = json.load(f)
        mm = np.memmap(os.path.join(ORDNER, "cmems_uv.i16"), dtype="<i2", mode="r",
                       shape=(m["T"], 2, m["NY"], m["NX"]))
        _C.clear()
        _C.update(st=st, m=m, mm=mm, z=np.array(m["zeiten"], dtype="f8"))
    return _C


def info():
    C = _laden()
    if not C:
        return None
    m = C["m"]
    return {"quelle": m["quelle"], "abruf": m["abruf"], "von": m["zeiten"][0], "bis": m["zeiten"][-1]}


def _raum(mm_t, lat, lon, m):
    """bilinear an (lat, lon)-Gittern gleicher Form; Land = 0 (Gewichte nur ueber Wasserecken)."""
    y = (lat - m["lat0"]) / m["dlat"]
    x = ((lon - m["lon0"]) % 360.0) / m["dlon"]
    y = np.clip(y, 0, m["NY"] - 1.001)
    i0 = np.floor(y).astype(int)
    j0 = np.floor(x).astype(int) % m["NX"]
    j1 = (j0 + 1) % m["NX"]
    fy = y - i0
    fx = x - np.floor(x)
    u = np.zeros(lat.shape)
    v = np.zeros(lat.shape)
    w = np.zeros(lat.shape)
    for ii, jj, g in ((i0, j0, (1 - fy) * (1 - fx)), (i0, j1, (1 - fy) * fx),
                      (i0 + 1, j0, fy * (1 - fx)), (i0 + 1, j1, fy * fx)):
        a = mm_t[0][ii, jj]
        b = mm_t[1][ii, jj]
        ok = a != m["land"]
        u += np.where(ok, a * g, 0)
        v += np.where(ok, b * g, 0)
        w += np.where(ok, g, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        u = np.where(w > 0.05, u / w, 0) / 1000.0
        v = np.where(w > 0.05, v / w, 0) / 1000.0
    return u, v


def uv(lat, lon, t):
    """lat, lon: Arrays gleicher Form (Grad), t: Unix-Sekunden. -> (u, v) m/s oder None."""
    C = _laden()
    if not C:
        return None
    z = C["z"]
    if t < z[0] or t > z[-1]:
        return None
    m, mm = C["m"], C["mm"]
    lat = np.asarray(lat, dtype="f8")
    lon = np.asarray(lon, dtype="f8")
    k = int(min(len(z) - 2, np.searchsorted(z, t, side="right") - 1))
    f = (t - z[k]) / (z[k + 1] - z[k])
    u0, v0 = _raum(mm[k], lat, lon, m)
    if f <= 0:
        return u0, v0
    u1, v1 = _raum(mm[k + 1], lat, lon, m)
    return u0 + f * (u1 - u0), v0 + f * (v1 - v0)


if __name__ == "__main__":
    import sys
    import time
    la, lo = float(sys.argv[1]), float(sys.argv[2])
    r = uv(np.array([la]), np.array([lo]), time.time())
    print(info())
    print(r and "u=%.3f v=%.3f m/s" % (r[0][0], r[1][0]))
