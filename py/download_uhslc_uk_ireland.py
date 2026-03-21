#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for UK and Ireland stations.
Uses Fast Delivery dataset (hybrid RQ+FD) where available, falls back to RQDS.

Data in millimeters, relative to station datum.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/UK_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

STATIONS = [
    # UK
    {'uhslc_id': 293, 'name': 'Lerwick', 'dataset': 'global_hourly_fast',
     'lat': 60.154, 'lon': -1.140, 'country': 'UK'},
    {'uhslc_id': 294, 'name': 'Newlyn', 'dataset': 'global_hourly_fast',
     'lat': 50.103, 'lon': -5.543, 'country': 'UK'},
    {'uhslc_id': 295, 'name': 'Stornoway', 'dataset': 'global_hourly_fast',
     'lat': 58.207, 'lon': -5.177, 'country': 'UK'},
    # Ireland
    {'uhslc_id': 835, 'name': 'Castletownbere', 'dataset': 'global_hourly_fast',
     'lat': 51.650, 'lon': -9.900, 'country': 'Ireland'},
    {'uhslc_id': 834, 'name': 'Malin Head', 'dataset': 'global_hourly_fast',
     'lat': 55.367, 'lon': -7.333, 'country': 'Ireland'},
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
        print(f"  ✓ Bereits vorhanden ({n_lines} Zeilen), überspringe.")
        return True

    # Try fast dataset first, fall back to rqds
    datasets_to_try = [dataset]
    if dataset == 'global_hourly_fast':
        datasets_to_try.append('global_hourly_rqds')
    elif dataset == 'global_hourly_rqds':
        datasets_to_try.append('global_hourly_fast')

    for ds in datasets_to_try:
        url = f'{ERDDAP_BASE}/{ds}.csv?time,sea_level,station_name&uhslc_id={sid}'
        print(f"  ↓ {ds}...", end='', flush=True)

        for attempt in range(3):
            try:
                resp = requests.get(url, timeout=120)
                if resp.status_code == 404:
                    print(f" 404", end='')
                    break
                resp.raise_for_status()

                lines = resp.text.strip().split('\n')
                if len(lines) < 3:
                    print(f" leer", end='')
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

                if rows:
                    df = pd.DataFrame(rows, columns=['time', 'waterlevel_m'])
                    df = df.drop_duplicates(subset='time').sort_values('time')
                    df.to_csv(csv_path, index=False)

                    n = len(df)
                    first = df['time'].iloc[0][:10]
                    last = df['time'].iloc[-1][:10]
                    years = n / (24 * 365.25)
                    print(f" {n} Werte ({years:.1f} Jahre, {first} — {last})")
                    return True
                else:
                    print(f" keine gültigen Daten", end='')
                    break

            except Exception as e:
                if attempt < 2:
                    wait = 30 * (attempt + 1)
                    print(f" [Retry in {wait}s]", end='', flush=True)
                    time.sleep(wait)
                else:
                    print(f" FEHLER: {e}", end='')
                    break

        print()  # newline after trying this dataset

    print(f"  ✗ Keine Daten gefunden")
    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download Hourly Sea Level Data — UHSLC ERDDAP (UK + Ireland)")
    print("=" * 70)
    print(f"Ausgabe: {OUTPUT_DIR}")
    print(f"Stationen: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['country']})")
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
