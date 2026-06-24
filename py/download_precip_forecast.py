#!/usr/bin/env python3
"""
Download GFS precipitation rate forecasts from NOAA NOMADS
and convert to compact binary grid files for client-side Canvas rendering.

Source: NOAA GFS, 0.25° global resolution
URL: https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl
Variable: PRATE (precipitation rate, kg/m²/s ≈ mm/s)

Output per frame: precip_f{NNN}.bin — uint16 LE, precip rate in 0.01 mm/h
                  ~130 KB per frame at 1° resolution

Usage:
    python3 download_precip_forecast.py [--hours 72] [--cycle 06] [--res 0.5]
"""

import os
import json
import argparse
import requests
import numpy as np
import xarray as xr
from datetime import datetime, timezone

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "precip")
NOMADS_BASE = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"


def get_forecast_hours(max_hours):
    """Forecast hours: 3-120 every 3h, then 126-384 every 6h."""
    hours = list(range(3, min(max_hours + 1, 121), 3))
    if max_hours > 120:
        hours += list(range(126, min(max_hours + 1, 385), 6))
    return hours


def get_latest_cycle():
    """Determine the latest available GFS cycle (lags ~4-5 hours)."""
    now = datetime.now(timezone.utc)
    cycle_hour = (now.hour // 6) * 6
    if now.hour - cycle_hour < 5:
        cycle_hour -= 6
        if cycle_hour < 0:
            cycle_hour = 18
            now = now.replace(day=now.day - 1)
    return now.strftime("%Y%m%d"), f"{cycle_hour:02d}"


def download_grib(date_str, cycle, fhour):
    """Download a single GFS GRIB2 file from NOMADS (only PRATE at surface)."""
    fname = f"gfs.t{cycle}z.pgrb2.0p25.f{fhour:03d}"
    url = (
        f"{NOMADS_BASE}"
        f"?dir=%2Fgfs.{date_str}%2F{cycle}%2Fatmos"
        f"&file={fname}"
        f"&var_PRATE=on"
        f"&lev_surface=on"
    )

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


def grib_to_bin(grib_path, fhour, target_res):
    """Convert GRIB2 to binary grid (uint16, precip rate in 0.01 mm/h)."""
    try:
        ds = xr.open_dataset(grib_path, engine="cfgrib",
                             backend_kwargs={"filter_by_keys": {"stepType": "instant"}})
    except Exception:
        try:
            ds = xr.open_dataset(grib_path, engine="cfgrib",
                                 backend_kwargs={"filter_by_keys": {"stepType": "avg"}})
        except Exception as e:
            print(f"    Error reading GRIB: {e}")
            os.remove(grib_path)
            return None, None

    # Find PRATE variable
    var_name = None
    for name in ds.data_vars:
        if "prate" in name.lower() or "precip" in name.lower():
            var_name = name
            break
    if var_name is None:
        var_name = list(ds.data_vars)[0]

    data = ds[var_name].values  # kg/m²/s
    lats = ds.latitude.values
    lons = ds.longitude.values

    # Ensure latitude goes from 90 to -90
    if lats[0] < lats[-1]:
        data = np.flipud(data)
        lats = lats[::-1]

    # Resample to target resolution
    src_res = abs(lats[1] - lats[0])
    if target_res > src_res * 1.5:
        step = int(round(target_res / src_res))
        data = data[::step, ::step]
        lats = lats[::step]
        lons = lons[::step]

    # Convert kg/m²/s → mm/h (* 3600), then store as 0.01 mm/h units
    # So 1 mm/h = 100 in the file, max ~655 mm/h (more than enough)
    data = np.nan_to_num(data, nan=0.0)
    data_mmh = data * 3600.0  # mm/h
    data_u16 = np.clip(data_mmh * 100, 0, 65535).astype(np.uint16)

    ny, nx = data_u16.shape
    grid_info = {
        "nx": nx, "ny": ny,
        "la1": round(float(lats[0]), 4),
        "la2": round(float(lats[-1]), 4),
        "lo1": round(float(lons[0]), 4),
        "lo2": round(float(lons[-1]), 4),
        "dx": round(abs(float(lons[1] - lons[0])), 4),
        "dy": round(abs(float(lats[1] - lats[0])), 4)
    }

    bin_name = f"precip_f{fhour:03d}.bin"
    bin_path = os.path.join(OUTPUT_DIR, bin_name)
    data_u16.tofile(bin_path)

    ds.close()
    os.remove(grib_path)

    file_size = os.path.getsize(bin_path)
    print(f"    -> {bin_name} ({nx}x{ny}, {file_size // 1024} KB)")
    return bin_name, grid_info


def main():
    parser = argparse.ArgumentParser(description="Download GFS precipitation forecasts")
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

    # Clean old files
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith("precip_") and f.endswith(".bin"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    if args.date and args.cycle:
        date_str, cycle = args.date, args.cycle
    else:
        date_str, cycle = get_latest_cycle()

    print(f"GFS Precip Download: {date_str} {cycle}Z, max {args.hours}h, {args.res}° resolution")
    print(f"Output: {OUTPUT_DIR}\n")

    forecast_hours = get_forecast_hours(args.hours)
    frames = []
    grid_info = None

    for fh in forecast_hours:
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
        "unit": "0.01 mm/h",
        "frames": frames
    }
    meta_path = os.path.join(OUTPUT_DIR, "precip_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nFertig! {len(frames)} Frames generiert.")
    print(f"Metadaten: {meta_path}")


if __name__ == "__main__":
    main()
