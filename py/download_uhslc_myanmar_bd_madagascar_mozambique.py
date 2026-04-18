#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for high-tidal-range stations
in Myanmar, Bangladesh, Madagascar, and Mozambique. RQDS (Research Quality).
"""

import os
import time
import requests
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/IndianOcean_UHSLC_BD_MM_MG_MZ'
ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

STATIONS = [
    # Bangladesh (Meghna-Mündung, bis 6 m Tidenhub)
    {'uhslc_id': 124, 'name': 'Chittagong',    'lat': 22.247, 'lon': 91.825, 'country': 'Bangladesh', 'tz': 'Asia/Dhaka',       'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 134, 'name': 'Hiron Point',   'lat': 21.783, 'lon': 89.467, 'country': 'Bangladesh', 'tz': 'Asia/Dhaka',       'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 135, 'name': 'Khal 10',       'lat': 22.267, 'lon': 91.817, 'country': 'Bangladesh', 'tz': 'Asia/Dhaka',       'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 136, 'name': "Cox's Bazaar",  'lat': 21.450, 'lon': 91.833, 'country': 'Bangladesh', 'tz': 'Asia/Dhaka',       'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 137, 'name': 'Teknaf',        'lat': 20.883, 'lon': 92.300, 'country': 'Bangladesh', 'tz': 'Asia/Dhaka',       'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 138, 'name': 'Charchanga',    'lat': 22.217, 'lon': 91.050, 'country': 'Bangladesh', 'tz': 'Asia/Dhaka',       'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 139, 'name': 'Khepupara',     'lat': 21.833, 'lon': 89.833, 'country': 'Bangladesh', 'tz': 'Asia/Dhaka',       'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    # Myanmar (Golf von Martaban, bis 7 m Tidenhub)
    {'uhslc_id': 906, 'name': 'Moulmein',         'lat': 16.465, 'lon': 97.622, 'country': 'Myanmar', 'tz': 'Asia/Yangon',     'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 907, 'name': 'Akyab (Sittwe)',   'lat': 20.140, 'lon': 92.903, 'country': 'Myanmar', 'tz': 'Asia/Yangon',     'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    # Madagascar (Mosambik-Kanal, bis 5 m)
    {'uhslc_id': 150, 'name': 'Nosy Be',          'lat': -13.400, 'lon': 48.300, 'country': 'Madagascar', 'tz': 'Indian/Antananarivo', 'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    # Mozambique (3-5 m)
    {'uhslc_id': 190, 'name': 'Maputo',           'lat': -25.975, 'lon': 32.570, 'country': 'Mozambique', 'tz': 'Africa/Maputo',    'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 191, 'name': 'Antonio Enes',     'lat': -16.232, 'lon': 39.902, 'country': 'Mozambique', 'tz': 'Africa/Maputo',    'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 192, 'name': 'Pemba',            'lat': -12.968, 'lon': 40.487, 'country': 'Mozambique', 'tz': 'Africa/Maputo',    'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 193, 'name': 'Nacala',           'lat': -14.463, 'lon': 40.680, 'country': 'Mozambique', 'tz': 'Africa/Maputo',    'gloss_id': None, 'dataset': 'global_hourly_rqds'},
    {'uhslc_id': 900, 'name': 'Inhambane',        'lat': -23.868, 'lon': 35.377, 'country': 'Mozambique', 'tz': 'Africa/Maputo',    'gloss_id': None, 'dataset': 'global_hourly_rqds'},
]


def download_station(station):
    sid = station['uhslc_id']
    name = station['name']
    dataset = station['dataset']
    safe_name = name.replace(' ', '_').replace("'", '').replace('.', '').replace(',', '').replace('(', '').replace(')', '').replace('#', '')
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

        except requests.exceptions.Timeout:
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f" [timeout, retry in {wait}s]", end='', flush=True)
                time.sleep(wait)
            else:
                print(f" TIMEOUT")
                return False
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

    print("=" * 70)
    print("UHSLC ERDDAP — Bangladesh + Myanmar + Madagascar + Mozambique")
    print("=" * 70)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Stations: {len(STATIONS)}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']}, {station['country']})")
        if download_station(station):
            success += 1
        time.sleep(3)

    print(f"\n{'='*70}")
    print(f"Result: {success}/{len(STATIONS)} successful")

    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.csv'):
            path = os.path.join(OUTPUT_DIR, f)
            size_kb = os.path.getsize(path) / 1024
            n_lines = sum(1 for _ in open(path)) - 1
            years = n_lines / (24 * 365.25)
            print(f"  {f}: {size_kb:.0f} KB, {n_lines} values ({years:.1f} years)")


if __name__ == '__main__':
    main()
