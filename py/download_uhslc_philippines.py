#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Philippine tide stations.

Data in millimeters, relative to station datum. Converted to meters on save.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Philippines_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

# Philippine stations from UHSLC
# Sources: https://uhslc.soest.hawaii.edu/stations/
STATIONS = [
    {'uhslc_id': 370, 'name': 'Manila', 'dataset': 'global_hourly_fast',
     'lat': 14.585, 'lon': 120.968},
    {'uhslc_id': 371, 'name': 'Legaspi', 'dataset': 'global_hourly_fast',
     'lat': 13.145, 'lon': 123.758},
    {'uhslc_id': 372, 'name': 'Davao', 'dataset': 'global_hourly_fast',
     'lat': 7.083, 'lon': 125.633},
    {'uhslc_id': 373, 'name': 'Jolo', 'dataset': 'global_hourly_fast',
     'lat': 6.067, 'lon': 121.0},
    {'uhslc_id': 379, 'name': 'Cebu', 'dataset': 'global_hourly_fast',
     'lat': 10.300, 'lon': 123.917},
    {'uhslc_id': 380, 'name': 'Puerto Princesa', 'dataset': 'global_hourly_fast',
     'lat': 9.745, 'lon': 118.736},
    {'uhslc_id': 382, 'name': 'Subic Bay', 'dataset': 'global_hourly_fast',
     'lat': 14.765, 'lon': 120.252},
    {'uhslc_id': 654, 'name': 'Currimao', 'dataset': 'global_hourly_fast',
     'lat': 17.988, 'lon': 120.488},
    {'uhslc_id': 655, 'name': 'Lubang', 'dataset': 'global_hourly_fast',
     'lat': 13.818, 'lon': 120.202},
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
    print("Download Hourly Sea Level Data -- UHSLC ERDDAP (Philippines)")
    print("=" * 70)
    print(f"Ausgabe: {OUTPUT_DIR}")
    print(f"Stationen: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']})")
        if download_station(station):
            success += 1
        time.sleep(3)
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
