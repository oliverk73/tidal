#!/usr/bin/env python3
"""
Download GFS 10 m wind forecasts (u, v) from NOAA NOMADS and convert to
compact binary grid files for client-side Canvas rendering with animated
particles (static/js/wind_layer.js).

Source: NOAA GFS, 0.25° global resolution
URL: https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl
Variables: UGRD + VGRD at 10 m above ground (m/s)

Output per frame:
  wind_f{NNN}.bin — int16 LE, u block (nx*ny) followed by v block (nx*ny),
                    values in 0.01 m/s, row 0 = 90°N, column 0 = 0°E
                    (~1 MB per frame @ 0.5°, ~260 KB @ 1°)

Usage:
    python3 download_wind_forecast.py [--hours 72] [--cycle 06] [--res 0.5]
"""

import os
import json
import argparse
import requests
import numpy as np
import xarray as xr
from datetime import datetime, timezone, timedelta

# Project root is the parent of this script's py/ directory (matches download_wave_forecast.py)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "wind")
NOMADS_BASE = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"


def get_forecast_hours(max_hours):
    """Forecast hours: 0-120 every 3h, then 126-384 every 6h."""
    hours = list(range(0, min(max_hours + 1, 121), 3))
    if max_hours > 120:
        hours += list(range(126, min(max_hours + 1, 385), 6))
    return hours


def grib_url(date_str, cycle, fhour):
    fname = f"gfs.t{cycle}z.pgrb2.0p25.f{fhour:03d}"
    return (
        f"{NOMADS_BASE}"
        f"?dir=%2Fgfs.{date_str}%2F{cycle}%2Fatmos"
        f"&file={fname}"
        f"&var_UGRD=on"
        f"&var_VGRD=on"
        f"&lev_10_m_above_ground=on"
    ), fname


def get_latest_cycle():
    """Latest GFS cycle whose f000 is already on NOMADS (GFS lags ~4-5 h).
    Probes the four most recent cycles, newest first."""
    now = datetime.now(timezone.utc)
    t = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
    for _ in range(4):
        date_str, cycle = t.strftime("%Y%m%d"), f"{t.hour:02d}"
        url, _fname = grib_url(date_str, cycle, 0)
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 500:
                return date_str, cycle
        except Exception:
            pass
        t -= timedelta(hours=6)
    raise SystemExit("Kein GFS-Lauf auf NOMADS gefunden (letzte 24 h).")


def download_grib(date_str, cycle, fhour):
    """Download a single GFS GRIB2 file from NOMADS (only 10 m u/v)."""
    url, fname = grib_url(date_str, cycle, fhour)
    local_path = os.path.join(OUTPUT_DIR, fname + ".grib2")
    print(f"  Downloading f{fhour:03d}... ", end="", flush=True)
    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code != 200 or len(resp.content) < 500:
            print(f"SKIP (HTTP {resp.status_code}, {len(resp.content)} bytes)")
            return None
        with open(local_path, "wb") as f:
            f.write(resp.content)
        print(f"OK ({len(resp.content) // 1024} KB)")
        return local_path
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def remove_grib(grib_path):
    """Remove the GRIB file plus the .idx index cfgrib leaves next to it."""
    folder = os.path.dirname(grib_path)
    base = os.path.basename(grib_path)
    for f in os.listdir(folder):
        if f == base or (f.startswith(base) and f.endswith(".idx")):
            os.remove(os.path.join(folder, f))


