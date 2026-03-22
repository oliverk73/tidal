#!/usr/bin/env python3
"""
Download GFS-Wave forecasts (significant wave height + primary wave direction)
from NOAA NOMADS and convert to compact binary grid files for client-side
Canvas rendering with particle animation.

Source: NOAA GFS-Wave, 0.25° global resolution
URL: https://nomads.ncep.noaa.gov/cgi-bin/filter_gfswave.pl

Output per frame:
  wave_f{NNN}.bin  — uint16 LE, wave height in cm       (~130 KB @ 1°)
  wdir_f{NNN}.bin  — uint16 LE, wave direction in 0.1°  (~130 KB @ 1°)

Usage:
    python3 download_wave_forecast.py [--hours 72] [--cycle 00] [--res 1.0]
"""

import os
import json
import argparse
import requests
import numpy as np
import xarray as xr
from datetime import datetime, timezone

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "waves")
NOMADS_BASE = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfswave.pl"


def get_forecast_hours(max_hours):
    """Forecast hours: 0-120 every 3h, then 126-384 every 6h."""
    hours = list(range(0, min(max_hours + 1, 121), 3))
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
    """Download a single GRIB2 file from NOMADS (HTSGW + DIRPW at surface)."""
    fname = f"gfswave.t{cycle}z.global.0p25.f{fhour:03d}.grib2"
    url = (
        f"{NOMADS_BASE}"
        f"?dir=%2Fgfs.{date_str}%2F{cycle}%2Fwave%2Fgridded"
        f"&file={fname}"
        f"&var_HTSGW=on"
        f"&var_DIRPW=on"
        f"&lev_surface=on"
    )

    local_path = os.path.join(OUTPUT_DIR, fname)
    print(f"  Downloading f{fhour:03d}... ", end="", flush=True)
    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code != 200 or len(resp.content) < 1000:
            print(f"SKIP (HTTP {resp.status_code}, {len(resp.content)} bytes)")
            return None
        with open(local_path, "wb") as f:
            f.write(resp.content)
        print(f"OK ({len(resp.content) // 1024} KB)")
        return local_path
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def find_var(ds, candidates):
    """Find a variable by checking multiple possible names."""
    ds_vars_lower = {v.lower(): v for v in ds.data_vars}
    for c in candidates:
        if c.lower() in ds_vars_lower:
            return ds_vars_lower[c.lower()]
    # Fallback: partial match
    for c in candidates:
        for v in ds.data_vars:
            if c.lower() in v.lower():
                return v
    return None


