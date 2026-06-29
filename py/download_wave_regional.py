#!/usr/bin/env python3
"""Download higher-resolution REGIONAL wave forecasts (Copernicus Marine) and
augment the global GFS-Wave layer with them for enclosed/marginal seas where
the 0.5° global model is too coarse.

Runs AFTER download_wave_forecast.py: it reads static/waves/wave_meta.json
(date, cycle, frame hours) and adds a "regions" array, sampling each regional
model at the SAME forecast valid times as the global frames.

Regions (variable VHM0 = sig. wave height, VMDR = mean wave direction FROM):
  - baltic        cmems_mod_bal_wav_anfc_PT1H-i        ~1 nm  (WAM 4.7)
  - mediterranean cmems_mod_med_wav_anfc_4.2km_PT1H-i  1/24°  (WAM 6)
  - redsea        cmems_mod_glo_wav_anfc_0.083deg_PT3H-i  1/12° (no regional model exists)
  - persiangulf   cmems_mod_glo_wav_anfc_0.083deg_PT3H-i  1/12°

Output (same binary format as the global layer, lon in -180..180):
  wave_{region}_f{NNN}.bin  — uint16 LE, wave height in cm
  wdir_{region}_f{NNN}.bin  — uint16 LE, wave direction in 0.1°

Requires: copernicusmarine (logged in), xarray, numpy.
"""
import os
import json
import tempfile
import datetime as dt

import numpy as np
import xarray as xr
import copernicusmarine as cm

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "waves")
META_PATH = os.path.join(OUTPUT_DIR, "wave_meta.json")

# bbox = (lon_min, lon_max, lat_min, lat_max); stride coarsens to ~0.05-0.08°
REGIONS = [
    {"name": "baltic",        "dataset": "cmems_mod_bal_wav_anfc_PT1H-i",
     "bbox": (9.0, 30.5, 53.0, 66.0),  "stride": 3},
    {"name": "mediterranean", "dataset": "cmems_mod_med_wav_anfc_4.2km_PT1H-i",
     "bbox": (-6.0, 37.0, 30.0, 46.5), "stride": 2},
    {"name": "redsea",        "dataset": "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
     "bbox": (32.0, 44.0, 12.0, 30.5), "stride": 1},
    {"name": "persiangulf",   "dataset": "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
     "bbox": (46.5, 57.5, 22.5, 30.7), "stride": 1},
]


def load_meta():
    with open(META_PATH) as f:
        return json.load(f)


def clean_old():
    for f in os.listdir(OUTPUT_DIR):
        if (f.startswith("wave_") or f.startswith("wdir_")) and "_f" in f and f.endswith(".bin"):
            # region files look like wave_baltic_f000.bin (3 underscores); leave global wave_f000.bin
            parts = f.split("_")
            if len(parts) >= 3:
                os.remove(os.path.join(OUTPUT_DIR, f))


def fetch_region(region, base_valid, frame_hours, tmpdir):
    lon0, lon1, lat0, lat1 = region["bbox"]
    last_h = max(frame_hours)
    t0 = base_valid - dt.timedelta(hours=2)
    t1 = base_valid + dt.timedelta(hours=last_h + 2)
    nc = os.path.join(tmpdir, f"{region['name']}.nc")
    cm.subset(
        dataset_id=region["dataset"],
        variables=["VHM0", "VMDR"],
        minimum_longitude=lon0, maximum_longitude=lon1,
        minimum_latitude=lat0, maximum_latitude=lat1,
        start_datetime=t0.strftime("%Y-%m-%dT%H:%M:%S"),
        end_datetime=t1.strftime("%Y-%m-%dT%H:%M:%S"),
        output_filename=os.path.basename(nc), output_directory=tmpdir,
        overwrite=True, disable_progress_bar=True,
    )
    return nc


def build_region(region, base_valid, frames, tmpdir):
    nc = fetch_region(region, base_valid, [f["hour"] for f in frames], tmpdir)
    ds = xr.open_dataset(nc)
    st = region["stride"]
    if st > 1:
        ds = ds.isel(latitude=slice(None, None, st), longitude=slice(None, None, st))
    # latitude descending so row 0 = north (matches global grid convention)
    if float(ds.latitude[0]) < float(ds.latitude[-1]):
        ds = ds.isel(latitude=slice(None, None, -1))

    lats = ds.latitude.values
    lons = ds.longitude.values
    ny, nx = len(lats), len(lons)
    grid = {
        "nx": nx, "ny": ny,
        "la1": round(float(lats[0]), 4), "la2": round(float(lats[-1]), 4),
        "lo1": round(float(lons[0]), 4), "lo2": round(float(lons[-1]), 4),
        "dx": round(abs(float(lons[1] - lons[0])), 4),
        "dy": round(abs(float(lats[1] - lats[0])), 4),
    }

    out_frames = []
    for fr in frames:
        valid = base_valid + dt.timedelta(hours=fr["hour"])
        sl = ds.sel(time=np.datetime64(valid.replace(tzinfo=None)), method="nearest")
        h = np.nan_to_num(sl.VHM0.values, nan=0.0)
        h_u16 = np.clip(h * 100, 0, 65535).astype("<u2")
        hname = f"wave_{region['name']}_f{fr['hour']:03d}.bin"
        h_u16.tofile(os.path.join(OUTPUT_DIR, hname))

        d = np.nan_to_num(sl.VMDR.values, nan=0.0)
        d_u16 = np.clip(d * 10, 0, 3600).astype("<u2")
        dname = f"wdir_{region['name']}_f{fr['hour']:03d}.bin"
        d_u16.tofile(os.path.join(OUTPUT_DIR, dname))

        out_frames.append({"height": hname, "direction": dname,
                           "hour": fr["hour"], "label": fr.get("label", f"+{fr['hour']}h")})

    ds.close()
    return {"name": region["name"], "grid": grid, "frames": out_frames}


def main():
    meta = load_meta()
    base_valid = dt.datetime.strptime(meta["date"] + meta["cycle"], "%Y%m%d%H").replace(
        tzinfo=dt.timezone.utc)
    frames = meta["frames"]
    print(f"Regional waves: base {base_valid.isoformat()}, {len(frames)} frames")

    clean_old()
    regions_out = []
    with tempfile.TemporaryDirectory() as tmp:
        for region in REGIONS:
            try:
                print(f"  {region['name']} ({region['dataset']}) ...", flush=True)
                r = build_region(region, base_valid, frames, tmp)
                g = r["grid"]
                print(f"    OK {g['nx']}x{g['ny']} dx={g['dx']} dy={g['dy']} "
                      f"({len(r['frames'])} frames)")
                regions_out.append(r)
            except Exception as e:
                print(f"    FEHLER {region['name']}: {str(e)[:200]}")

    if not regions_out:
        print("Keine Regionen erzeugt — wave_meta.json unverändert.")
        return

    meta["regions"] = regions_out
    with open(META_PATH, "w") as f:
        json.dump(meta, f)
    print(f"wave_meta.json aktualisiert: {len(regions_out)} Regionen.")


if __name__ == "__main__":
    main()
