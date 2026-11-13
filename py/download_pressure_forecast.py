#!/usr/bin/env python3
"""
Luftdruck auf Meereshoehe (GFS PRMSL) mit Isobaren fuer die Kartenebene "Pressure" (Oliver 13.11.2026,
Vorbild windy.app type=prmsl&iso=1).

Quelle: NOAA GFS 0,25 Grad ueber NOMADS (wie py/download_wind_forecast.py), Variable PRMSL, mean sea level.

Ausgabe je Zeitschritt in static/pressure/:
  pressure_f{NNN}.bin   uint16 LE, Druck in 0,1 hPa, Zeile 0 = 90 N, Spalte 0 = 0 E (Gitter wie Wind, 0,5 Grad)
  pressure_f{NNN}.json  {"isobaren": [{"hpa": 1012, "linien": [[[lon, lat], ...], ...]}],
                         "labels": [[lon, lat, hpa], ...], "zentren": [[lon, lat, "H"|"L", hpa], ...]}
                        Isobaren alle ISO_HPA hPa aus dem leicht geglaetteten Feld (contourpy), Laenge -180..180;
                        Zentren = lokale Extrema in einem Fenster von ZENTRUM_GRAD (H >= 1015, L <= 1005 hPa).
                        "fronten": [{"typ": "kalt"|"warm"|"stationaer", "linie": [[lon, lat]...], "warm": [Grad]}]
                        objektive Frontenanalyse aus 850 hPa (py/fronten.py, Thermal Front Parameter)
  pressure_meta.json    Gitter + Zeitschritte (Format wie wind_meta.json)

Usage: venv/bin/python py/download_pressure_forecast.py [--hours 72] [--res 0.5]
"""
import argparse
import json
import os
from datetime import datetime, timezone

import numpy as np
import requests
import xarray as xr
from scipy import ndimage

import download_wind_forecast as W

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "pressure")
ISO_HPA, ZENTRUM_GRAD = 4, 12.0


def grib_url(date_str, cycle, fhour):
    fname = f"gfs.t{cycle}z.pgrb2.0p25.f{fhour:03d}"
    return (f"{W.NOMADS_BASE}?dir=%2Fgfs.{date_str}%2F{cycle}%2Fatmos&file={fname}"
            f"&var_PRMSL=on&lev_mean_sea_level=on"), fname


def lade(date_str, cycle, fhour, felder850=False, gelaende=False):
    url, fname = grib_url(date_str, cycle, fhour)
    if gelaende:                                        # Oberflaechenhoehe fuer die Frontenmaske (einmal je Lauf)
        url = url.replace("&var_PRMSL=on&lev_mean_sea_level=on", "&var_HGT=on&lev_surface=on")
        fname += "_hgt"
    elif felder850:                                       # fuer die Fronten: T, RH, Wind in 850 hPa
        url = url.replace("&var_PRMSL=on&lev_mean_sea_level=on", "&var_TMP=on&var_RH=on&var_UGRD=on&var_VGRD=on&lev_850_mb=on")
        fname += "_850"
    pfad = os.path.join(OUTPUT_DIR, fname + ".grib2")
    for _ in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200 and len(r.content) > 500:
                open(pfad, "wb").write(r.content)
                return pfad
        except Exception:
            pass
    return None