def grib_to_bin(grib_path, fhour, target_res):
    """Convert GRIB2 to binary grids for height and direction."""
    try:
        # cfgrib may split variables into separate datasets
        datasets = xr.open_datasets(grib_path, engine="cfgrib")
    except Exception:
        try:
            datasets = [xr.open_dataset(grib_path, engine="cfgrib")]
        except Exception as e:
            print(f"    Error reading GRIB: {e}")
            return None, None, None

    # Merge all datasets to find both variables
    height_data = None
    dir_data = None
    lats = None
    lons = None

    for ds in datasets:
        if lats is None and 'latitude' in ds.coords:
            lats = ds.latitude.values
            lons = ds.longitude.values

        hvar = find_var(ds, ['htsgw', 'swh', 'hs'])
        if hvar and height_data is None:
            height_data = ds[hvar].values

        dvar = find_var(ds, ['dirpw', 'mwd', 'dp'])
        if dvar and dir_data is None:
            dir_data = ds[dvar].values

    for ds in datasets:
        ds.close()

    if height_data is None or lats is None:
        print(f"    No wave height variable found!")
        os.remove(grib_path)
        return None, None, None

    # Ensure latitude goes from 90 to -90
    if lats[0] < lats[-1]:
        height_data = np.flipud(height_data)
        if dir_data is not None:
            dir_data = np.flipud(dir_data)
        lats = lats[::-1]

    # Resample to target resolution
    src_res = abs(lats[1] - lats[0])
    if target_res > src_res * 1.5:
        step = int(round(target_res / src_res))
        height_data = height_data[::step, ::step]
        if dir_data is not None:
            dir_data = dir_data[::step, ::step]
        lats = lats[::step]
        lons = lons[::step]

    ny, nx = height_data.shape

    # Wave height: NaN → 0, convert to uint16 centimeters
    height_data = np.nan_to_num(height_data, nan=0.0)
    height_u16 = np.clip(height_data * 100, 0, 65535).astype(np.uint16)

    h_name = f"wave_f{fhour:03d}.bin"
    height_u16.tofile(os.path.join(OUTPUT_DIR, h_name))

    # Wave direction: NaN → 0, convert to uint16 in 0.1° units (0-3600)
    d_name = None
    if dir_data is not None:
        dir_data = np.nan_to_num(dir_data, nan=0.0)
        dir_u16 = np.clip(dir_data * 10, 0, 3600).astype(np.uint16)
        d_name = f"wdir_f{fhour:03d}.bin"
        dir_u16.tofile(os.path.join(OUTPUT_DIR, d_name))

    os.remove(grib_path)

    grid_info = {
        "nx": nx, "ny": ny,
        "la1": round(float(lats[0]), 4),
        "la2": round(float(lats[-1]), 4),
        "lo1": round(float(lons[0]), 4),
        "lo2": round(float(lons[-1]), 4),
        "dx": round(abs(float(lons[1] - lons[0])), 4),
        "dy": round(abs(float(lats[1] - lats[0])), 4)
    }

    h_size = os.path.getsize(os.path.join(OUTPUT_DIR, h_name))
    print(f"    -> {h_name} + {d_name or 'NO DIR'} ({nx}x{ny}, {h_size // 1024} KB each)")
    return h_name, d_name, grid_info


def main():
    parser = argparse.ArgumentParser(description="Download GFS-Wave forecasts as binary grids")
    parser.add_argument("--hours", type=int, default=72,
                        help="Max forecast hours (default: 72)")
    parser.add_argument("--cycle", type=str, default=None,
                        help="Cycle hour (00/06/12/18). Auto-detect if omitted.")
    parser.add_argument("--date", type=str, default=None,
                        help="Date YYYYMMDD. Auto-detect if omitted.")
    parser.add_argument("--res", type=float, default=1.0,
                        help="Target resolution in degrees (default: 1.0)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Clean old files
    for f in os.listdir(OUTPUT_DIR):
        if (f.startswith("wave_") or f.startswith("wdir_")) and f.endswith(".bin"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    if args.date and args.cycle:
        date_str, cycle = args.date, args.cycle
    else:
        date_str, cycle = get_latest_cycle()

    print(f"GFS-Wave Download: {date_str} {cycle}Z, max {args.hours}h, {args.res}° resolution")
    print(f"Output: {OUTPUT_DIR}\n")

    forecast_hours = get_forecast_hours(args.hours)
    frames = []
    grid_info = None
    has_direction = False

    for fh in forecast_hours:
        grib_path = download_grib(date_str, cycle, fh)
        if grib_path is None:
            continue

        h_name, d_name, gi = grib_to_bin(grib_path, fh, args.res)
        if h_name:
            if grid_info is None:
                grid_info = gi
            frame = {
                "height": h_name,
                "hour": fh,
                "label": f"+{fh}h"
            }
            if d_name:
                frame["direction"] = d_name
                has_direction = True
            frames.append(frame)

    if not frames:
        print("Keine Frames heruntergeladen!")
        return

    meta = {
        "date": date_str,
        "cycle": cycle,
        "generated": datetime.now(timezone.utc).isoformat(),
        "grid": grid_info,
        "hasDirection": has_direction,
        "frames": frames
    }
    meta_path = os.path.join(OUTPUT_DIR, "wave_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nFertig! {len(frames)} Frames generiert (Richtung: {'ja' if has_direction else 'nein'}).")
    print(f"Metadaten: {meta_path}")


if __name__ == "__main__":
    main()
