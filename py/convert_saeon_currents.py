#!/usr/bin/env python3
"""Parse SAEON / DEA-MIMS ADCP hourly-current text files to per-station CSVs.

Input:  currents/South_Africa_SAEON/raw/*.zip
Output: currents/South_Africa_SAEON/<STATION>.csv  (time,speed,direction in m/s, deg true)
        currents/South_Africa_SAEON/_stations.json

Text format (confirmed for Walters Shoal, Algoa Bay, KZN Bight bundles):
  - First ~35 lines: # comments with Latitude, Longitude, Bin size, etc.
  - Row 36: empty col1, then timestamps (dd/mm/yyyy HH:MM) separated by ','
  - Rows 37..72: magnitude matrix (cm/s), col1 = bin depth, col2+ = values per timestamp
  - Row 73: timestamps header (duplicate of row 36)
  - Rows 74..: direction matrix (degrees true north), same layout as magnitude
  - No-data sentinel: -9999
Multiple deployments (D1/D2/D3) per station are concatenated.
"""
import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from io import TextIOWrapper
from pathlib import Path

import numpy as np
import pandas as pd

HOME = Path.home()
RAW_DIR = HOME / 'currents' / 'South_Africa_SAEON' / 'raw'
OUT_DIR = HOME / 'currents' / 'South_Africa_SAEON'

# Mooring prefix -> human-readable name
STATION_NAMES = {
    'ABay01': 'Algoa Bay ABay01',
    'ABay02': 'Algoa Bay ABay02',
    'ABay03': 'Algoa Bay ABay03',
    'ABay04': 'Algoa Bay ABay04',
    'CR01':   'Cape Recife CR01',
    'PA01':   'Port Alfred PA01',
    'PA02':   'Port Alfred PA02',
    'Dbn01':  'Durban Dbn01',
    'Dbn03':  'Durban Dbn03',
    'RiB01':  'Richards Bay RiB01',
    'RiB02':  'Richards Bay RiB02',
    'Sezela': 'Sezela Mooring',
    'PJ':     'Port St Johns',
    'WSN01':  'Walters Shoal WSN01',
    'WSS01':  'Walters Shoal WSS01',
}

# fname like "ABay01_D1_hourly_currents_6Dec2013_7Dec2014.txt"
STATION_RX = re.compile(r'([A-Za-z]+\d*)_(D\d+)?_?hourly_currents', re.IGNORECASE)


def station_from_filename(fname: str):
    base = Path(fname).name
    m = STATION_RX.match(base)
    if not m:
        return None
    prefix = m.group(1)
    # "Sezela" no digit; keep as-is
    return prefix


def parse_text(raw: str):
    """Return (lat, lon, depth_m, bin_depths_arr, timestamps_arr, mag, direc).
    mag/direc shape (nbins, ntimes) in cm/s / deg, NaN where -9999.
    """
    lines = raw.splitlines()
    lat = lon = depth = None
    for L in lines[:40]:
        low = L.lower()
        if 'latitude' in low and lat is None:
            m = re.search(r'([-+]?\d+\.?\d*)', L.split(':', 1)[-1])
            if m: lat = float(m.group(1))
        elif 'longitude' in low and lon is None:
            m = re.search(r'([-+]?\d+\.?\d*)', L.split(':', 1)[-1])
            if m: lon = float(m.group(1))
        elif 'deployment depth' in low or 'bottom depth' in low:
            m = re.search(r'(\d+(?:\.\d+)?)', L)
            if m: depth = float(m.group(1))

    # Find the two header rows (timestamps). Each starts with ',' and contains '/'.
    header_idx = []
    for i, L in enumerate(lines):
        if L.startswith(',') and '/' in L and ':' in L:
            header_idx.append(i)
            if len(header_idx) == 2:
                break
    if len(header_idx) != 2:
        raise ValueError(f'expected 2 timestamp headers, got {len(header_idx)}')

    def split_row(L):
        return L.split(',')

    t_hdr = split_row(lines[header_idx[0]])[1:]
    timestamps = pd.to_datetime(t_hdr, format='%d/%m/%Y %H:%M', errors='coerce')

    def read_block(start_i, end_i):
        depths, rows = [], []
        for L in lines[start_i:end_i]:
            if not L.strip() or L.startswith('#'):
                continue
            parts = split_row(L)
            try:
                d = float(parts[0])
            except ValueError:
                break
            vals = np.full(len(timestamps), np.nan, dtype=float)
            for j, v in enumerate(parts[1:len(timestamps)+1]):
                v = v.strip()
                if not v: continue
                try:
                    x = float(v)
                    if x <= -9990:
                        continue
                    vals[j] = x
                except ValueError:
                    pass
            depths.append(d)
            rows.append(vals)
        return np.array(depths), np.array(rows) if rows else np.empty((0, len(timestamps)))

    # Magnitude block: from header_idx[0]+1 until header_idx[1]
    bin_depths, mag = read_block(header_idx[0] + 1, header_idx[1])
    # Direction block: from header_idx[1]+1 to end
    _, direc = read_block(header_idx[1] + 1, len(lines))
    if mag.shape != direc.shape:
        # align by min number of bins
        n = min(mag.shape[0], direc.shape[0])
        mag, direc = mag[:n], direc[:n]
        bin_depths = bin_depths[:n]
    return lat, lon, depth, bin_depths, timestamps, mag, direc