def isobaren(p_hpa, lats, lons):
    """p_hpa (ny, nx) 90N..90S, 0..360 -> Isobaren, Labelpunkte, Zentren (Laenge -180..180)."""
    import contourpy
    nx = p_hpa.shape[1]
    k = int(np.argmin(np.abs(lons - 180.0)))
    pr = np.concatenate([p_hpa[:, k:], p_hpa[:, :k]], axis=1)          # Spalte 0 = -180
    lo = np.concatenate([lons[k:] - 360.0, lons[:k]])
    pr = np.concatenate([pr, pr[:, :1]], axis=1)                       # Naht +180 schliessen
    lo = np.concatenate([lo, [lo[0] + 360.0]])
    glatt = ndimage.gaussian_filter(pr, sigma=1.2, mode=("nearest", "wrap"))
    gen = contourpy.contour_generator(lo, lats, glatt, line_type="Separate")
    stufen = range(int(np.floor(np.nanmin(glatt) / ISO_HPA) * ISO_HPA), int(np.ceil(np.nanmax(glatt))) + 1, ISO_HPA)
    iso, labels = [], []
    for h in stufen:
        linien = []
        for seg in gen.lines(h):
            if len(seg) < 4:
                continue
            from shapely.geometry import LineString
            seg = np.asarray(LineString(seg).simplify(0.08).coords)   # Douglas-Peucker, optisch gleich
            seg = np.round(seg, 1)                      # 0,1 Grad (~10 km) reicht fuer Isobaren
            seg = seg[np.r_[True, np.any(np.diff(seg, axis=0) != 0, axis=1)]]
            if len(seg) < 3:
                continue
            linien.append(seg.tolist())
            if len(seg) >= 25:                          # ein Label je laengerer Linie, weitere alle ~150 Punkte
                for j in range(len(seg) // 2, len(seg), 150):
                    labels.append([float(seg[j][0]), float(seg[j][1]), int(h)])
        if linien:
            iso.append({"hpa": int(h), "linien": linien})
    # Zentren
    fen = int(round(ZENTRUM_GRAD / abs(lats[1] - lats[0])))
    mx = ndimage.maximum_filter(glatt, size=fen, mode=("nearest", "wrap"))
    mn = ndimage.minimum_filter(glatt, size=fen, mode=("nearest", "wrap"))
    zentren = []
    for art, maske in (("H", (glatt == mx) & (glatt >= 1015)), ("L", (glatt == mn) & (glatt <= 1005))):
        for i, j in zip(*np.nonzero(maske[:, :-1])):
            if abs(lats[i]) > 85:
                continue
            zentren.append([round(float(lo[j]), 2), round(float(lats[i]), 2), art, int(round(float(pr[i, j])))])
    return iso, labels, zentren


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=72)
    ap.add_argument("--res", type=float, default=0.5)
    a = ap.parse_args()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    W.grib_url_orig = W.grib_url
    W.grib_url = grib_url                               # Lauf-Suche von download_wind_forecast mit PRMSL-URL
    date_str, cycle = W.get_latest_cycle()
    print(f"GFS {date_str} {cycle}z")
    frames, grid = [], None
    oro = None
    ph = lade(date_str, cycle, 0, gelaende=True)
    if ph:
        try:
            dh = xr.open_dataset(ph, engine="cfgrib", backend_kwargs={"indexpath": ""})
            oro = dh[next(n for n in dh.data_vars)].values
            if dh.latitude.values[0] < dh.latitude.values[-1]:
                oro = np.flipud(oro)
            dh.close()
        finally:
            for x in (ph, ph + ".idx"):
                if os.path.exists(x):
                    os.remove(x)
    for fh in W.get_forecast_hours(a.hours):
        pfad = lade(date_str, cycle, fh)
        if not pfad:
            print(f"  f{fh:03d} fehlt")
            continue
        try:
            ds = xr.open_dataset(pfad, engine="cfgrib", backend_kwargs={"indexpath": ""})
            var = next(n for n in ds.data_vars)
            p = ds[var].values / 100.0                  # Pa -> hPa
            lats, lons = ds.latitude.values, ds.longitude.values
            ds.close()
        finally:
            for x in (pfad, pfad + ".idx"):
                if os.path.exists(x):
                    os.remove(x)
        if lats[0] < lats[-1]:
            p, lats = np.flipud(p), lats[::-1]
        step = max(1, int(round(a.res / abs(lats[1] - lats[0]))))
        p, lats, lons = p[::step, ::step], lats[::step], lons[::step]
        ny, nx = p.shape
        grid = {"nx": nx, "ny": ny, "la1": float(lats[0]), "la2": float(lats[-1]), "lo1": float(lons[0]),
                "lo2": float(lons[-1]), "dx": round(float(lons[1] - lons[0]), 4), "dy": round(abs(float(lats[1] - lats[0])), 4)}
        b = f"pressure_f{fh:03d}.bin"
        np.clip(np.round(p * 10), 0, 65535).astype("<u2").tofile(os.path.join(OUTPUT_DIR, b))
        iso, labels, zentren = isobaren(p, lats, lons)
        front = []
        p850 = lade(date_str, cycle, fh, felder850=True)
        if p850:
            try:
                import fronten
                d8 = xr.open_dataset(p850, engine="cfgrib", backend_kwargs={"indexpath": ""})
                la8 = d8.latitude.values
                f = (lambda a_: np.flipud(a_) if la8[0] < la8[-1] else a_)
                t8, r8, u8, v8 = (f(d8[k].values)[::step, ::step] for k in ("t", "r", "u", "v"))
                d8.close()
                front = fronten.analyse(t8, r8, u8, v8, lats, lons,
                                         None if oro is None else oro[::step, ::step])
            finally:
                for x in (p850, p850 + ".idx"):
                    if os.path.exists(x):
                        os.remove(x)
        j = f"pressure_f{fh:03d}.json"
        json.dump({"isobaren": iso, "labels": labels, "zentren": zentren, "fronten": front},
                  open(os.path.join(OUTPUT_DIR, j), "w"), separators=(",", ":"))
        frames.append({"file": b, "iso": j, "hour": fh, "label": f"+{fh}h"})
        print(f"  f{fh:03d}: {np.nanmin(p):.0f}-{np.nanmax(p):.0f} hPa, {sum(len(x['linien']) for x in iso)} Isobaren, "
              f"{len(zentren)} Zentren, {len(front)} Fronten, {os.path.getsize(os.path.join(OUTPUT_DIR, j)) // 1024} KB")
    meta = {"date": date_str, "cycle": cycle, "generated": datetime.now(timezone.utc).isoformat(), "grid": grid,
            "unit": "0.1 hPa", "layout": "uint16 LE", "isobar_step_hpa": ISO_HPA, "frames": frames}
    json.dump(meta, open(os.path.join(OUTPUT_DIR, "pressure_meta.json"), "w"), indent=1)
    print(f"{len(frames)} Zeitschritte -> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
