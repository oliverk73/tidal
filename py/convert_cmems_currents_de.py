#!/usr/bin/env python3
"""Convert CMEMS in-situ NetCDF files to CSV (time, speed, direction).

Handles multi-depth files (picks shallowest with most data),
merges MO + AD partitions for same station, and writes metadata.
"""
import os, json, glob
import numpy as np
import pandas as pd
import xarray as xr

NC_DIR   = '/home/oliver/currents/Germany'
OUT_DIR  = NC_DIR
LAT_MIN, LAT_MAX = 53.0, 56.0
LON_MIN, LON_MAX = 5.5, 15.0

STATION_NAMES = {
    '6600024': 'Darßer Schwelle',
    '6600023': 'Fehmarn Belt',
    '6200087': 'NSBIII Nordsee',
    '1000044': 'Kieler Leuchtturm',
    'N10WBenthicNode': 'N10W Benthic Node',
    'N9NBenthicNode': 'N9N Benthic Node',
    'N7SBenthicNode': 'N7S Benthic Node',
    'N6SBenthicNode': 'N6S Benthic Node',
    'LightshipElbe1': 'Feuerschiff Elbe 1',
    'LightshipElbe4': 'Feuerschiff Elbe 4',
    'LightshipBremen': 'Feuerschiff Bremen',
    'LightshipFehmarnbelt': 'Feuerschiff Fehmarnbelt',
    'LightshipFlensburg': 'Feuerschiff Flensburg',
    'LightshipKiel2': 'Feuerschiff Kiel 2',
    'LightshipKiel3': 'Feuerschiff Kiel 3',
}


def extract_station(ds):
    code = ds.attrs.get('platform_code', '?')
    lat = float(ds.attrs.get('geospatial_lat_min', 0))
    lon = float(ds.attrs.get('geospatial_lon_min', 0))
    return code, lat, lon


def pick_best_depth(arr):
    """For 2D array (time, depth), return 1D of shallowest depth with most data."""
    if arr.ndim == 1:
        return arr
    counts = [np.count_nonzero(~np.isnan(arr[:, d])) for d in range(arr.shape[1])]
    best = 0
    for d in range(arr.shape[1]):
        if counts[d] > counts[best] * 0.9:
            best = d
            break
    return arr[:, best]


def nc_to_df(path):
    ds = xr.open_dataset(path)
    code, lat, lon = extract_station(ds)

    if not (LAT_MIN < lat < LAT_MAX and LON_MIN < lon < LON_MAX):
        ds.close()
        return None, None, None, None

    times = ds['TIME'].values

    if 'HCSP' in ds and 'HCDT' in ds:
        speed = pick_best_depth(ds['HCSP'].values)
        direction = pick_best_depth(ds['HCDT'].values)
    elif 'EWCT' in ds and 'NSCT' in ds:
        ewct = pick_best_depth(ds['EWCT'].values)
        nsct = pick_best_depth(ds['NSCT'].values)
        speed = np.sqrt(ewct**2 + nsct**2)
        direction = np.rad2deg(np.arctan2(ewct, nsct)) % 360
    else:
        ds.close()
        return None, None, None, None

    # QC filter: use QC flags if available
    if 'HCSP_QC' in ds:
        qc = pick_best_depth(ds['HCSP_QC'].values)
        good = np.isin(qc, [1, 2])  # 1=good, 2=probably good
        speed = np.where(good, speed, np.nan)
        direction = np.where(good, direction, np.nan)

    ds.close()

    df = pd.DataFrame({'time': times, 'speed': speed, 'direction': direction})
    df = df.dropna()
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    df = df[(df['speed'] >= 0) & (df['speed'] < 15) & df['direction'].between(0, 360)]

    return code, lat, lon, df


def main():
    nc_files = sorted(glob.glob(os.path.join(NC_DIR, '*.nc')))

    station_dfs = {}
    station_meta = {}

    for f in nc_files:
        name = os.path.basename(f)
        code, lat, lon, df = nc_to_df(f)
        if df is None or df.empty:
            continue

        if code in station_dfs:
            station_dfs[code] = pd.concat([station_dfs[code], df])
            station_dfs[code] = station_dfs[code][~station_dfs[code].index.duplicated(keep='first')].sort_index()
        else:
            station_dfs[code] = df
            station_meta[code] = {'lat': lat, 'lon': lon}

        print(f'{name:50s} -> {code:25s} {len(df):>8d} Werte')

    print(f'\n{len(station_dfs)} Stationen nach Merge:')
    meta = {}
    for code, df in sorted(station_dfs.items()):
        csv_path = os.path.join(OUT_DIR, f'{code}.csv')
        df.to_csv(csv_path)
        m = station_meta[code]
        display_name = STATION_NAMES.get(code, code)
        years = (df.index[-1] - df.index[0]).days / 365.25
        meta[code] = {
            'name': display_name,
            'lat': m['lat'], 'lon': m['lon'],
            'n_obs': len(df),
            'start': str(df.index[0])[:10],
            'end': str(df.index[-1])[:10],
        }
        print(f'  {code:25s} {display_name:30s} {len(df):>8d} ({years:.1f}a) {str(df.index[0])[:10]}..{str(df.index[-1])[:10]}')

    with open(os.path.join(OUT_DIR, '_stations.json'), 'w') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f'\n{len(meta)} CSVs + _stations.json geschrieben.')


if __name__ == '__main__':
    main()
