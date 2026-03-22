#!/usr/bin/env python3
"""
Download hourly sea level data from Australian Bureau of Meteorology (BOM)
Australian Baseline Sea Level Monitoring Project (ABSLMP).
Saves as NPZ files for UTide analysis.
"""

import numpy as np
import requests
import time
from datetime import datetime
from pathlib import Path
import re

OUTPUT_DIR = Path("/home/oliver/water_levels/Australia_BOM/npz")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.bom.gov.au/ntc"

STATIONS = [
    {'id': 'IDO71001', 'name': 'Cape Ferguson', 'lat': -19.28, 'lon': 147.06, 'start': 1991},
    {'id': 'IDO71002', 'name': 'Rosslyn Bay', 'lat': -23.16, 'lon': 150.79, 'start': 1993},
    {'id': 'IDO71003', 'name': 'Port Kembla', 'lat': -34.47, 'lon': 150.91, 'start': 1991},
    {'id': 'IDO71004', 'name': 'Stony Point', 'lat': -38.37, 'lon': 145.22, 'start': 1993},
    {'id': 'IDO71005', 'name': 'Burnie', 'lat': -41.05, 'lon': 145.91, 'start': 1993},
    {'id': 'IDO71006', 'name': 'Lorne', 'lat': -38.55, 'lon': 143.99, 'start': 1993},
    {'id': 'IDO71007', 'name': 'Spring Bay', 'lat': -42.55, 'lon': 147.93, 'start': 1991},
    {'id': 'IDO71008', 'name': 'Portland', 'lat': -38.34, 'lon': 141.61, 'start': 1991},
    {'id': 'IDO71009', 'name': 'Port Stanvac', 'lat': -35.11, 'lon': 138.47, 'start': 1992},
    {'id': 'IDO71010', 'name': 'Thevenard', 'lat': -32.15, 'lon': 133.64, 'start': 1992},
    {'id': 'IDO71011', 'name': 'Esperance', 'lat': -33.87, 'lon': 121.90, 'start': 1992},
    {'id': 'IDO71012', 'name': 'Hillarys', 'lat': -31.83, 'lon': 115.74, 'start': 1992},
    {'id': 'IDO71013', 'name': 'Broome', 'lat': -18.00, 'lon': 122.22, 'start': 1992},
    {'id': 'IDO71014', 'name': 'Darwin', 'lat': -12.47, 'lon': 130.85, 'start': 1991},
    {'id': 'IDO71015', 'name': 'Groote Eylandt', 'lat': -13.86, 'lon': 136.42, 'start': 1993},
    {'id': 'IDO71016', 'name': 'Cocos Islands', 'lat': -12.12, 'lon': 96.89, 'start': 1993},
    {'id': 'IDO71017', 'name': 'Thursday Island', 'lat': -10.58, 'lon': 142.22, 'start': 2002},
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (research; tide analysis)'}


def download_station(station):
    """Download all available years for one station."""
    sid = station['id']
    name = station['name']
    safe_name = name.replace(' ', '_')
    npz_path = OUTPUT_DIR / f"{safe_name}.npz"

    if npz_path.exists():
        d = np.load(npz_path, allow_pickle=True)
        n = len(d['levels_m'])
        years = n / (24 * 365.25)
        print(f"  schon vorhanden ({n} Werte, {years:.1f}J)")
        return True

    all_times = []
    all_values = []

    start_year = station['start']
    end_year = 2026

    for year in range(start_year, end_year):
        url = f"{BASE_URL}/{sid}/{sid}_{year}.csv"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404 or resp.status_code == 403:
                continue
            resp.raise_for_status()

            lines = resp.text.strip().split('\n')
            count = 0
            for line in lines[1:]:  # Skip header
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        dt_str = parts[0].strip()
                        val_str = parts[1].strip()
                        val = float(val_str)
                        if val < -100 or val > 100:  # -9999 = missing
                            continue
                        dt = datetime.strptime(dt_str, '%d-%b-%Y %H:%M')
                        all_times.append(dt)
                        all_values.append(val)
                        count += 1
                    except (ValueError, IndexError):
                        pass
            if count > 0:
                print(f"    {year}: {count} Werte", flush=True)

        except Exception as e:
            if '404' not in str(e) and '403' not in str(e):
                print(f"    {year}: FEHLER {e}")

        time.sleep(0.3)

    if not all_times:
        print(f"  ✗ Keine Daten")
        return False

    times_arr = np.array(all_times, dtype='datetime64[s]')
    values_arr = np.array(all_values, dtype=np.float64)

    sort_idx = np.argsort(times_arr)
    times_arr = times_arr[sort_idx]
    values_arr = values_arr[sort_idx]

    _, unique_idx = np.unique(times_arr, return_index=True)
    times_arr = times_arr[unique_idx]
    values_arr = values_arr[unique_idx]

    np.savez_compressed(npz_path,
                        datetimes_utc=times_arr,
                        levels_m=values_arr,
                        station_id=sid,
                        name=name,
                        latitude=station['lat'],
                        longitude=station['lon'],
                        datum='AHD',
                        )

    years = len(times_arr) / (24 * 365.25)
    print(f"  ✓ {len(times_arr)} Werte ({years:.1f} Jahre) → {npz_path.name}")
    return True


def main():
    print("=" * 70)
    print("Download BOM ABSLMP — Australien Pegeldaten")
    print("=" * 70)
    print(f"\n{len(STATIONS)} Stationen\n")

    for i, s in enumerate(STATIONS, 1):
        print(f"\n[{i}/{len(STATIONS)}] {s['id']} | {s['name']} "
              f"({s['lat']:.2f}°S, {s['lon']:.2f}°E)")
        download_station(s)

    print(f"\n\nFertig. NPZ-Dateien in: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
