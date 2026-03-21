#!/usr/bin/env python3
"""
Download astronomical water level data from HIC (Flanders Hydraulics Research)
for all Belgian tide stations with astronomical predictions.

Uses the KIWIS API directly via requests (no pywaterinfo constructor needed,
which avoids the initial API call that triggers rate limiting).
Data is saved as CSV files per station in water_levels/Belgium/.

Reference level: TAW (Tweede Algemene Waterpassing), ~2.33m above NAP.
"""

import os
import sys
import json
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Belgium'
CATALOG_CACHE = os.path.join(OUTPUT_DIR, '_station_catalog.json')
START_YEAR = 2007
END_YEAR = 2026

KIWIS_BASE = 'https://hicws.vlaanderen.be/KiWIS/KiWIS'


def get_astronomical_stations():
    """Get all stations with astronomical tide predictions from cached catalog."""
    if os.path.exists(CATALOG_CACHE):
        print(f"Lade Stationskatalog aus Cache...")
        with open(CATALOG_CACHE, 'r') as f:
            stations = json.load(f)
        print(f"{len(stations)} Stationen aus Cache geladen.")
        return stations

    # Fallback: fetch catalog via KIWIS API directly
    print("Lade Stationskatalog von HIC KIWIS API...")
    params = {
        'service': 'kisters',
        'type': 'queryServices',
        'request': 'getTimeseriesList',
        'datasource': 0,
        'format': 'json',
        'timeseriesgroup_id': '354718',
        'returnfields': 'station_name,station_no,ts_id,station_latitude,station_longitude',
    }
    resp = requests.get(KIWIS_BASE, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # First row is header
    header = data[0]
    stations = []
    for row in data[1:]:
        stations.append(dict(zip(header, row)))

    with open(CATALOG_CACHE, 'w') as f:
        json.dump(stations, f, indent=2)

    print(f"{len(stations)} Zeitreihen gefunden.")
    return stations


def download_timeseries(ts_id, start, end):
    """Download timeseries data directly from KIWIS API."""
    params = {
        'service': 'kisters',
        'type': 'queryServices',
        'request': 'getTimeseriesValues',
        'datasource': 0,
        'format': 'json',
        'ts_id': str(ts_id),
        'from': start,
        'to': end,
        'metadata': 'false',
    }
    resp = requests.get(KIWIS_BASE, params=params, timeout=60)
    if resp.status_code == 429:
        raise Exception(f"429 Rate limit: {resp.text[:200]}")
    resp.raise_for_status()
    data = resp.json()

    if not data or len(data) == 0:
        return None

    # data[0] contains {'data': [[timestamp, value], ...], ...}
    ts_data = data[0].get('data', [])
    if not ts_data:
        return None

    rows = [(row[0], row[1]) for row in ts_data if row[1] is not None]
    if not rows:
        return None

    df = pd.DataFrame(rows, columns=['Timestamp', 'Value'])
    return df


def download_station(ts_id, station_name, station_code, output_dir):
    """Download data for a single station year by year and save as CSV."""
    safe_name = station_code.replace('/', '_').replace(' ', '_')
    csv_path = os.path.join(output_dir, f"{safe_name}.csv")

    # Skip if already downloaded
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 1024:
        print(f"  ✓ {station_name} — bereits vorhanden, überspringe.")
        return True

    print(f"  ↓ {station_name} (ts_id={ts_id})...", end='', flush=True)

    all_dfs = []
    for year in range(START_YEAR, END_YEAR + 1):
        start = f'{year}-01-01'
        end = f'{year}-12-31' if year < END_YEAR else '2026-03-20'

        for attempt in range(3):
            try:
                df = download_timeseries(ts_id, start, end)
                if df is not None and len(df) > 0:
                    all_dfs.append(df)
                break
            except Exception as e:
                if '429' in str(e):
                    wait = 60 * (attempt + 1)
                    print(f" [Rate limit, warte {wait}s]", end='', flush=True)
                    time.sleep(wait)
                else:
                    print(f" [{year}: {e}]", end='')
                    break

        # Pause between requests to avoid rate limiting
        time.sleep(2)

    if not all_dfs:
        print(f" KEINE DATEN")
        return False

    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.drop_duplicates(subset='Timestamp').sort_values('Timestamp')
    combined.columns = ['time', 'waterlevel_m_TAW']

    # Clean timestamps
    combined['time'] = pd.to_datetime(combined['time']).dt.strftime('%Y-%m-%d %H:%M:%S+00:00')

    combined.to_csv(csv_path, index=False)
    n_rows = len(combined)
    years = n_rows / (6 * 24 * 365.25)
    print(f" {n_rows} Werte ({years:.1f} Jahre)")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    stations = get_astronomical_stations()

    print(f"\nDownload-Zeitraum: {START_YEAR} bis {END_YEAR}")
    print(f"Ausgabeverzeichnis: {OUTPUT_DIR}")
    print(f"{'='*60}\n")

    success = 0
    failed = 0

    for i, st in enumerate(stations):
        station_name = st['station_name']
        station_code = st['station_no']
        ts_id = st['ts_id']

        print(f"[{i+1}/{len(stations)}] {station_name}")
        result = download_station(ts_id, station_name, station_code, OUTPUT_DIR)

        if result:
            success += 1
        else:
            failed += 1

        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"ERGEBNIS")
    print(f"{'='*60}")
    print(f"Erfolgreich: {success}")
    print(f"Fehlgeschlagen: {failed}")
    print(f"Gesamt: {len(stations)}")


if __name__ == '__main__':
    main()