def grib_to_bin(grib_path, fhour, target_res):
    """Convert GRIB2 to one binary file: int16 u block + int16 v block (0.01 m/s)."""
    try:
        ds = xr.open_dataset(grib_path, engine="cfgrib",
                             backend_kwargs={"filter_by_keys": {"typeOfLevel": "heightAboveGround"}})
    except Exception as e:
        print(f"    Error reading GRIB: {e}")
        remove_grib(grib_path)
        return None, None

    uvar = next((n for n in ds.data_vars if n.lower() in ("u10", "u")), None)
    vvar = next((n for n in ds.data_vars if n.lower() in ("v10", "v")), None)
    if uvar is None or vvar is None:
        print(f"    No u/v wind variables found: {list(ds.data_vars)}")
        ds.close()
        remove_grib(grib_path)
        return None, None

    u = ds[uvar].values
    v = ds[vvar].values
    lats = ds.latitude.values
    lons = ds.longitude.values
    ds.close()
    remove_grib(grib_path)

    # Ensure latitude goes from 90 to -90
    if lats[0] < lats[-1]:
        u = np.flipud(u)
        v = np.flipud(v)
        lats = lats[::-1]

    # Resample to target resolution
    src_res = abs(lats[1] - lats[0])
    if target_res > src_res * 1.5:
        step = int(round(target_res / src_res))
        u = u[::step, ::step]
        v = v[::step, ::step]
        lats = lats[::step]
        lons = lons[::step]

    # m/s → int16 in 0.01 m/s (±327 m/s, far beyond any real 10 m wind)
    def to_i16(a):
        return np.clip(np.round(np.nan_to_num(a, nan=0.0) * 100), -32767, 32767).astype("<i2")

    ny, nx = u.shape
    grid_info = {
        "nx": nx, "ny": ny,
        "la1": round(float(lats[0]), 4),
        "la2": round(float(lats[-1]), 4),
        "lo1": round(float(lons[0]), 4),
        "lo2": round(float(lons[-1]), 4),
        "dx": round(abs(float(lons[1] - lons[0])), 4),
        "dy": round(abs(float(lats[1] - lats[0])), 4)
    }

    bin_name = f"wind_f{fhour:03d}.bin"
    bin_path = os.path.join(OUTPUT_DIR, bin_name)
    with open(bin_path, "wb") as f:
        f.write(to_i16(u).tobytes())
        f.write(to_i16(v).tobytes())

    speed = np.hypot(u, v)
    print(f"    -> {bin_name} ({nx}x{ny}, {os.path.getsize(bin_path) // 1024} KB, "
          f"max {float(np.nanmax(speed)):.1f} m/s)")
    return bin_name, grid_info


def main():
    parser = argparse.ArgumentParser(description="Download GFS 10 m wind forecasts")
    parser.add_argument("--hours", type=int, default=72,
                        help="Max forecast hours (default: 72)")
    parser.add_argument("--cycle", type=str, default=None,
                        help="Cycle hour (00/06/12/18). Auto-detect if omitted.")
    parser.add_argument("--date", type=str, default=None,
                        help="Date YYYYMMDD. Auto-detect if omitted.")
    parser.add_argument("--res", type=float, default=0.5,
                        help="Target resolution in degrees (default: 0.5)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.date and args.cycle:
        date_str, cycle = args.date, args.cycle
    else:
        date_str, cycle = get_latest_cycle()

    print(f"GFS Wind Download: {date_str} {cycle}Z, max {args.hours}h, {args.res}° resolution")
    print(f"Output: {OUTPUT_DIR}\n")

    frames = []
    grid_info = None

    for fh in get_forecast_hours(args.hours):
        grib_path = download_grib(date_str, cycle, fh)
        if grib_path is None:
            continue

        bin_name, gi = grib_to_bin(grib_path, fh, args.res)
        if bin_name:
            if grid_info is None:
                grid_info = gi
            frames.append({
                "file": bin_name,
                "hour": fh,
                "label": f"+{fh}h"
            })

    if not frames:
        print("Keine Frames heruntergeladen!")
        return

    meta = {
        "date": date_str,
        "cycle": cycle,
        "generated": datetime.now(timezone.utc).isoformat(),
        "grid": grid_info,
        "unit": "0.01 m/s",
        "layout": "u block then v block, int16 LE",
        "frames": frames
    }
    meta_path = os.path.join(OUTPUT_DIR, "wind_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Old frames are removed only after the new meta is in place, so the map
    # never points at missing files while a download is running.
    keep = {fr["file"] for fr in frames}
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith("wind_f") and f.endswith(".bin") and f not in keep:
            os.remove(os.path.join(OUTPUT_DIR, f))

    print(f"\nFertig! {len(frames)} Frames generiert.")
    print(f"Metadaten: {meta_path}")


if __name__ == "__main__":
    main()
