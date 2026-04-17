#!/usr/bin/env python3
"""Convert CMEMS in-situ NetCDFs in currents/cmems_raw/ to per-country CSVs.

Output layout mirrors the existing German pipeline:
    currents/<Country>/<platform_code>.csv
    currents/<Country>/_stations.json

Country is assigned by bbox. If a station's coords match multiple bboxes,
priority order is used (e.g. BE before NL/FR/UK for the southern North Sea).
Unassigned stations go to currents/_unclassified/.

Does NOT re-process platforms already present in any country directory.
Re-run is idempotent: existing CSVs are skipped unless --overwrite is passed.
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
RAW_DIR = HOME / 'currents' / 'cmems_raw'
CURRENTS_DIR = HOME / 'currents'

# (country_dirname, lat_min, lat_max, lon_min, lon_max)
# Order = priority; first match wins.
COUNTRY_BBOXES = [
    # Narrow overrides before wider ones (the Belgian coast is inside NL's bbox otherwise)
    ('Belgium',         51.00, 51.85,   2.00,   3.40),
    ('Germany',         53.20, 56.00,   5.50,  15.00),
    ('Netherlands',     51.20, 54.00,   2.50,   7.30),
    ('Denmark',         54.00, 58.00,   7.20,  13.50),
    ('France_Channel',  48.80, 51.20,  -2.00,   2.80),
    ('France_Atlantic', 43.30, 48.80,  -5.20,  -1.00),    # excludes Santander/Bilbao (ES)
    ('France_Med',      42.30, 44.00,   3.00,  10.00),    # mainland + Corsica, above ES Catalonia
    ('UK',              49.00, 61.00, -10.00,   2.00),
    ('Ireland',         51.00, 56.00, -11.50,  -5.50),
    ('Norway',          57.00, 72.00,   4.00,  32.00),
    ('Sweden',          55.00, 66.50,  10.50,  24.50),
    ('Finland',         59.00, 66.00,  19.00,  29.00),
    ('Estonia',         57.50, 60.00,  21.00,  28.50),
    ('Latvia',          55.50, 58.20,  20.50,  28.00),
    ('Lithuania',       55.00, 56.50,  20.50,  23.00),
    ('Poland',          53.80, 55.00,  14.00,  20.00),
    ('Spain_Atlantic',  42.00, 44.50, -10.50,  -1.75),    # Cantabrian + Galicia offshore
    ('Spain_Med',       35.80, 42.30,  -6.00,   4.50),    # Balearics to 4.5E
    ('Portugal',        35.00, 42.30, -10.50,  -6.00),
    ('Italy',           36.00, 46.00,   6.00,  19.50),
    ('Croatia',         42.00, 46.00,  13.00,  20.00),
    ('Slovenia',        45.00, 46.00,  13.00,  14.50),
    ('Malta',           35.70, 36.20,  14.00,  15.00),
    ('Greece',          34.00, 42.00,  19.00,  29.00),
    ('Cyprus',          34.30, 35.80,  32.00,  35.00),
    ('Turkey',          36.00, 42.50,  26.00,  45.00),
    ('Romania',         43.50, 45.50,  27.80,  30.00),
    ('Bulgaria',        41.90, 44.00,  27.30,  28.80),
    ('Iceland',         62.50, 67.50, -25.00, -12.00),
    ('FaroeIslands',    61.00, 63.00,  -8.00,  -5.00),
]

CURRENT_VARS_SD = ('HCSP', 'HCDT')        # speed + direction (degrees)
CURRENT_VARS_UV = ('EWCT', 'NSCT')        # east + north (m/s)


def assign_country(lat, lon):
    for name, lat_min, lat_max, lon_min, lon_max in COUNTRY_BBOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return None


def pick_best_depth(arr):
    """For 2D array (time, depth), return 1D of shallowest depth with most data."""
    if arr.ndim == 1:
        return arr
    if arr.shape[1] == 0:
        return arr[:, 0] if arr.shape[1] == 1 else np.full(arr.shape[0], np.nan)
    counts = [np.count_nonzero(~np.isnan(arr[:, d])) for d in range(arr.shape[1])]
    best = int(np.argmax(counts))
    # Prefer shallowest non-empty if close to the max
    for d in range(arr.shape[1]):
        if counts[d] > counts[best] * 0.9:
            best = d
            break
    return arr[:, best]


def nc_to_df(path):
    """Returns (platform_code, lat, lon, df or None, reason_if_none)."""
    try:
        ds = xr.open_dataset(path)
    except Exception as e:
        return None, None, None, None, f'open_error: {e}'

    code = ds.attrs.get('platform_code', os.path.basename(path).replace('.nc', ''))
    try:
        lat = float(ds.attrs.get('geospatial_lat_min'))
        lon = float(ds.attrs.get('geospatial_lon_min'))
    except (TypeError, ValueError):
        ds.close()
        return code, None, None, None, 'no_coords'

    times = ds['TIME'].values if 'TIME' in ds else None
    if times is None or len(times) == 0:
        ds.close()
        return code, lat, lon, None, 'no_time'

    if all(v in ds for v in CURRENT_VARS_SD):
        speed = pick_best_depth(ds['HCSP'].values)
        direction = pick_best_depth(ds['HCDT'].values)
        qc_key = 'HCSP_QC'
    elif all(v in ds for v in CURRENT_VARS_UV):
        ewct = pick_best_depth(ds['EWCT'].values)
        nsct = pick_best_depth(ds['NSCT'].values)
        speed = np.sqrt(ewct**2 + nsct**2)
        direction = np.rad2deg(np.arctan2(ewct, nsct)) % 360
        qc_key = 'EWCT_QC'
    else:
        ds.close()
        return code, lat, lon, None, 'no_current_vars'

    # QC filter: keep flags 1 (good) and 2 (probably good)
    if qc_key in ds:
        qc = pick_best_depth(ds[qc_key].values)
        good = np.isin(qc, [1, 2])
        speed = np.where(good, speed, np.nan)
        direction = np.where(good, direction, np.nan)

    ds.close()

    df = pd.DataFrame({'time': times, 'speed': speed, 'direction': direction})
    df = df.dropna()
    if df.empty:
        return code, lat, lon, None, 'empty_after_qc'
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    df = df[(df['speed'] >= 0) & (df['speed'] < 15)
            & df['direction'].between(0, 360)]
    if df.empty:
        return code, lat, lon, None, 'empty_after_range_filter'
    return code, lat, lon, df, None


def merge_df(existing, new):
    combined = pd.concat([existing, new])
    combined = combined[~combined.index.duplicated(keep='first')].sort_index()
    return combined


def load_or_init_stations(dir_path):
    meta_file = dir_path / '_stations.json'
    if meta_file.exists():
        with open(meta_file) as f:
            return json.load(f)
    return {}


def save_stations(dir_path, meta):
    meta_file = dir_path / '_stations.json'
    with open(meta_file, 'w') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--overwrite', action='store_true',
                    help='re-process platforms even if CSV already exists')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    nc_files = sorted(glob.glob(str(RAW_DIR / '*.nc')))
    if not nc_files:
        print(f'No NetCDF files in {RAW_DIR}', file=sys.stderr)
        return

    # First pass: group by platform_code so multi-file platforms merge
    per_platform = {}  # code -> [(path, lat, lon, df), ...]
    reasons = {}       # path -> reason skipped
    for f in nc_files:
        code, lat, lon, df, reason = nc_to_df(f)
        if df is None:
            reasons[f] = reason or 'unknown'
            continue
        per_platform.setdefault(code, []).append((f, lat, lon, df))

    # Figure out "already present elsewhere": scan all country dirs
    existing_elsewhere = set()
    for sub in CURRENTS_DIR.iterdir():
        if not sub.is_dir() or sub.name in ('cmems_raw',):
            continue
        for csv in sub.glob('*.csv'):
            s = csv.stem
            if not s.startswith('_'):
                existing_elsewhere.add(s)

    # Country bucketing
    buckets = {}  # country -> [(code, lat, lon, df)]
    unclassified = []
    skipped_existing = []
    for code, parts in sorted(per_platform.items()):
        lat = np.mean([p[1] for p in parts if p[1] is not None])
        lon = np.mean([p[2] for p in parts if p[2] is not None])
        df = parts[0][3]
        for _, _, _, d in parts[1:]:
            df = merge_df(df, d)

        country = assign_country(lat, lon)
        target_csv_exists = False
        if country:
            target = CURRENTS_DIR / country / f'{code}.csv'
            target_csv_exists = target.exists()

        # skip if already present in any country dir and not overwriting
        if code in existing_elsewhere and not args.overwrite:
            skipped_existing.append(code)
            continue
        if target_csv_exists and not args.overwrite:
            skipped_existing.append(code)
            continue

        if country is None:
            unclassified.append((code, lat, lon, df))
        else:
            buckets.setdefault(country, []).append((code, lat, lon, df))

    # Write
    print(f'{len(per_platform)} platforms processed, '
          f'{len(skipped_existing)} already present (skipped), '
          f'{len(unclassified)} unclassified, '
          f'{len(reasons)} NC files skipped '
          f'(reasons: {set(reasons.values())})\n')

    total_written = 0
    for country in sorted(buckets):
        cdir = CURRENTS_DIR / country
        if not args.dry_run:
            cdir.mkdir(parents=True, exist_ok=True)
        meta = load_or_init_stations(cdir) if not args.dry_run else {}
        print(f'[{country}]')
        for code, lat, lon, df in buckets[country]:
            years = (df.index[-1] - df.index[0]).days / 365.25
            print(f'  {code:30s} {len(df):>8d}  ({years:5.1f}a) '
                  f'{str(df.index[0])[:10]}..{str(df.index[-1])[:10]}  @ {lat:.3f},{lon:.3f}')
            if args.dry_run:
                continue
            csv_path = cdir / f'{code}.csv'
            df.to_csv(csv_path)
            meta[code] = {
                'name': code,
                'lat': round(lat, 4), 'lon': round(lon, 4),
                'n_obs': len(df),
                'start': str(df.index[0])[:10],
                'end': str(df.index[-1])[:10],
                'source': 'cmems',
            }
            total_written += 1
        if not args.dry_run:
            save_stations(cdir, meta)
        print(f'  -> {len(buckets[country])} stations\n')

    if unclassified:
        u_dir = CURRENTS_DIR / '_unclassified'
        if not args.dry_run:
            u_dir.mkdir(parents=True, exist_ok=True)
        meta = load_or_init_stations(u_dir) if not args.dry_run else {}
        print('[_unclassified]  (fix country bbox or add manually)')
        for code, lat, lon, df in unclassified:
            print(f'  {code:30s} @ {lat:.3f},{lon:.3f}  n={len(df)}')
            if args.dry_run:
                continue
            csv_path = u_dir / f'{code}.csv'
            df.to_csv(csv_path)
            meta[code] = {'name': code, 'lat': round(lat, 4), 'lon': round(lon, 4),
                          'n_obs': len(df), 'source': 'cmems',
                          'start': str(df.index[0])[:10], 'end': str(df.index[-1])[:10]}
            total_written += 1
        if not args.dry_run:
            save_stations(u_dir, meta)

    if not args.dry_run:
        print(f'\nTotal: {total_written} CSVs written.')


if __name__ == '__main__':
    main()
