#!/usr/bin/env python3
"""Convert IMOS ANMN hourly velocity NCs to per-station CSVs.

Input:  currents/Australia_IMOS/raw/<SITE>.nc
Output: currents/Australia_IMOS/<SITE>.csv (time,speed,direction)
        currents/Australia_IMOS/_stations.json

Strategy: depth-average UCUR/VCUR over all CELL_INDEX bins at each timestamp
(tidal currents on a shelf are largely barotropic, so this gives a clean signal).
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

HOME = Path.home()
RAW_DIR = HOME / 'currents' / 'Australia_IMOS' / 'raw'
OUT_DIR = HOME / 'currents' / 'Australia_IMOS'

QC_GOOD = [1, 2]


def load_and_aggregate(path):
    """Returns (df, lat, lon, site_code, title) or (None, ...) on failure."""
    try:
        ds = xr.open_dataset(path, decode_times=True)
    except Exception as e:
        return None, None, None, None, None, f'open_error: {e}'

    site = ds.attrs.get('site_code', Path(path).stem)
    title = ds.attrs.get('title', site)

    # Instrument-level lat/lon: take first (usually all within a few m)
    try:
        lat = float(ds['LATITUDE'].values.mean())
        lon = float(ds['LONGITUDE'].values.mean())
    except Exception:
        lat = (float(ds.attrs.get('geospatial_lat_min', 'nan'))
               + float(ds.attrs.get('geospatial_lat_max', 'nan'))) / 2
        lon = (float(ds.attrs.get('geospatial_lon_min', 'nan'))
               + float(ds.attrs.get('geospatial_lon_max', 'nan'))) / 2

    if 'UCUR' not in ds or 'VCUR' not in ds or 'TIME' not in ds:
        ds.close()
        return None, lat, lon, site, title, 'no_current_vars'

    u = ds['UCUR'].values
    v = ds['VCUR'].values
    t = ds['TIME'].values

    # QC: flags 1 (good) and 2 (probably good). UCUR_quality_control / VCUR_...
    uq = ds['UCUR_quality_control'].values if 'UCUR_quality_control' in ds else None
    vq = ds['VCUR_quality_control'].values if 'VCUR_quality_control' in ds else None

    if uq is not None:
        bad = ~np.isin(uq, QC_GOOD)
        u = np.where(bad, np.nan, u)
    if vq is not None:
        bad = ~np.isin(vq, QC_GOOD)
        v = np.where(bad, np.nan, v)

    ds.close()

    # Flat ragged: OBSERVATION dim, one u/v per (time, cell, instrument)
    df = pd.DataFrame({'time': pd.to_datetime(t, errors='coerce'),
                       'u': u, 'v': v})
    df = df.dropna()
    if df.empty:
        return None, lat, lon, site, title, 'empty_after_qc'

    # Depth-average by timestamp
    gb = df.groupby('time').agg({'u': 'mean', 'v': 'mean'})
    gb['speed'] = np.sqrt(gb['u']**2 + gb['v']**2)
    gb['direction'] = np.rad2deg(np.arctan2(gb['u'], gb['v'])) % 360

    out = gb[['speed', 'direction']].sort_index()
    # range sanity
    out = out[(out['speed'] < 15) & out['direction'].between(0, 360)]
    if out.empty:
        return None, lat, lon, site, title, 'empty_after_range'

    return out, lat, lon, site, title, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--overwrite', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta_file = OUT_DIR / '_stations.json'
    meta = {}
    if meta_file.exists():
        with open(meta_file) as f: meta = json.load(f)

    nc_files = sorted(glob.glob(str(RAW_DIR / '*.nc')))
    print(f'{len(nc_files)} NC files in {RAW_DIR}')

    total_written = 0
    errors = {}
    for nc in nc_files:
        site = Path(nc).stem
        csv_path = OUT_DIR / f'{site}.csv'
        if csv_path.exists() and not args.overwrite:
            print(f'  {site}: exists, skip')
            continue

        df, lat, lon, code, title, reason = load_and_aggregate(nc)
        if df is None:
            print(f'  {site}: {reason}')
            errors[site] = reason
            continue

        years = (df.index[-1] - df.index[0]).days / 365.25
        print(f'  {site:12s} {len(df):>7d} pts ({years:4.1f}a) '
              f'{str(df.index[0])[:10]}..{str(df.index[-1])[:10]} @ {lat:.3f},{lon:.3f}')

        if args.dry_run: continue

        df.to_csv(csv_path)
        meta[code or site] = {
            'name': code or site,
            'title': title,
            'lat': round(lat, 4),
            'lon': round(lon, 4),
            'n_obs': int(len(df)),
            'start': str(df.index[0])[:10],
            'end': str(df.index[-1])[:10],
            'source': 'IMOS ANMN hourly_timeseries FV02',
        }
        total_written += 1

    if not args.dry_run:
        with open(meta_file, 'w') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f'\nWrote {total_written} CSVs, {len(errors)} errors: {set(errors.values())}')


if __name__ == '__main__':
    main()
