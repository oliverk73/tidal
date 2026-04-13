#!/usr/bin/env python3
"""
Download WLP (Water Level Predictions) from CHS IWLS API for Nova Scotia stations.
Uses 15-min resolution, downloads 1 full year (2025) for UTide analysis.

WLP data = official CHS tide predictions → reverse-engineering CHS harmonics via UTide.
"""
import os
import json
import time
import datetime
import requests
import pandas as pd

API_BASE = 'https://api-sine.dfo-mpo.gc.ca/api/v1'
OUTPUT_DIR = '/home/oliver/water_levels/Canada_IWLS_NS'
CATALOG_PATH = os.path.join(OUTPUT_DIR, '_ns_stations.json')
RESOLUTION = 'FIFTEEN_MINUTES'

# Download 1 full year of predictions
START_DATE = '2025-01-01'
END_DATE = '2025-12-31'


def download_wlp(station):
    """Download WLP data month by month for one station."""
    code = station['code']
    name = station['name']
    station_id = station['id']
    safe_name = code + '_' + name.replace(' ', '_').replace('/', '_').replace("'", '').replace('.', '').replace('#', '')

    csv_path = os.path.join(OUTPUT_DIR, f'{safe_name}_wlp.csv')

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 5000:
        lines = sum(1 for _ in open(csv_path)) - 1
        print(f"  ✓ Bereits vorhanden ({lines} Werte)")
        return True

    start = datetime.date.fromisoformat(START_DATE)
    end = datetime.date.fromisoformat(END_DATE)

    months = []
    current = start.replace(day=1)
    while current <= end:
        next_month = (current.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        month_end = min(next_month - datetime.timedelta(days=1), end)
        months.append((current, month_end))
        current = next_month

    all_rows = []
    empty_count = 0

    for m_start, m_end in months:
        from_dt = f'{m_start}T00:00:00Z'
        to_dt = f'{m_end}T23:59:59Z'

        try:
            resp = requests.get(
                f'{API_BASE}/stations/{station_id}/data',
                params={
                    'time-series-code': 'wlp',
                    'from': from_dt,
                    'to': to_dt,
                    'resolution': RESOLUTION,
                },
                timeout=15,
            )
            if resp.status_code == 429:
                time.sleep(10)
                continue
            if resp.status_code in (404, 400, 500):
                empty_count += 1
            elif resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    for d in data:
                        all_rows.append((d['eventDate'], d['value']))
                    empty_count = 0
                else:
                    empty_count += 1
            else:
                empty_count += 1
        except Exception:
            empty_count += 1

        import sys
        sys.stdout.write('.' if len(all_rows) > 0 else 'x')
        sys.stdout.flush()

        if empty_count >= 2 and len(all_rows) == 0:
            break

        time.sleep(1.5)

    if not all_rows:
        print(f" KEINE WLP-DATEN")
        return False

    df = pd.DataFrame(all_rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')
    df.to_csv(csv_path, index=False)

    print(f" {len(df)} Werte → {csv_path}")
    return True


def main():
    with open(CATALOG_PATH) as f:
        stations = json.load(f)

    print(f"Downloading WLP for {len(stations)} Nova Scotia stations")
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'='*70}")

    success = 0
    fail = 0
    for i, station in enumerate(stations):
        print(f"\n[{i+1}/{len(stations)}] {station['code']} {station['name']:<40s} ", end='', flush=True)
        if download_wlp(station):
            success += 1
        else:
            fail += 1

    print(f"\n\n{'='*70}")
    print(f"Fertig: {success} OK, {fail} ohne Daten")


if __name__ == '__main__':
    main()
