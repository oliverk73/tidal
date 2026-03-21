#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Canadian tide stations.
Uses the Fast Delivery dataset (hybrid RQ+FD), falls back to RQDS for Victoria.

Data in millimeters, relative to station datum.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Canada_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

# Stations with dataset preference (FD has most recent data, RQ for Victoria)
STATIONS = [
    {'uhslc_id': 275, 'name': 'Halifax', 'dataset': 'global_hourly_fast',
     'lat': 44.667, 'lon': -63.583, 'province': 'Nova Scotia'},
    {'uhslc_id': 540, 'name': 'Prince Rupert', 'dataset': 'global_hourly_fast',
     'lat': 54.317, 'lon': -130.323, 'province': 'British Columbia'},
    {'uhslc_id': 542, 'name': 'Tofino', 'dataset': 'global_hourly_fast',
     'lat': 49.153, 'lon': -125.913, 'province': 'British Columbia'},
    {'uhslc_id': 543, 'name': 'Victoria', 'dataset': 'global_hourly_rqds',
     'lat': 48.425, 'lon': -123.370, 'province': 'British Columbia'},
    {'uhslc_id': 276, 'name': "St. John's", 'dataset': 'global_hourly_rqds',
     'lat': 47.567, 'lon': -52.700, 'province': 'Newfoundland'},
    {'uhslc_id': 274, 'name': 'Churchill', 'dataset': 'global_hourly_fast',
     'lat': 58.783, 'lon': -94.183, 'province': 'Manitoba'},
    {'uhslc_id': 833, 'name': 'Nain', 'dataset': 'global_hourly_fast',
     'lat': 56.550, 'lon': -61.683, 'province': 'Newfoundland'},
    {'uhslc_id': 273, 'name': 'Port-aux-Basques', 'dataset': 'global_hourly_fast',
     'lat': 47.567, 'lon': -59.133, 'province': 'Newfoundland'},
    {'uhslc_id': 541, 'name': 'Bamfield', 'dataset': 'global_hourly_fast',
     'lat': 48.833, 'lon': -125.133, 'province': 'British Columbia'},
    {'uhslc_id': 836, 'name': 'Alert', 'dataset': 'global_hourly_fast',
     'lat': 82.492, 'lon': -62.317, 'province': 'Nunavut'},
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
        print(f"  ✓ Bereits vorhanden ({n_lines} Zeilen), überspringe.")
        return True

    url = f'{ERDDAP_BASE}/{dataset}.csv?time,sea_level,station_name&uhslc_id={sid}'
    print(f"  ↓ {url.split('?')[0].split('/')[-1]}...", end='', flush=True)

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=120)
            if resp.status_code == 404:
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
        print(" KEINE GÜLTIGEN DATEN")
        return False

    df = pd.DataFrame(rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')
    df.to_csv(csv_path, index=False)

    n = len(df)
    first = df['time'].iloc[0][:10]
    last = df['time'].iloc[-1][:10]
    years = n / (24 * 365.25)
    print(f" {n} Werte ({years:.1f} Jahre, {first} — {last})")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download Hourly Sea Level Data — UHSLC ERDDAP (Canada)")
    print("=" * 70)
    print(f"Ausgabe: {OUTPUT_DIR}")
    print(f"Stationen: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['province']})")
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