def depth_average(timestamps, mag_cm, direc_deg):
    """Return DataFrame with time, speed (m/s), direction (deg)."""
    # convert to u,v (east, north)
    rad = np.deg2rad(direc_deg)
    u = mag_cm * np.sin(rad) / 100.0
    v = mag_cm * np.cos(rad) / 100.0
    # NaN-mean over bins
    with np.errstate(invalid='ignore'):
        u_mean = np.nanmean(u, axis=0)
        v_mean = np.nanmean(v, axis=0)
    speed = np.sqrt(u_mean**2 + v_mean**2)
    direction = np.rad2deg(np.arctan2(u_mean, v_mean)) % 360.0
    df = pd.DataFrame({'time': timestamps, 'speed': speed, 'direction': direction})
    df = df.dropna(subset=['time']).dropna(subset=['speed'])
    df = df[df['speed'] < 15.0]
    df = df[(df['direction'] >= 0) & (df['direction'] <= 360)]
    return df.set_index('time').sort_index()


def process_zip(zip_path: Path):
    """Return {station_code: [(df, meta), ...]} for every hourly_currents txt."""
    out = defaultdict(list)
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith('.txt'): continue
            if 'hourly' not in name.lower(): continue
            if 'current' not in name.lower(): continue
            if 'temperature' in name.lower(): continue
            code = station_from_filename(name)
            if not code: continue
            with zf.open(name) as fh:
                raw = TextIOWrapper(fh, encoding='latin-1').read()
            try:
                lat, lon, depth, bins, ts, mag, direc = parse_text(raw)
            except Exception as e:
                print(f'  parse error in {name}: {e}', file=sys.stderr)
                continue
            if lat is None or lon is None:
                print(f'  {name}: missing lat/lon, skip', file=sys.stderr)
                continue
            df = depth_average(ts, mag, direc)
            if df.empty:
                continue
            meta = {'lat': lat, 'lon': lon, 'depth': depth,
                    'source_file': name, 'nbins': int(mag.shape[0])}
            out[code].append((df, meta))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_stations = defaultdict(list)

    for zp in sorted(RAW_DIR.glob('*.zip')):
        print(f'--- {zp.name}')
        bundles = process_zip(zp)
        for code, entries in bundles.items():
            all_stations[code].extend(entries)
            for df, meta in entries:
                print(f'  {code}: {len(df)} pts {df.index[0].date()}..{df.index[-1].date()} '
                      f'@ {meta["lat"]:.3f},{meta["lon"]:.3f}')

    # Concatenate deployments per station
    stations_meta = {}
    for code, entries in sorted(all_stations.items()):
        dfs = [e[0] for e in entries]
        lats = [e[1]['lat'] for e in entries]
        lons = [e[1]['lon'] for e in entries]
        # Drop duplicates (PJ appears in both 29112024 and 31112024/33112024 bundles,
        # but we only downloaded 29112024. Still be safe.)
        df = pd.concat(dfs).sort_index()
        df = df[~df.index.duplicated(keep='first')]
        if len(df) < 500:  # skip too-short stations
            print(f'  SKIP {code}: only {len(df)} pts')
            continue
        out_csv = OUT_DIR / f'{code}.csv'
        if out_csv.exists() and not args.overwrite:
            print(f'  {code}: CSV exists, skip')
        else:
            df.to_csv(out_csv)
        stations_meta[code] = {
            'name': STATION_NAMES.get(code, code),
            'lat': round(float(np.mean(lats)), 4),
            'lon': round(float(np.mean(lons)), 4),
            'n_obs': int(len(df)),
            'start': str(df.index[0])[:10],
            'end': str(df.index[-1])[:10],
            'source': 'SAEON / DEA-MIMS hourly ADCP, depth-averaged',
        }

    meta_file = OUT_DIR / '_stations.json'
    with open(meta_file, 'w') as f:
        json.dump(stations_meta, f, indent=2, ensure_ascii=False)
    print(f'\nWrote {len(stations_meta)} stations to {OUT_DIR}')


if __name__ == '__main__':
    main()
