#!/usr/bin/env python3
"""
Download sea surface temperature data and convert to compact binary grid
for client-side Canvas rendering.

Two sources available (--source):
  oisst  — NOAA OISST v2.1, 0.25° native, daily analysis (default, ~500 KB)
  mur    — NASA MUR SST v4.1, 0.01° native, daily analysis (~12 MB at 0.1°)
           Much better coastal detail, recommended for quality display.

Output: sst.bin — uint16 LE, temperature as (T_celsius + 50) * 100
        sst_meta.json — grid metadata

Usage:
    python3 download_sst.py                        # OISST at 0.5°
    python3 download_sst.py --source mur           # MUR SST at 0.1°
    python3 download_sst.py --source mur --res 0.05  # MUR SST at 0.05°
"""

import os
import json
import argparse
import requests
import numpy as np
import xarray as xr
from datetime import datetime, timezone

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "sst")

ERDDAP_OISST = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg.nc"
ERDDAP_MUR = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.nc"


def download_oisst():
    """Download latest OISST from ERDDAP as NetCDF (0.25° native, 0-360° lon)."""
    url = (
        f"{ERDDAP_OISST}"
        f"?sst[(last)][(0.0)][(-89.875):(89.875)][(0.125):(359.875)]"
    )
    local_path = os.path.join(OUTPUT_DIR, "sst_latest.nc")
    print("Downloading NOAA OISST v2.1 from ERDDAP... ", end="", flush=True)
    return _download(url, local_path)


def download_mur(res):
    """Download latest MUR SST from ERDDAP as NetCDF.

    MUR is 0.01° native (-180..180° lon). We request with stride to get
    the desired resolution directly from the server, avoiding huge downloads.
    """
    # ERDDAP stride syntax: [(start):(stride):(stop)]
    # MUR lat: -89.99..89.99, lon: -179.99..180.0
    stride = max(1, round(res / 0.01))
    actual_res = stride * 0.01
    print(f"  Angeforderte Auflösung: {res}° → Stride {stride} → effektiv {actual_res}°")

    url = (
        f"{ERDDAP_MUR}"
        f"?analysed_sst[(last)]"
        f"[(-89.99):({stride}):(89.99)]"
        f"[(-179.99):({stride}):(179.99)]"
    )
    local_path = os.path.join(OUTPUT_DIR, "sst_latest.nc")
    print("Downloading NASA MUR SST v4.1 from ERDDAP... ", end="", flush=True)
    return _download(url, local_path)


def _download(url, local_path):
    """Generic ERDDAP download with progress."""
    try:
        resp = requests.get(url, timeout=600, stream=True)
        if resp.status_code != 200:
            print(f"FEHLER (HTTP {resp.status_code})")
            # Show error details (ERDDAP returns HTML error messages)
            text = resp.text[:500] if resp.text else ""
            if text:
                print(f"  {text}")
            return None
        # Stream to file with progress
        total = 0
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
                total += len(chunk)
                mb = total / (1024 * 1024)
                print(f"\rDownloading... {mb:.1f} MB", end="", flush=True)
        print(f"\rOK ({total // 1024} KB)                ")
        return local_path
    except Exception as e:
        print(f"FEHLER: {e}")
        return None


def nc_to_bin(nc_path, target_res, source):
    """Convert NetCDF to binary grid (uint16, temp as (°C+50)*100)."""
    ds = xr.open_dataset(nc_path)

    # Find SST variable (different name per source)
    if "sst" in ds.data_vars:
        sst = ds["sst"]
    elif "analysed_sst" in ds.data_vars:
        sst = ds["analysed_sst"]
    else:
        print(f"  Keine SST-Variable gefunden! Variablen: {list(ds.data_vars)}")
        ds.close()
        os.remove(nc_path)
        return None, None, None

    # Remove single-valued dimensions (time, depth)
    sst = sst.squeeze()
    data = sst.values  # 2D array, °C, NaN over land

    # Find lat/lon coordinates (different names per source)
    for lat_name in ["latitude", "lat"]:
        if lat_name in ds.coords:
            lats = ds[lat_name].values
            break
    for lon_name in ["longitude", "lon"]:
        if lon_name in ds.coords:
            lons = ds[lon_name].values
            break

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

    # MUR uses -180..180 longitude → convert to 0..360 for consistency with JS layer
    if float(lons[0]) < 0:
        print("  Konvertiere Längengrade: -180..180 → 0..360")
        # Find the split point (index where lon goes from negative to positive)
        split_idx = np.searchsorted(lons, 0)
        lons = np.concatenate([lons[split_idx:], lons[:split_idx] + 360])
        data = np.concatenate([data[:, split_idx:], data[:, :split_idx]], axis=1)

    # Resample to target resolution if needed (for OISST which is downloaded at native res)
    src_res = abs(float(lats[1] - lats[0]))
    if target_res > src_res * 1.5:
        step = int(round(target_res / src_res))
        data = data[::step, ::step]
        lats = lats[::step]
        lons = lons[::step]

    ny, nx = data.shape

    # Convert: NaN (land) → 0, SST → (T_celsius + 50) * 100 as uint16
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
    parser = argparse.ArgumentParser(description="Download sea surface temperature data")
    parser.add_argument("--source", choices=["oisst", "mur"], default="oisst",
                        help="Data source: oisst (0.25° NOAA) or mur (0.01° NASA, better coasts)")
    parser.add_argument("--res", type=float, default=None,
                        help="Target resolution in degrees (default: 0.5 for oisst, 0.1 for mur)")
    args = parser.parse_args()

    if args.res is None:
        args.res = 0.5 if args.source == "oisst" else 0.1

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Clean old files
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".bin"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    source_labels = {"oisst": "NOAA OISST v2.1", "mur": "NASA MUR SST v4.1"}
    print(f"{source_labels[args.source]} Download, {args.res}° Auflösung")
    print(f"Output: {OUTPUT_DIR}\n")

    if args.source == "mur":
        nc_path = download_mur(args.res)
    else:
        nc_path = download_oisst()

    if nc_path is None:
        print("Download fehlgeschlagen!")
        return

    bin_name, grid_info, data_date = nc_to_bin(nc_path, args.res, args.source)
    if bin_name is None:
        print("Konvertierung fehlgeschlagen!")
        return

    meta = {
        "source": args.source,
        "date": data_date,
        "generated": datetime.now(timezone.utc).isoformat(),
        "grid": grid_info,
        "unit": "(°C + 50) * 100",
        "file": bin_name
    }
    meta_path = os.path.join(OUTPUT_DIR, "sst_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nFertig! SST-Daten vom {data_date} ({source_labels[args.source]})")
    print(f"Metadaten: {meta_path}")


if __name__ == "__main__":
    main()
