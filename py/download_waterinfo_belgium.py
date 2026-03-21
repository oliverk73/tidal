#!/usr/bin/env python3
"""
Download observed water level data (Pv.10 = processed 10-min) from waterinfo.be
for all Belgian tide stations. Uses the KIWIS API at tsmpub endpoint.

Reference level: TAW (Tweede Algemene Waterpassing).
Checkpoint/resume: saves each station as CSV, skips existing files.
"""

import os
import json
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Belgium_waterinfo'
KIWIS_BASE = 'https://www.waterinfo.be/tsmpub/KiWIS/KiWIS'


def discover_stations():
    """Find all tide stations with Pv.10 (processed 10-min observed) timeseries."""
    stations = []

    for pattern in ['*tij/Noordzee*', '*tij/Westerschelde*', '*tij/Zeeschelde*',
                    '*tij/Rupel*', '*tij/Nete*', '*tij/Durme*', '*tij/Zenne*',
                    '*tij/Dijle*', '*tij/Kleine Nete*', '*tij/Grote Nete*',
                    '*tij/Haven*']:
        params = {
            'service': 'kisters',
            'type': 'queryServices',
            'request': 'getTimeseriesList',
            'datasource': 0,
            'format': 'json',
            'returnfields': 'station_name,station_no,ts_id,ts_name,parametertype_name,station_latitude,station_longitude',
            'station_name': pattern,
            'ts_name': 'Pv.10',
            'parametertype_name': 'W',
        }
        resp = requests.get(KIWIS_BASE, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            for row in data[1:]:
                stations.append({
                    'name': row[0],
                    'code': row[1],
                    'ts_id': row[2],
                    'ts_name': row[3],
                    'lat': row[5],
                    'lon': row[6],
                })

    # Deduplicate by station code (some have multiple Pv.10 series)
    seen = set()
    unique = []
    for s in stations:
        if s['code'] not in seen:
            seen.add(s['code'])
            unique.append(s)

    return unique


def download_station(station, output_dir):
    """Download Pv.10 data year by year for one station."""
    code = station['code']
    name = station['name']
    ts_id = station['ts_id']
    safe_code = code.replace('/', '_').replace(' ', '_')

    csv_path = os.path.join(output_dir, f'{safe_code}.csv')

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 5000:
        print(f"  ✓ Bereits vorhanden, überspringe.")
        return True

    print(f"  ↓ ts_id={ts_id}...", end='', flush=True)

    all_rows = []
    for year in range(2007, 2027):
        start = f'{year}-01-01'
        end = f'{year}-12-31' if year < 2026 else '2026-03-21'

        for attempt in range(3):
            try:
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
                    wait = 30 * (attempt + 1)
                    print(f" [429, {wait}s]", end='', flush=True)
                    time.sleep(wait)
                    continue
                elif resp.status_code == 503:
                    wait = 10 * (attempt + 1)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                if data and len(data) > 0:
                    ts_data = data[0].get('data', [])
                    for row in ts_data:
                        if row[1] is not None:
                            all_rows.append((row[0], row[1]))
                break

            except Exception as e:
                if attempt < 2:
                    time.sleep(5)
                else:
                    print(f" [{year}: {e}]", end='')
                    break

        time.sleep(1.5)  # Rate limit

    if not all_rows:
        print(f" KEINE DATEN")
        return False

    df = pd.DataFrame(all_rows, columns=['time', 'waterlevel_m_TAW'])
    # Parse timestamps (they come as local time CET/CEST with timezone)
    df['time'] = pd.to_datetime(df['time'], utc=True).dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
    df = df.drop_duplicates(subset='time').sort_values('time')
    df.to_csv(csv_path, index=False)

    n = len(df)
    years = n / (6 * 24 * 365.25)
    print(f" {n} Werte ({years:.1f} Jahre)")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download Observed Water Levels — waterinfo.be (Belgien)")
    print("=" * 70)

    stations = discover_stations()
    print(f"Stationen gefunden: {len(stations)}")
    for s in stations:
        print(f"  {s['code']:>25s} | {s['name']}")
    print()

    # Save catalog
    catalog_path = os.path.join(OUTPUT_DIR, '_station_catalog.json')
    with open(catalog_path, 'w') as f:
        json.dump(stations, f, indent=2)

    success = 0
    failed = 0

    for i, station in enumerate(stations):
        print(f"\n[{i+1}/{len(stations)}] {station['code']} | {station['name']}")
        if download_station(station, OUTPUT_DIR):
            success += 1
        else:
            failed += 1

    print(f"\n{'='*70}")
    print(f"Ergebnis: {success} erfolgreich, {failed} fehlgeschlagen")

    total_mb = 0
    n_files = 0
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.csv'):
            total_mb += os.path.getsize(os.path.join(OUTPUT_DIR, f)) / (1024*1024)
            n_files += 1
    print(f"Dateien: {n_files}, Gesamt: {total_mb:.0f} MB")


if __name__ == '__main__':
    main()
