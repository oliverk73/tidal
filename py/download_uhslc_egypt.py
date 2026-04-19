#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Egypt (Alexandria, RQDS).
Only one usable station; Red Sea coast has no open water-level station.
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Egypt_UHSLC'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

STATIONS = [
    {'uhslc_id': 807, 'name': 'Alexandria', 'lat': 31.212, 'lon': 29.923, 'country': 'Egypt', 'tz': 'Africa/Cairo', 'gloss_id': None, 'dataset': 'global_hourly_rqds'},
]


def download_station(station):
    sid = station['uhslc_id']
    name = station['name']
    dataset = station['dataset']
    safe_name = name.replace(' ', '_').replace("'", '').replace('.', '').replace(',', '')
    csv_path = os.path.join(OUTPUT_DIR, f'{sid}_{safe_name}.csv')

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 10000:
        n_lines = sum(1 for _ in open(csv_path))
        print(f"  Already downloaded ({n_lines} lines), skipping.")
        return True

    url = f'{ERDDAP_BASE}/{dataset}.csv?time,sea_level,station_name&uhslc_id={sid}'
    print(f"  Downloading from {dataset}...", end='', flush=True)

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=180)
            if resp.status_code == 404:
                print(f" not found (404)")
                return False
            resp.raise_for_status()

            lines = resp.text.strip().split('\n')
            if len(lines) < 3:
                print(f" no data")
                return False

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
                print(f" no valid data")
                return False

            df = pd.DataFrame(rows, columns=['time', 'waterlevel_m'])
            df = df.drop_duplicates(subset='time').sort_values('time')
            df.to_csv(csv_path, index=False)

            n = len(df)
            first = df['time'].iloc[0][:10]
            last = df['time'].iloc[-1][:10]
            years = n / (24 * 365.25)
            print(f" {n} values ({years:.1f} years, {first} - {last})")
            return True

        except Exception as e:
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f" [error, retry in {wait}s]", end='', flush=True)
                time.sleep(wait)
            else:
                print(f" ERROR: {e}")
                return False

    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("UHSLC ERDDAP - Egypt (Alexandria)")
    for station in STATIONS:
        print(f"[{station['name']}] UHSLC {station['uhslc_id']}")
        download_station(station)


if __name__ == '__main__':
    main()
