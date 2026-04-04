#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Brazilian tide stations.
Uses Fast Delivery dataset where available, falls back to Research Quality.

Data in millimeters, relative to station datum.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Brazil_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

STATIONS = [
    # --- North (Amapa, Para, Maranhao) ---
    {'uhslc_id': 716, 'name': 'Santana',              'lat':  -0.067, 'lon': -51.167, 'state': 'Amapa',               'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 229, 'name': 'Belem',                'lat':  -1.450, 'lon': -48.500, 'state': 'Para',                'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 715, 'name': 'Madeira',              'lat':  -2.565, 'lon': -44.378, 'state': 'Maranhao',            'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},

    # --- Northeast (Piaui, Ceara, Rio Grande do Norte, Pernambuco, Bahia) ---
    {'uhslc_id': 711, 'name': 'Luis Correia',         'lat':  -2.867, 'lon': -41.672, 'state': 'Piaui',              'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 283, 'name': 'Fortaleza',            'lat':  -3.717, 'lon': -38.467, 'state': 'Ceara',              'water': 'Atlantic Ocean', 'dataset': 'global_hourly_fast'},
    {'uhslc_id': 284, 'name': 'Termisa',              'lat':  -4.817, 'lon': -37.050, 'state': 'Ceara',              'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 202, 'name': 'Natal',                'lat':  -5.752, 'lon': -35.195, 'state': 'Rio Grande do Norte', 'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 712, 'name': 'Recife',               'lat':  -8.050, 'lon': -34.867, 'state': 'Pernambuco',         'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 710, 'name': 'Suape',                'lat':  -8.350, 'lon': -34.950, 'state': 'Pernambuco',         'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 708, 'name': 'Salvador',             'lat': -12.973, 'lon': -38.517, 'state': 'Bahia',              'water': 'Atlantic Ocean', 'dataset': 'global_hourly_fast'},
    {'uhslc_id': 707, 'name': 'Canavieiras',          'lat': -15.667, 'lon': -38.967, 'state': 'Bahia',              'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},

    # --- Islands ---
    {'uhslc_id': 201, 'name': 'Peter and Paul Rocks', 'lat':   0.920, 'lon': -29.343, 'state': 'Pernambuco',         'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 203, 'name': 'Fernando de Noronha',  'lat':  -3.828, 'lon': -32.403, 'state': 'Pernambuco',         'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 204, 'name': 'Trindade',             'lat': -20.503, 'lon': -29.310, 'state': 'Espirito Santo',     'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},

    # --- Southeast (Rio de Janeiro, Sao Paulo) ---
    {'uhslc_id': 719, 'name': 'Macae',                'lat': -22.385, 'lon': -41.770, 'state': 'Rio de Janeiro',     'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 280, 'name': 'Ilha Fiscal',          'lat': -22.897, 'lon': -43.165, 'state': 'Rio de Janeiro',     'water': 'Atlantic Ocean', 'dataset': 'global_hourly_fast'},
    {'uhslc_id': 282, 'name': 'Ubatuba',              'lat': -23.500, 'lon': -45.117, 'state': 'Sao Paulo',          'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 281, 'name': 'Cananeia',             'lat': -25.017, 'lon': -47.925, 'state': 'Sao Paulo',          'water': 'Atlantic Ocean', 'dataset': 'global_hourly_fast'},

    # --- South (Santa Catarina, Rio Grande do Sul) ---
    {'uhslc_id': 718, 'name': 'Imbituba',             'lat': -28.230, 'lon': -48.650, 'state': 'Santa Catarina',     'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 714, 'name': 'Rio Grande',           'lat': -32.138, 'lon': -52.103, 'state': 'Rio Grande do Sul',  'water': 'Atlantic Ocean', 'dataset': 'global_hourly_rqds'},
]
# Note: Skipping 717 (Santana SSN) as it's the same location as 716 (Santana)
# Note: Skipping 709 (Rio de Janeiro) as it's very close to 280 (Ilha Fiscal) in the same bay


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
    print("Download Hourly Sea Level Data - UHSLC ERDDAP (Brazil)")
    print("=" * 70)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Stations: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['state']})")
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
