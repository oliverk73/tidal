#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Caribbean stations
(Cuba + Jamaica + Bahamas). Research Quality dataset, millimeters.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Caribbean_UHSLC_CubaJamaicaBahamas'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

STATIONS = [
    # Cuba
    {'uhslc_id': 244, 'name': 'Gibara',           'lat': 21.117, 'lon': -76.117, 'country': 'Cuba',    'tz': 'America/Havana',  'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 251, 'name': 'Guantanamo Bay',   'lat': 19.907, 'lon': -75.147, 'country': 'Cuba',    'tz': 'America/Havana',  'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    # Jamaica
    {'uhslc_id': 782, 'name': 'Port Royal',       'lat': 17.933, 'lon': -76.850, 'country': 'Jamaica', 'tz': 'America/Jamaica', 'gloss_id': 210,  'dataset': 'global_hourly_rqds'},
    # Bahamas
    {'uhslc_id': 257, 'name': 'Settlement Point', 'lat': 26.690, 'lon': -78.983, 'country': 'Bahamas', 'tz': 'America/Nassau',  'gloss_id': 211,  'dataset': 'global_hourly_rqds'},
]
# Note: UHSLC 239 (Siboney, Cuba) has only ~1 year of data — insufficient for
# 175-constituent UTide fit, skipped.


def download_station(station):
    sid = station['uhslc_id']
    name = station['name']
    dataset = station['dataset']
    safe_name = name.replace(' ', '_').replace("'", '').replace('.', '').replace(',', '')
    csv_path = os.path.join(OUTPUT_DIR, f'{sid}_{safe_name}.csv')

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 10000:
        n_lines = sum(1 for _ in open(csv_path))
        print(f"  Already downloaded ({n_lines} lines), skipping.")
        return True

    url = f'{ERDDAP_BASE}/{dataset}.csv?time,sea_level,station_name&uhslc_id={sid}'
    print(f"  Downloading from {dataset}...", end='', flush=True)

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=180)
            if resp.status_code == 404:
                print(f" not found (404)")
                return False
            resp.raise_for_status()

            lines = resp.text.strip().split('\n')
            if len(lines) < 3:
                print(f" no data")
                return False

            rows = []
            for line in lines[2:]:
                parts = line.split(',')
                if len(parts) >= 2:
                    ts = parts[0]
                    val = parts[1]
                    if val and val != 'NaN':
                        try:
                            rows.append((ts, float(val) / 1000.0))
                        except ValueError:
                            pass

            if not rows:
                print(f" no valid data")
                return False

            df = pd.DataFrame(rows, columns=['time', 'waterlevel_m'])
            df = df.drop_duplicates(subset='time').sort_values('time')
            df.to_csv(csv_path, index=False)

            n = len(df)
            first = df['time'].iloc[0][:10]
            last = df['time'].iloc[-1][:10]
            years = n / (24 * 365.25)
            print(f" {n} values ({years:.1f} years, {first} - {last})")
            return True

        except requests.exceptions.Timeout:
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f" [timeout, retry in {wait}s]", end='', flush=True)
                time.sleep(wait)
            else:
                print(f" TIMEOUT")
                return False
        except Exception as e:
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f" [error, retry in {wait}s]", end='', flush=True)
                time.sleep(wait)
            else:
                print(f" ERROR: {e}")
                return False

    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download Hourly Sea Level Data - UHSLC ERDDAP (Cuba + Jamaica)")
    print("=" * 70)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Stations: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['country']})")
        if download_station(station):
            success += 1
        time.sleep(3)

    print(f"\n{'='*70}")
    print(f"Result: {success}/{len(STATIONS)} successful")

    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.csv'):
            path = os.path.join(OUTPUT_DIR, f)
            size_kb = os.path.getsize(path) / 1024
            n_lines = sum(1 for _ in open(path)) - 1
            years = n_lines / (24 * 365.25)
            print(f"  {f}: {size_kb:.0f} KB, {n_lines} values ({years:.1f} years)")


if __name__ == '__main__':
    main()
