#!/usr/bin/env python3
"""
Ozeanstrom ohne Gezeiten fuer die Ansicht „Total current“ (Gezeitenstrom + Ozeanstrom), 20.11.2026.

Quelle: Copernicus GLO12 (Mercator), cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i, uo/vo in 0,5 m Tiefe,
weltweit 1/12°, alle 6 h. Das Modell rechnet ohne Gezeiten – anders als HYCOM, dessen Ebene Gezeiten enthaelt
und deshalb nicht zum eigenen Gezeitenstrom addiert werden darf. Der stuendliche „merged“-Datensatz waere
~8 GB je Tag, deshalb der 6-stuendliche.

Ausgabe (quellen/ozeanstrom/):
  cmems_uv.i16   int16 mm/s, Form (T, 2, NY, NX), Zeile 0 = Sued (-80°), Spalte 0 = -180°; Land = -32768
  cmems_meta.json  Zeiten (Unix-s), Raster, Quelle, Abrufzeit

Aufruf:  venv/bin/python py/download_ocean_cmems.py [--tage 5]
Dauer ~5 min, voruebergehend ~1,5 GB in quellen/ozeanstrom/roh.
"""
import argparse
import json
import os
import shutil
from datetime import datetime, timedelta, timezone

import numpy as np
import xarray as xr

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(BASIS, "quellen", "ozeanstrom")
DATENSATZ = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"
LAND = -32768


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tage", type=float, default=5.0, help="Vorhersage ab heute 00 UTC (Tage)")
    a = ap.parse_args()
    import copernicusmarine as cm

    os.makedirs(AUS, exist_ok=True)
    roh = os.path.join(AUS, "roh")
    os.makedirs(roh, exist_ok=True)
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=6)
    ende = start + timedelta(hours=6) + timedelta(days=a.tage)
    print(f"Copernicus {DATENSATZ}: {start:%d.%m. %H} – {ende:%d.%m. %H} UTC ... ", flush=True)
    cm.subset(dataset_id=DATENSATZ, variables=["uo", "vo"], minimum_depth=0.4, maximum_depth=0.6,
              start_datetime=start.strftime("%Y-%m-%dT%H:%M:%S"), end_datetime=ende.strftime("%Y-%m-%dT%H:%M:%S"),
              output_directory=roh, output_filename="uv.nc", overwrite=True, disable_progress_bar=True)
    nc = os.path.join(roh, "uv.nc")
    with xr.open_dataset(nc) as ds:
        lat = ds.latitude.values.astype("f8")
        lon = ds.longitude.values.astype("f8")
        zeiten = [int(np.datetime64(t, "s").astype("int64")) for t in ds.time.values]
        T, NY, NX = len(zeiten), len(lat), len(lon)
        tmp = os.path.join(AUS, "cmems_uv.i16.neu")
        mm = np.memmap(tmp, dtype="<i2", mode="w+", shape=(T, 2, NY, NX))
        for i in range(T):
            for k, var in enumerate(("uo", "vo")):
                x = ds[var].isel(time=i, depth=0).values
                q = np.where(np.isfinite(x), np.clip(np.round(x * 1000), -32000, 32000), LAND)
                mm[i, k] = q.astype("<i2")
        mm.flush()
        del mm
    meta = {"quelle": "Copernicus GLO12 " + DATENSATZ + " (uo/vo 0,5 m, ohne Gezeiten)",
            "abruf": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "zeiten": zeiten, "T": T, "NY": NY, "NX": NX,
            "lat0": float(lat[0]), "lon0": float(lon[0]), "dlat": float(lat[1] - lat[0]), "dlon": float(lon[1] - lon[0]),
            "einheit": "mm/s", "land": LAND}
    os.replace(tmp, os.path.join(AUS, "cmems_uv.i16"))
    with open(os.path.join(AUS, "cmems_meta.json.neu"), "w") as f:
        json.dump(meta, f)
    os.replace(os.path.join(AUS, "cmems_meta.json.neu"), os.path.join(AUS, "cmems_meta.json"))
    shutil.rmtree(roh, ignore_errors=True)
    t0 = datetime.fromtimestamp(zeiten[0], timezone.utc)
    t1 = datetime.fromtimestamp(zeiten[-1], timezone.utc)
    print(f"OK: {T} Zeitschritte {t0:%d.%m. %H}–{t1:%d.%m. %H} UTC, {NX}x{NY}, "
          f"{os.path.getsize(os.path.join(AUS, 'cmems_uv.i16')) // 2**20} MB")


if __name__ == "__main__":
    main()
