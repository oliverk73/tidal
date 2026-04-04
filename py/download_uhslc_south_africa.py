#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for South African tide stations.
Uses Research Quality dataset where available, falls back to Fast Delivery.
Downloads only the most recent ~19 years (one nodal cycle).

Data in millimeters, relative to station datum.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/SouthAfrica_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

STATIONS = [
    # --- Namibia (operated by SANHO) ---
    {'uhslc_id': 702, 'name': 'Luderitz',       'lat': -26.650, 'lon': 15.150, 'province': 'Namibia',        'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},

    # --- West Coast (Atlantic) ---
    {'uhslc_id': 701, 'name': 'Port Nolloth',   'lat': -29.250, 'lon': 16.867, 'province': 'Northern Cape',  'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 703, 'name': 'Saldanha Bay',   'lat': -33.017, 'lon': 17.950, 'province': 'Western Cape',   'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 704, 'name': 'Cape Town',       'lat': -33.900, 'lon': 18.433, 'province': 'Western Cape',   'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 221, 'name': "Simon's Town",    'lat': -34.183, 'lon': 18.433, 'province': 'Western Cape',   'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},

    # --- South Coast (Indian Ocean) ---
    {'uhslc_id': 185, 'name': 'Mossel Bay',     'lat': -34.183, 'lon': 22.133, 'province': 'Western Cape',   'water': 'Indian Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 186, 'name': 'Knysna',         'lat': -34.050, 'lon': 23.045, 'province': 'Western Cape',   'water': 'Indian Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 184, 'name': 'Port Elizabeth',  'lat': -33.960, 'lon': 25.630, 'province': 'Eastern Cape',   'water': 'Indian Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 187, 'name': 'East London',    'lat': -33.017, 'lon': 27.917, 'province': 'Eastern Cape',   'water': 'Indian Ocean',   'dataset': 'global_hourly_rqds'},

    # --- East Coast (Indian Ocean) ---
    {'uhslc_id': 181, 'name': 'Durban',         'lat': -29.867, 'lon': 31.050, 'province': 'KwaZulu-Natal',  'water': 'Indian Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 188, 'name': "Richard's Bay",  'lat': -28.800, 'lon': 32.083, 'province': 'KwaZulu-Natal',  'water': 'Indian Ocean',   'dataset': 'global_hourly_rqds'},
]


def download_station(station):
    """Download all hourly data for one station from UHSLC ERDDAP."""
    sid = station['uhslc_id']
    name = station['name']
    dataset = station['dataset']
    safe_name = name.replace(' ', '_').replace("'", '').replace('.', '').replace(',', '')

    csv_path = os.path.join(OUTPUT_DIR, f'{sid}_{safe_name}.csv')

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 10000:
        n_lines = sum(1 for _ in open(csv_path))
        print(f"  Already downloaded ({n_lines} lines), skipping.")
        return True

    datasets_to_try = [dataset]
    if dataset == 'global_hourly_fast':
        datasets_to_try.append('global_hourly_rqds')
    else:
        datasets_to_try.append('global_hourly_fast')

    for ds in datasets_to_try:
        url = f'{ERDDAP_BASE}/{ds}.csv?time,sea_level,station_name&uhslc_id={sid}'
        print(f"  Downloading from {ds}...", end='', flush=True)

        for attempt in range(3):
            try:
                resp = requests.get(url, timeout=180)
                if resp.status_code == 404:
                    print(f" not found (404)", end='')
                    break
                resp.raise_for_status()

                lines = resp.text.strip().split('\n')
                if len(lines) < 3:
                    print(f" no data", end='')
                    break

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
                    print(f" no valid data", end='')
                    break

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
                    print(f" TIMEOUT", end='')
                    break
            except Exception as e:
                if attempt < 2:
                    wait = 30 * (attempt + 1)
                    print(f" [error, retry in {wait}s]", end='', flush=True)
                    time.sleep(wait)
                else:
                    print(f" ERROR: {e}", end='')
                    break

        print()

    print(f"  FAILED: no data from any dataset")
    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download Hourly Sea Level Data - UHSLC ERDDAP (South Africa)")
    print("=" * 70)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Stations: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['province']})")
        if download_station(station):
            success += 1
        time.sleep(3)

    print(f"\n{'='*70}")
    print(f"Result: {success}/{len(STATIONS)} successful")

    total_mb = 0
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.csv'):
            path = os.path.join(OUTPUT_DIR, f)
            size_mb = os.path.getsize(path) / (1024*1024)
            total_mb += size_mb
            n_lines = sum(1 for _ in open(path)) - 1
            years = n_lines / (24 * 365.25)
            print(f"  {f}: {size_mb:.1f} MB, {n_lines} values ({years:.1f} years)")
    print(f"  Total: {total_mb:.1f} MB")


if __name__ == '__main__':
    main()
