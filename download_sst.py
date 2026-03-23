#!/usr/bin/env python3
"""
Download NOAA OISST v2.1 (Optimum Interpolation Sea Surface Temperature)
and convert to compact binary grid file for client-side Canvas rendering.

Source: NOAA OISST v2.1, 0.25° global resolution, daily analysis
URL: https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg
Variable: sst (sea surface temperature, °C, only over ocean — land is NaN)

Output: sst.bin — uint16 LE, temperature as (T_celsius + 50) * 100
        sst_meta.json — grid metadata

Usage:
    python3 download_sst.py [--res 0.5]
"""

import os
import json
import argparse
import requests
import numpy as np
import xarray as xr
from datetime import datetime, timezone

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "sst")
ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg.nc"


def download_oisst():
    """Download latest OISST from ERDDAP as NetCDF."""
    # Request latest SST at depth=0 (surface), full global grid
    url = (
        f"{ERDDAP_BASE}"
        f"?sst[(last)][(0.0)][(-89.875):(89.875)][(0.125):(359.875)]"
    )

    local_path = os.path.join(OUTPUT_DIR, "oisst_latest.nc")
    print("Downloading NOAA OISST from ERDDAP... ", end="", flush=True)
    try:
        resp = requests.get(url, timeout=300)
        if resp.status_code != 200:
            print(f"FEHLER (HTTP {resp.status_code})")
            print(f"  Response: {resp.text[:500]}")
            return None
        with open(local_path, "wb") as f:
            f.write(resp.content)
        print(f"OK ({len(resp.content) // 1024} KB)")
        return local_path
    except Exception as e:
        print(f"FEHLER: {e}")
        return None


def nc_to_bin(nc_path, target_res):
    """Convert NetCDF to binary grid (uint16, temp as (°C+50)*100)."""
    ds = xr.open_dataset(nc_path)

    # Get SST variable
    sst = ds["sst"]
    # Remove time/depth dimensions if present (squeeze single-valued dims)
    sst = sst.squeeze()

    data = sst.values  # 2D array, °C, NaN over land
    lats = ds.latitude.values if "latitude" in ds.coords else ds.lat.values
    lons = ds.longitude.values if "longitude" in ds.coords else ds.lon.values

    # Get the date of the data
    time_var = ds["time"] if "time" in ds.coords else None
    if time_var is not None:
        data_date = str(time_var.values.flatten()[0])[:10]
    else:
        data_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Ensure latitude goes from 90 to -90 (north first)
    if lats[0] < lats[-1]:
        data = np.flipud(data)
        lats = lats[::-1]

    # Resample to target resolution if needed
    src_res = abs(float(lats[1] - lats[0]))
    if target_res > src_res * 1.5:
        step = int(round(target_res / src_res))
        data = data[::step, ::step]
        lats = lats[::step]
        lons = lons[::step]

    ny, nx = data.shape

    # Convert: NaN (land) → 0, SST → (T_celsius + 50) * 100 as uint16
    # This maps -50°C..+605°C to 0..65535 (more than enough)
    # Special: value 0 means "no data / land"
    land_mask = np.isnan(data)
    data = np.nan_to_num(data, nan=-50.0)
    data_u16 = np.clip((data + 50.0) * 100.0, 0, 65535).astype(np.uint16)
    data_u16[land_mask] = 0  # land = 0 = transparent

    grid_info = {
        "nx": int(nx), "ny": int(ny),
        "la1": round(float(lats[0]), 4),
        "la2": round(float(lats[-1]), 4),
        "lo1": round(float(lons[0]), 4),
        "lo2": round(float(lons[-1]), 4),
        "dx": round(abs(float(lons[1] - lons[0])), 4),
        "dy": round(abs(float(lats[1] - lats[0])), 4)
    }

    bin_name = "sst.bin"
    bin_path = os.path.join(OUTPUT_DIR, bin_name)
    data_u16.tofile(bin_path)

    ds.close()
    os.remove(nc_path)

    file_size = os.path.getsize(bin_path)
    print(f"  -> {bin_name} ({nx}x{ny}, {file_size // 1024} KB)")
    return bin_name, grid_info, data_date


def main():
    parser = argparse.ArgumentParser(description="Download NOAA OISST sea surface temperature")
    parser.add_argument("--res", type=float, default=0.5,
                        help="Target resolution in degrees (default: 0.5)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Clean old files
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".bin"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    print(f"NOAA OISST Download, {args.res}° resolution")
    print(f"Output: {OUTPUT_DIR}\n")

    nc_path = download_oisst()
    if nc_path is None:
        print("Download fehlgeschlagen!")
        return

    bin_name, grid_info, data_date = nc_to_bin(nc_path, args.res)
    if bin_name is None:
        print("Konvertierung fehlgeschlagen!")
        return

    meta = {
        "date": data_date,
        "generated": datetime.now(timezone.utc).isoformat(),
        "grid": grid_info,
        "unit": "(°C + 50) * 100",
        "file": bin_name
    }
    meta_path = os.path.join(OUTPUT_DIR, "sst_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nFertig! SST-Daten vom {data_date}")
    print(f"Metadaten: {meta_path}")


if __name__ == "__main__":
    main()
