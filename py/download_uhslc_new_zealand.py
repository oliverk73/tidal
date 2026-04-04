#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for New Zealand tide stations.
Uses Fast Delivery dataset where available, falls back to Research Quality.

Data in millimeters, relative to station datum.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/New_Zealand_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

STATIONS = [
    # --- North Island ---
    {'uhslc_id': 398, 'name': 'Marsden Point',  'lat': -35.833, 'lon': 174.500, 'region': 'Northland',       'water': 'Pacific Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  70, 'name': 'Auckland',        'lat': -36.850, 'lon': 174.767, 'region': 'Auckland',        'water': 'Hauraki Gulf',    'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  73, 'name': 'Tauranga',        'lat': -37.650, 'lon': 176.183, 'region': 'Bay of Plenty',   'water': 'Pacific Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  78, 'name': 'Gisborne',        'lat': -38.683, 'lon': 178.033, 'region': 'Gisborne',        'water': 'Pacific Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 668, 'name': 'Napier',          'lat': -39.483, 'lon': 176.917, 'region': "Hawke's Bay",     'water': 'Pacific Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  76, 'name': 'Taranaki',        'lat': -39.050, 'lon': 174.033, 'region': 'Taranaki',        'water': 'Tasman Sea',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  75, 'name': 'Wanganui',        'lat': -39.947, 'lon': 174.990, 'region': 'Manawatu-Whanganui', 'water': 'Tasman Sea',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  71, 'name': 'Wellington',       'lat': -41.283, 'lon': 174.783, 'region': 'Wellington',      'water': 'Cook Strait',     'dataset': 'global_hourly_fast'},

    # --- South Island ---
    {'uhslc_id':  77, 'name': 'Nelson',           'lat': -41.267, 'lon': 173.267, 'region': 'Nelson',          'water': 'Tasman Bay',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  74, 'name': 'Westport',         'lat': -41.733, 'lon': 171.600, 'region': 'West Coast',      'water': 'Tasman Sea',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 403, 'name': 'Jackson Bay',      'lat': -43.983, 'lon': 168.617, 'region': 'West Coast',      'water': 'Tasman Sea',      'dataset': 'global_hourly_fast'},
    {'uhslc_id': 667, 'name': 'Lyttelton',        'lat': -43.600, 'lon': 172.717, 'region': 'Canterbury',      'water': 'Pacific Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 665, 'name': 'Timaru',           'lat': -44.383, 'lon': 171.250, 'region': 'Canterbury',      'water': 'Pacific Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 669, 'name': 'Port Chalmers',    'lat': -45.817, 'lon': 170.650, 'region': 'Otago',           'water': 'Pacific Ocean',   'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  72, 'name': 'Bluff',            'lat': -46.600, 'lon': 168.350, 'region': 'Southland',       'water': 'Foveaux Strait',  'dataset': 'global_hourly_fast'},

    # --- Chatham Islands ---
    {'uhslc_id':  79, 'name': 'Chatham Island',   'lat': -43.947, 'lon': -176.562, 'region': 'Chatham Islands', 'water': 'Pacific Ocean',  'dataset': 'global_hourly_fast'},

    # --- Antarctica (NZ-administered) ---
    {'uhslc_id': 663, 'name': 'Scott Base',       'lat': -77.850, 'lon': 166.767, 'region': 'Ross Island',     'water': 'Ross Sea',        'dataset': 'global_hourly_rqds'},
]


def download_station(station):
    """Download all hourly data for one station from UHSLC ERDDAP."""
    sid = station['uhslc_id']
    name = station['name']
    dataset = station['dataset']
    safe_name = name.replace(' ', '_').replace("'", '').replace('.', '')

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
    print("Download Hourly Sea Level Data - UHSLC ERDDAP (New Zealand)")
    print("=" * 70)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Stations: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['region']})")
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
