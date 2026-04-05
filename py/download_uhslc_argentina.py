#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Argentine tide stations.
Uses Fast Delivery where it has more data, falls back to Research Quality.

Data in millimeters, relative to station datum.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Argentina_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

STATIONS = [
    # --- Rio de la Plata ---
    {'uhslc_id': 285, 'name': 'Buenos Aires',    'lat': -34.567, 'lon': -58.500, 'province': 'Buenos Aires',       'dataset': 'global_hourly_rqds'},

    # --- Atlantic Coast ---
    {'uhslc_id': 729, 'name': 'Mar del Plata',   'lat': -38.035, 'lon': -57.538, 'province': 'Buenos Aires',       'dataset': 'global_hourly_fast'},
    {'uhslc_id': 731, 'name': 'Puerto Madryn',   'lat': -42.763, 'lon': -65.030, 'province': 'Chubut',             'dataset': 'global_hourly_fast'},
    {'uhslc_id': 286, 'name': 'Puerto Deseado',  'lat': -47.750, 'lon': -65.917, 'province': 'Santa Cruz',         'dataset': 'global_hourly_fast'},

    # --- Tierra del Fuego ---
    {'uhslc_id': 600, 'name': 'Ushuaia',         'lat': -54.805, 'lon': -68.295, 'province': 'Tierra del Fuego',   'dataset': 'global_hourly_fast'},

    # --- Antarctic ---
    {'uhslc_id': 601, 'name': 'Esperanza',       'lat': -63.395, 'lon': -56.995, 'province': 'Antartida Argentina', 'dataset': 'global_hourly_fast'},
    {'uhslc_id': 682, 'name': 'Dallmann',        'lat': -62.233, 'lon': -58.683, 'province': 'Antartida Argentina', 'dataset': 'global_hourly_rqds'},
]
# Skipping 681 (San Martin) - only 1.1 years of data, insufficient for harmonic analysis


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
    print("Download Hourly Sea Level Data - UHSLC ERDDAP (Argentina)")
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
