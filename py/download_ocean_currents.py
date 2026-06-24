#!/usr/bin/env python3
"""
Download HYCOM surface current forecasts (u, v) via OPeNDAP and export
as leaflet-velocity JSON for animated particle visualisation.

Source: HYCOM ESPC-D-V02 (FMRC best time series), 0.08° global
URL:    https://tds.hycom.org/thredds/dodsC/FMRC_ESPC-D-V02_uv3z/

Output:
  ocean_currents_meta.json       — metadata (times, source, grid)
  ocean_currents_f{NNN}.json     — leaflet-velocity JSON per frame

Usage:
    python3 download_ocean_currents.py [--hours 72] [--res 0.16] [--region europe]
"""

import os
import json
import argparse
import numpy as np
import xarray as xr
from datetime import datetime, timezone, timedelta

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "static", "ocean_currents")

HYCOM_URL = ("https://tds.hycom.org/thredds/dodsC/"
             "FMRC_ESPC-D-V02_uv3z/FMRC_ESPC-D-V02_uv3z_best.ncd")

# Predefined regions (lat_min, lat_max, lon_min, lon_max).
# Negative lon_min triggers wrap branch which produces correct -180..180 output.
REGIONS = {
    "europe":    (30, 72, 345, 375),    # 345==-15E, 375==15E (wraps around 360)
    "north_sea": (48, 62, 350, 370),
    "atlantic":  (20, 72, 280, 375),    # 280==-80W (inkl. US-Ostküste + Kanada)
    "global":    (-70, 80, -180, 180),  # full earth, output -180..180
}


def download_hycom_frame(ds, time_idx, depth_idx, region, target_res):
    """Extract one forecast frame from HYCOM OPeNDAP, regrid if needed."""

    lat_min, lat_max, lon_min, lon_max = region
    lats = ds["lat"].values
    lons = ds["lon"].values

    # Handle longitude wrapping (e.g. 345..375 for Europe)
    if lon_min >= 360:
        lon_min -= 360
        lon_max -= 360

    if lon_min < 0:
        # Need to wrap: select [lon_min+360 .. 360] + [0 .. lon_max]
        sel_lon1 = (lons >= (lon_min + 360))
        sel_lon2 = (lons <= lon_max)
        sel_lon = sel_lon1 | sel_lon2
        wrap = True
    elif lon_max > lons[-1]:
        sel_lon1 = (lons >= lon_min)
        sel_lon2 = (lons <= (lon_max - 360))
        sel_lon = sel_lon1 | sel_lon2
        wrap = True
    else:
        sel_lon = (lons >= lon_min) & (lons <= lon_max)
        wrap = False

    sel_lat = (lats >= lat_min) & (lats <= lat_max)

    u_raw = ds["water_u"].isel(time=time_idx, depth=depth_idx)
    v_raw = ds["water_v"].isel(time=time_idx, depth=depth_idx)

    if wrap:
        # Download both parts
        idx_lon1 = np.where(sel_lon1)[0]
        idx_lon2 = np.where(sel_lon2)[0]
        idx_lat = np.where(sel_lat)[0]

        u1 = u_raw.isel(lat=idx_lat, lon=idx_lon1).values
        u2 = u_raw.isel(lat=idx_lat, lon=idx_lon2).values
        v1 = v_raw.isel(lat=idx_lat, lon=idx_lon1).values
        v2 = v_raw.isel(lat=idx_lat, lon=idx_lon2).values

        u_data = np.concatenate([u1, u2], axis=1)
        v_data = np.concatenate([v1, v2], axis=1)
        out_lons = np.concatenate([lons[idx_lon1] - 360, lons[idx_lon2]])
        out_lats = lats[idx_lat]
    else:
        idx_lon = np.where(sel_lon)[0]
        idx_lat = np.where(sel_lat)[0]
        u_data = u_raw.isel(lat=idx_lat, lon=idx_lon).values
        v_data = v_raw.isel(lat=idx_lat, lon=idx_lon).values
        out_lons = lons[idx_lon]
        out_lats = lats[idx_lat]
        # Normalise longitudes to -180..180
        out_lons = np.where(out_lons > 180, out_lons - 360, out_lons)

    # Resample to target resolution if coarser than native
    native_res = abs(out_lats[1] - out_lats[0])
    if target_res > native_res * 1.5:
        step_lat = max(1, int(round(target_res / abs(out_lats[1] - out_lats[0]))))
        step_lon = max(1, int(round(target_res / abs(out_lons[1] - out_lons[0]))))
        u_data = u_data[::step_lat, ::step_lon]
        v_data = v_data[::step_lat, ::step_lon]
        out_lats = out_lats[::step_lat]
        out_lons = out_lons[::step_lon]

    return u_data, v_data, out_lats, out_lons


def to_velocity_json(u_data, v_data, lats, lons, ref_time_str, fhour):
    """Convert u/v grids to leaflet-velocity JSON format.

    leaflet-velocity expects:
      - la1 > la2  (North to South)
      - data array flattened row-major, North→South, West→East
      - NaN → null in JSON
    """
    # Ensure lat goes North→South
    if lats[0] < lats[-1]:
        lats = lats[::-1]
        u_data = np.flipud(u_data)
        v_data = np.flipud(v_data)

    ny, nx = u_data.shape
    dx = round(abs(float(lons[1] - lons[0])), 4)
    dy = round(abs(float(lats[0] - lats[1])), 4)

    header_base = {
        "lo1": round(float(lons[0]), 4),
        "lo2": round(float(lons[-1]), 4),
        "la1": round(float(lats[0]), 4),
        "la2": round(float(lats[-1]), 4),
        "dx": dx,
        "dy": dy,
        "nx": nx,
        "ny": ny,
        "refTime": ref_time_str,
        "forecastTime": fhour,
        "scanMode": 0,
    }

    def clean(arr):
        """Replace NaN with None for JSON."""
        flat = arr.flatten().tolist()
        return [None if (v is None or np.isnan(v)) else round(v, 4) for v in flat]

    data = [
        {
            "header": {**header_base,
                       "parameterCategory": 2,
                       "parameterNumber": 2,
                       "parameterNumberName": "eastward_sea_water_velocity",
                       "parameterUnit": "m.s-1"},
            "data": clean(u_data),
        },
        {
            "header": {**header_base,
                       "parameterCategory": 2,
                       "parameterNumber": 3,
                       "parameterNumberName": "northward_sea_water_velocity",
                       "parameterUnit": "m.s-1"},
            "data": clean(v_data),
        },
    ]
    return data


