#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Mexican tide stations.
Uses Research Quality dataset (rqds) which has the longest records,
falls back to Fast Delivery (FD) for stations only available there.

Data in millimeters, relative to station datum.
Goal: obtain a full nodal cycle (~18.6 years) of data per station.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Mexico_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

# All Mexican stations from UHSLC ERDDAP
# Stations available in both datasets use 'global_hourly_fast' (longer + more recent)
# Stations only in rqds use 'global_hourly_rqds'
STATIONS = [
    # --- Pacific Coast (North to South) ---
    {'uhslc_id': 317, 'name': 'Ensenada',           'lat': 31.850, 'lon': -116.633, 'state': 'Baja California',     'water': 'Pacific Ocean',       'dataset': 'global_hourly_fast'},
    {'uhslc_id': 308, 'name': 'San Quintin',         'lat': 30.483, 'lon': -115.983, 'state': 'Baja California',     'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  36, 'name': 'Isla Guadalupe',      'lat': 28.883, 'lon': -118.300, 'state': 'Baja California',     'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 305, 'name': 'Isla de Cedros',      'lat': 28.100, 'lon': -115.183, 'state': 'Baja California',     'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},
    {'uhslc_id':  34, 'name': 'Cabo San Lucas',      'lat': 22.880, 'lon': -109.908, 'state': 'Baja California Sur', 'water': 'Pacific Ocean',       'dataset': 'global_hourly_fast'},
    {'uhslc_id':  90, 'name': 'Isla Socorro',         'lat': 18.733, 'lon': -111.017, 'state': 'Colima',             'water': 'Pacific Ocean',       'dataset': 'global_hourly_fast'},

    # --- Gulf of California ---
    {'uhslc_id': 307, 'name': 'San Felipe',          'lat': 31.018, 'lon': -114.818, 'state': 'Baja California',     'water': 'Gulf of California',  'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 310, 'name': 'Bahia de los Angeles','lat': 28.958, 'lon': -113.550, 'state': 'Baja California',     'water': 'Gulf of California',  'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 319, 'name': 'Loreto',              'lat': 26.017, 'lon': -111.367, 'state': 'Baja California Sur', 'water': 'Gulf of California',  'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 674, 'name': 'San Carlos',          'lat': 24.790, 'lon': -112.120, 'state': 'Baja California Sur', 'water': 'Gulf of California',  'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 671, 'name': 'La Paz',              'lat': 24.162, 'lon': -110.345, 'state': 'Baja California Sur', 'water': 'Gulf of California',  'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 676, 'name': 'Topolobampo',         'lat': 25.600, 'lon': -109.048, 'state': 'Sinaloa',            'water': 'Gulf of California',  'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 677, 'name': 'Yavaros',             'lat': 26.703, 'lon': -109.513, 'state': 'Sonora',             'water': 'Gulf of California',  'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 397, 'name': 'Guaymas',             'lat': 27.933, 'lon': -110.900, 'state': 'Sonora',             'water': 'Gulf of California',  'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 673, 'name': 'Mazatlan',            'lat': 23.198, 'lon': -106.422, 'state': 'Sinaloa',            'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},

    # --- Pacific Coast (Central/South) ---
    {'uhslc_id': 393, 'name': 'Puerto Vallarta',     'lat': 20.615, 'lon': -105.245, 'state': 'Jalisco',            'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 395, 'name': 'Manzanillo',          'lat': 19.050, 'lon': -104.333, 'state': 'Colima',             'water': 'Pacific Ocean',       'dataset': 'global_hourly_fast'},
    {'uhslc_id': 687, 'name': 'Zihuatanejo',         'lat': 17.637, 'lon': -101.558, 'state': 'Guerrero',           'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 316, 'name': 'Acapulco',            'lat': 16.840, 'lon':  -99.912, 'state': 'Guerrero',           'water': 'Pacific Ocean',       'dataset': 'global_hourly_fast'},
    {'uhslc_id': 672, 'name': 'Puerto Angel',        'lat': 15.657, 'lon':  -96.493, 'state': 'Oaxaca',             'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 394, 'name': 'Salina Cruz',         'lat': 16.160, 'lon':  -95.203, 'state': 'Oaxaca',             'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 318, 'name': 'Puerto Madero',       'lat': 14.717, 'lon':  -92.433, 'state': 'Chiapas',            'water': 'Pacific Ocean',       'dataset': 'global_hourly_rqds'},

    # --- Gulf of Mexico & Caribbean ---
    {'uhslc_id': 277, 'name': 'Madero (Tampico)',    'lat': 22.262, 'lon':  -97.795, 'state': 'Tamaulipas',         'water': 'Gulf of Mexico',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 250, 'name': 'Veracruz',            'lat': 19.200, 'lon':  -96.133, 'state': 'Veracruz',           'water': 'Gulf of Mexico',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 779, 'name': 'Ciudad del Carmen',   'lat': 18.533, 'lon':  -91.833, 'state': 'Campeche',           'water': 'Gulf of Mexico',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 861, 'name': 'Celestun',            'lat': 20.858, 'lon':  -90.403, 'state': 'Yucatan',            'water': 'Gulf of Mexico',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 721, 'name': 'Progreso',            'lat': 21.283, 'lon':  -89.667, 'state': 'Yucatan',            'water': 'Gulf of Mexico',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 862, 'name': 'Telchac',             'lat': 21.340, 'lon':  -89.308, 'state': 'Yucatan',            'water': 'Gulf of Mexico',      'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 860, 'name': 'Puerto Morelos',      'lat': 20.868, 'lon':  -86.867, 'state': 'Quintana Roo',       'water': 'Caribbean Sea',       'dataset': 'global_hourly_rqds'},
]


def download_station(station):
    """Download all hourly data for one station from UHSLC ERDDAP."""
    sid = station['uhslc_id']
    name = station['name']
    dataset = station['dataset']
    safe_name = name.replace(' ', '_').replace("'", '').replace('.', '').replace('(', '').replace(')', '')

    csv_path = os.path.join(OUTPUT_DIR, f'{sid}_{safe_name}.csv')

    # Skip if already downloaded
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 10000:
        n_lines = sum(1 for _ in open(csv_path))
        print(f"  Already downloaded ({n_lines} lines), skipping.")
        return True

    # Try preferred dataset first, then fallback
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

                # Parse: skip header (2 lines), columns: time, sea_level(mm), station_name
                rows = []
                for line in lines[2:]:
                    parts = line.split(',')
                    if len(parts) >= 2:
                        ts = parts[0]
                        val = parts[1]
                        if val and val != 'NaN':
                            try:
                                rows.append((ts, float(val) / 1000.0))  # mm -> meters
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
                    print(f" TIMEOUT after 3 attempts", end='')
                    break
            except Exception as e:
                if attempt < 2:
                    wait = 30 * (attempt + 1)
                    print(f" [error, retry in {wait}s]", end='', flush=True)
                    time.sleep(wait)
                else:
                    print(f" ERROR: {e}", end='')
                    break

        print()  # newline after failed dataset

    print(f"  FAILED: no data from any dataset")
    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download Hourly Sea Level Data - UHSLC ERDDAP (Mexico)")
    print("=" * 70)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Stations: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['state']})")
        if download_station(station):
            success += 1
        time.sleep(3)  # Be nice to the server

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
