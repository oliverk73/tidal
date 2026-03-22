#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Australian tide stations.
Focuses on stations NOT already covered by BOM ABSLMP or QLD MSQ datasets.

Data in millimeters, relative to station datum. Converted to meters on save.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Australia_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

# Australian stations from UHSLC not already in BOM/QLD datasets
STATIONS = [
    # NSW
    {'uhslc_id': 333, 'name': 'Fort Denison', 'dataset': 'global_hourly_fast',
     'lat': -33.850, 'lon': 151.233, 'state': 'NSW'},
    {'uhslc_id': 399, 'name': 'Lord Howe Island', 'dataset': 'global_hourly_fast',
     'lat': -31.533, 'lon': 159.067, 'state': 'NSW'},
    # WA
    {'uhslc_id': 175, 'name': 'Fremantle', 'dataset': 'global_hourly_fast',
     'lat': -32.050, 'lon': 115.733, 'state': 'WA'},
    {'uhslc_id': 167, 'name': 'Carnarvon', 'dataset': 'global_hourly_fast',
     'lat': -24.883, 'lon': 113.617, 'state': 'WA'},
    {'uhslc_id': 169, 'name': 'Port Hedland', 'dataset': 'global_hourly_fast',
     'lat': -20.317, 'lon': 118.567, 'state': 'WA'},
    # QLD (not in MSQ dataset)
    {'uhslc_id': 331, 'name': 'Brisbane', 'dataset': 'global_hourly_fast',
     'lat': -27.367, 'lon': 153.167, 'state': 'QLD'},
    # Torres Strait
    {'uhslc_id': 336, 'name': 'Booby Island', 'dataset': 'global_hourly_fast',
     'lat': -10.600, 'lon': 141.917, 'state': 'QLD'},
    # TAS
    {'uhslc_id': 339, 'name': 'Hobart', 'dataset': 'global_hourly_rqds',
     'lat': -42.877, 'lon': 147.342, 'state': 'TAS'},
    # WA
    {'uhslc_id': 165, 'name': 'Wyndham', 'dataset': 'global_hourly_rqds',
     'lat': -15.453, 'lon': 128.101, 'state': 'WA'},
    # Territories
    {'uhslc_id': 170, 'name': 'Christmas Island', 'dataset': 'global_hourly_fast',
     'lat': -10.417, 'lon': 105.667, 'state': 'WA'},
    {'uhslc_id': 62, 'name': 'Norfolk Island', 'dataset': 'global_hourly_rqds',
     'lat': -29.067, 'lon': 167.950, 'state': 'NSW'},
    # Also download overlapping stations for validation / longer time series
    {'uhslc_id': 334, 'name': 'Townsville', 'dataset': 'global_hourly_fast',
     'lat': -19.250, 'lon': 146.833, 'state': 'QLD'},
    {'uhslc_id': 332, 'name': 'Bundaberg', 'dataset': 'global_hourly_fast',
     'lat': -24.833, 'lon': 152.350, 'state': 'QLD'},
    {'uhslc_id': 335, 'name': 'Spring Bay', 'dataset': 'global_hourly_fast',
     'lat': -42.550, 'lon': 147.933, 'state': 'TAS'},
    {'uhslc_id': 128, 'name': 'Thevenard', 'dataset': 'global_hourly_fast',
     'lat': -32.150, 'lon': 133.640, 'state': 'SA'},
    {'uhslc_id': 129, 'name': 'Portland', 'dataset': 'global_hourly_fast',
     'lat': -38.343, 'lon': 141.613, 'state': 'VIC'},
    {'uhslc_id': 166, 'name': 'Broome', 'dataset': 'global_hourly_fast',
     'lat': -18.000, 'lon': 122.217, 'state': 'WA'},
    {'uhslc_id': 168, 'name': 'Darwin', 'dataset': 'global_hourly_fast',
     'lat': -12.467, 'lon': 130.850, 'state': 'NT'},
    {'uhslc_id': 176, 'name': 'Esperance', 'dataset': 'global_hourly_fast',
     'lat': -33.867, 'lon': 121.900, 'state': 'WA'},
]


def download_station(station):
    """Download all hourly data for one station from UHSLC ERDDAP."""
    sid = station['uhslc_id']
    name = station['name']
    dataset = station['dataset']
    safe_name = name.replace(' ', '_').replace("'", '').replace('.', '')

    csv_path = os.path.join(OUTPUT_DIR, f'{sid}_{safe_name}.csv')

    # Skip if already downloaded
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 10000:
        n_lines = sum(1 for _ in open(csv_path))
        print(f"  schon vorhanden ({n_lines} Zeilen), ueberspringe.")
        return True

    url = f'{ERDDAP_BASE}/{dataset}.csv?time,sea_level,station_name&uhslc_id={sid}'
    print(f"  {dataset}...", end='', flush=True)

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=180)
            if resp.status_code == 404:
                # Try research quality dataset as fallback
                if dataset == 'global_hourly_fast':
                    alt_url = f'{ERDDAP_BASE}/global_hourly_rqds.csv?time,sea_level,station_name&uhslc_id={sid}'
                    print(f" [fallback rqds]", end='', flush=True)
                    resp = requests.get(alt_url, timeout=180)
                    if resp.status_code == 404:
                        print(f" KEINE DATEN (404)")
                        return False
                    resp.raise_for_status()
                    break
                print(f" KEINE DATEN (404)")
                return False
            resp.raise_for_status()
            break
        except Exception as e:
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f" [Retry in {wait}s]", end='', flush=True)
                time.sleep(wait)
            else:
                print(f" FEHLER: {e}")
                return False

    lines = resp.text.strip().split('\n')
    if len(lines) < 3:
        print(" KEINE DATEN")
        return False

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
        print(" KEINE GUELTIGEN DATEN")
        return False

    df = pd.DataFrame(rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')
    df.to_csv(csv_path, index=False)

    n = len(df)
    first = df['time'].iloc[0][:10]
    last = df['time'].iloc[-1][:10]
    years = n / (24 * 365.25)
    print(f" {n} Werte ({years:.1f} Jahre, {first} -- {last})")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download Hourly Sea Level Data -- UHSLC ERDDAP (Australia)")
    print("=" * 70)
    print(f"Ausgabe: {OUTPUT_DIR}")
    print(f"Stationen: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['state']})")
        if download_station(station):
            success += 1
        time.sleep(3)  # Be nice to the server
        print()

    print(f"{'='*70}")
    print(f"Ergebnis: {success}/{len(STATIONS)} erfolgreich")

    total_mb = 0
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.csv'):
            path = os.path.join(OUTPUT_DIR, f)
            size_mb = os.path.getsize(path) / (1024*1024)
            total_mb += size_mb
            n_lines = sum(1 for _ in open(path)) - 1
            print(f"  {f}: {size_mb:.1f} MB, {n_lines} Werte")
    print(f"  Gesamt: {total_mb:.1f} MB")


if __name__ == '__main__':
    main()