def main():
    parser = argparse.ArgumentParser(description="Download HYCOM ocean currents")
    parser.add_argument("--hours", type=int, default=72,
                        help="Forecast hours to download (default: 72)")
    parser.add_argument("--step", type=int, default=3,
                        help="Hour step between frames (default: 3)")
    parser.add_argument("--res", type=float, default=0.16,
                        help="Target resolution in degrees (default: 0.16)")
    parser.add_argument("--region", default="global",
                        choices=REGIONS.keys(),
                        help="Region to download (default: europe)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    region = REGIONS[args.region]
    fhours = list(range(0, args.hours + 1, args.step))

    print(f"Ocean Currents Download: HYCOM ESPC-D-V02")
    print(f"  Region:     {args.region} {region}")
    print(f"  Resolution: {args.res}°")
    print(f"  Frames:     {len(fhours)} ({args.hours}h, step {args.step}h)")
    print()

    # Open HYCOM OPeNDAP dataset
    print("Connecting to HYCOM OPeNDAP... ", end="", flush=True)
    try:
        ds = xr.open_dataset(HYCOM_URL, decode_times=True)
    except Exception:
        ds = xr.open_dataset(HYCOM_URL, decode_times=False)
    print("OK")

    times = ds["time"].values
    time_units = ds["time"].attrs.get("units", "")
    print(f"  Available times: {len(times)}")

    # Parse reference time from units attribute ("hours since YYYY-MM-DD HH:MM:SS...")
    time_units = ds["time"].attrs.get("units", "")
    try:
        base_str = time_units.split("since")[1].strip()
        base_str = base_str.replace(".000 UTC", "").replace(" UTC", "")
        base_dt = datetime.strptime(base_str, "%Y-%m-%d %H:%M:%S")
        ref_time = base_dt + timedelta(hours=float(times[0]))
    except Exception:
        ref_time = datetime.now(timezone.utc)

    ref_time_str = ref_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"  Reference time: {ref_time_str}")
    print()

    # Find the time index closest to "now" and download forward from there
    now = datetime.now(timezone.utc)
    hours_since_base = (now - base_dt.replace(tzinfo=timezone.utc)
                        ).total_seconds() / 3600.0
    start_idx = max(0, int(hours_since_base / 3))
    if start_idx >= len(times):
        start_idx = len(times) - 1
    actual_start = base_dt + timedelta(hours=float(times[start_idx]))
    print(f"  Nearest to now: index {start_idx} = {actual_start}")
    print()

    # Download frames
    frames = []
    grid_info = None

    for fi, fh in enumerate(fhours):
        target_idx = start_idx + fi
        if target_idx >= len(times):
            print(f"  f{fh:03d}: beyond available range, stopping")
            break

        print(f"  Downloading f{fh:03d}... ", end="", flush=True)
        try:
            u, v, lats, lons = download_hycom_frame(
                ds, target_idx, 0, region, args.res)

            data = to_velocity_json(u, v, lats, lons, ref_time_str, fh)

            fname = f"ocean_currents_f{fh:03d}.json"
            fpath = os.path.join(OUTPUT_DIR, fname)
            with open(fpath, "w") as fp:
                json.dump(data, fp, separators=(",", ":"))

            fsize = os.path.getsize(fpath)
            ny, nx = u.shape
            valid = (~np.isnan(u)).sum()
            total = u.size
            print(f"OK ({nx}x{ny}, {fsize // 1024} KB, "
                  f"{valid}/{total} ocean points)")

            if grid_info is None:
                grid_info = data[0]["header"].copy()
                del grid_info["parameterCategory"]
                del grid_info["parameterNumber"]
                del grid_info["parameterNumberName"]
                del grid_info["parameterUnit"]

            # Compute forecast time label
            try:
                ft = base_dt + timedelta(hours=float(times[target_idx]))
                label = ft.strftime("%d.%m. %H:%M UTC")
            except Exception:
                label = f"+{fh}h"

            frames.append({
                "file": fname,
                "hour": fh,
                "label": label,
            })
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

    ds.close()

    if not frames:
        print("\nNo frames downloaded!")
        return

    # Write metadata
    meta = {
        "source": "HYCOM ESPC-D-V02",
        "region": args.region,
        "resolution": args.res,
        "generated": datetime.now(timezone.utc).isoformat(),
        "refTime": ref_time_str,
        "grid": grid_info,
        "frames": frames,
    }

    meta_path = os.path.join(OUTPUT_DIR, "ocean_currents_meta.json")
    with open(meta_path, "w") as fp:
        json.dump(meta, fp, indent=2)

    print(f"\nDone! {len(frames)} frames saved to {OUTPUT_DIR}/")
    print(f"  Metadata: ocean_currents_meta.json")
    total_size = sum(
        os.path.getsize(os.path.join(OUTPUT_DIR, f["file"]))
        for f in frames
    )
    print(f"  Total size: {total_size // (1024 * 1024)} MB")


if __name__ == "__main__":
    main()
