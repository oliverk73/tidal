#!/usr/bin/env python3
"""
Download water level observations (wlo) from CHS IWLS API for all Canadian
tide stations that have data. Uses 15-min resolution, month by month.

Checkpoint/resume: saves each station as CSV immediately, skips existing files.
Rate limit: 3 req/s, 30 req/min → 2.2s pause between requests.
"""

import os
import json
import time
import datetime
import requests
import pandas as pd

API_BASE = 'https://api-sine.dfo-mpo.gc.ca/api/v1'
OUTPUT_DIR = '/home/oliver/water_levels/Canada_IWLS'
CATALOG_PATH = '/home/oliver/water_levels/Canada/_stations_with_wlo.json'
RESOLUTION = 'FIFTEEN_MINUTES'

# UHSLC stations we already have (skip these)
UHSLC_CHS_CODES = {'00490', '07120', '00065', '02985', '05010', '01430',
                    '08545', '08615', '03765'}  # Halifax, Victoria, etc.


def download_station(station, output_dir):
    """Download wlo data month by month for one station."""
    code = station['code']
    name = station['name']
    station_id = station['id']
    safe_name = code + '_' + name.replace(' ', '_').replace('/', '_').replace("'", '').replace('.', '')

    csv_path = os.path.join(output_dir, f'{safe_name}.csv')

    # Skip if already downloaded
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 5000:
        print(f"  ✓ Bereits vorhanden, überspringe.")
        return True

    # Determine data range from holdings
    try:
        resp = requests.get(f'{API_BASE}/stations/{station_id}/holdings', timeout=15)
        resp.raise_for_status()
        holdings = resp.json()
    except Exception as e:
        print(f"  ✗ Holdings-Fehler: {e}")
        return False

    # Find wlo date range
    earliest = '9999-12-31'
    latest = '0000-01-01'
    for h in holdings:
        for dh in h['dataHoldings']:
            s = dh['dateStart'][:10]
            e = dh['dateEnd'][:10]
            if s < earliest:
                earliest = s
            if e > latest:
                latest = e

    if earliest > '9000':
        print(f"  ✗ Keine Holdings")
        return False

    # Start from 2020 — most stations only have data from ~2020 onwards
    api_start = max(earliest, '2020-01-01')
    api_end = min(latest, datetime.date.today().isoformat())

    start = datetime.date.fromisoformat(api_start)
    end = datetime.date.fromisoformat(api_end)

    # Generate month ranges
    months = []
    current = start.replace(day=1)
    while current <= end:
        next_month = (current.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        month_end = next_month - datetime.timedelta(days=1)
        if month_end > end:
            month_end = end
        months.append((current, month_end))
        current = next_month

    print(f"  {api_start} — {api_end}, {len(months)} Monate...", end='', flush=True)

    all_rows = []
    empty_streak = 0

    for i, (m_start, m_end) in enumerate(months):
        from_dt = f'{m_start}T00:00:00Z'
        to_dt = f'{m_end}T23:59:59Z'

        for attempt in range(3):
            try:
                resp = requests.get(
                    f'{API_BASE}/stations/{station_id}/data',
                    params={
                        'time-series-code': 'wlo',
                        'from': from_dt,
                        'to': to_dt,
                        'resolution': RESOLUTION,
                    },
                    timeout=30,
                )
                if resp.status_code == 429:
                    wait = 15 * (attempt + 1)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()

                if isinstance(data, list) and len(data) > 0:
                    for d in data:
                        all_rows.append((d['eventDate'], d['value']))
                    empty_streak = 0
                else:
                    empty_streak += 1
                break

            except requests.exceptions.HTTPError:
                break
            except Exception:
                break

        # Skip remaining months if many empty in a row (no data in this range)
        if empty_streak > 12:
            break

        time.sleep(2.2)

    if not all_rows:
        print(f" KEINE DATEN")
        return False

    df = pd.DataFrame(all_rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')
    df['time'] = pd.to_datetime(df['time']).dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
    df.to_csv(csv_path, index=False)

    n = len(df)
    years = n / (4 * 24 * 365.25)
    print(f" {n} Werte ({years:.1f} J)")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(CATALOG_PATH) as f:
        all_stations = json.load(f)

    # Skip stations we already have from UHSLC
    stations = [s for s in all_stations if s['code'] not in UHSLC_CHS_CODES]
    skipped = len(all_stations) - len(stations)

    print("=" * 70)
    print("Download Water Level Observations — CHS IWLS API (alle Stationen)")
    print("=" * 70)
    print(f"Stationen gesamt: {len(all_stations)}")
    print(f"UHSLC übersprungen: {skipped}")
    print(f"Zu downloaden: {len(stations)}")
    print(f"Auflösung: {RESOLUTION}")
    print(f"Ausgabe: {OUTPUT_DIR}")
    print()

    success = 0
    failed = 0
    skipped_existing = 0

    for i, station in enumerate(stations):
        print(f"[{i+1}/{len(stations)}] {station['code']:>6s} | {station['name']}")

        result = download_station(station, OUTPUT_DIR)
        if result:
            success += 1
        else:
            failed += 1

    print(f"\n{'='*70}")
    print(f"Ergebnis: {success} erfolgreich, {failed} fehlgeschlagen")

    # Summary
    total_mb = 0
    n_files = 0
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.csv'):
            total_mb += os.path.getsize(os.path.join(OUTPUT_DIR, f)) / (1024*1024)
            n_files += 1
    print(f"Dateien: {n_files}, Gesamt: {total_mb:.0f} MB")


if __name__ == '__main__':
    main()
