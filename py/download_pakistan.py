#!/usr/bin/env python3
"""
Download sea level data for Pakistan: Karachi (UHSLC RQDS),
Gwadar + Ormara (IOC SLSMF scrape, 1-min data resampled to hourly).

Keti Bandar skipped (IOC data too sparse).
"""
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

OUTPUT_DIR = Path('/home/oliver/water_levels/Pakistan')
UHSLC_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'
IOC_URL = 'http://www.ioc-sealevelmonitoring.org/bgraph.php'

UHSLC_STATIONS = [
    {'uhslc_id': 147, 'name': 'Karachi', 'lat': 24.812, 'lon': 66.975, 'country': 'Pakistan'},
]

IOC_STATIONS = [
    {'code': 'gwda', 'name': 'Gwadar', 'lat': 25.1122, 'lon': 62.3394,
     'country': 'Pakistan', 'start': '2020-11-01', 'end': '2022-10-28'},
    {'code': 'orma', 'name': 'Ormara', 'lat': 25.2037, 'lon': 64.6764,
     'country': 'Pakistan', 'start': '2019-11-01', 'end': '2021-12-31'},
]


def download_uhslc(station):
    sid = station['uhslc_id']
    name = station['name']
    csv_path = OUTPUT_DIR / f'uhslc_{sid}_{name}.csv'
    if csv_path.exists() and csv_path.stat().st_size > 10000:
        n = sum(1 for _ in open(csv_path))
        print(f"  {name}: already {n} lines, skipping")
        return True
    url = f'{UHSLC_BASE}/global_hourly_rqds.csv?time,sea_level,station_name&uhslc_id={sid}'
    print(f"  {name}: downloading UHSLC...", end='', flush=True)
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    lines = resp.text.strip().split('\n')
    rows = []
    for line in lines[2:]:
        parts = line.split(',')
        if len(parts) >= 2 and parts[1] and parts[1] != 'NaN':
            try:
                rows.append((parts[0], float(parts[1]) / 1000.0))
            except ValueError:
                pass
    if not rows:
        print(" no data")
        return False
    df = pd.DataFrame(rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')
    df.to_csv(csv_path, index=False)
    print(f" {len(df)} values ({df['time'].iloc[0][:10]} - {df['time'].iloc[-1][:10]})")
    return True


def parse_ioc_html(html, sensor_priority=('pr1', 'rad', 'prs', 'pwl')):
    """Extract (time, level_m) rows from IOC bgraph.php HTML table."""
    header_match = re.search(r'<tr>(<td[^>]*>[^<]*</td>)+</tr>', html)
    if not header_match:
        return []
    header_row = header_match.group(0)
    col_names = re.findall(r'<td[^>]*>([^<]+)</td>', header_row)
    # First col is Time, rest are sensors like "pr1(m)"
    sensor_cols = [c.split('(')[0] for c in col_names[1:]]
    # Choose preferred sensor index
    sensor_idx = None
    for pref in sensor_priority:
        if pref in sensor_cols:
            sensor_idx = sensor_cols.index(pref)
            break
    if sensor_idx is None and sensor_cols:
        sensor_idx = 0
    if sensor_idx is None:
        return []

    row_pattern = re.compile(r'<tr>(?:<td[^>]*>[^<]*</td>)+</tr>')
    rows = []
    for row in row_pattern.findall(html)[1:]:  # skip header
        cells = re.findall(r'<td[^>]*>([^<]*)</td>', row)
        if len(cells) < 2:
            continue
        ts = cells[0].strip()
        val_str = cells[1 + sensor_idx].strip() if len(cells) > 1 + sensor_idx else ''
        if not val_str or val_str == '-':
            continue
        try:
            val = float(val_str)
            rows.append((ts, val))
        except ValueError:
            pass
    return rows


def download_ioc_station(station):
    code = station['code']
    name = station['name']
    csv_path = OUTPUT_DIR / f'ioc_{code}_{name}.csv'
    if csv_path.exists() and csv_path.stat().st_size > 10000:
        n = sum(1 for _ in open(csv_path))
        print(f"  {name} ({code}): already {n} lines, skipping")
        return True

    start = datetime.strptime(station['start'], '%Y-%m-%d')
    end = datetime.strptime(station['end'], '%Y-%m-%d')
    # Scrape in 30-day chunks (IOC API limit is 31 days)
    all_rows = []
    current = start
    n_windows = 0
    n_with_data = 0
    while current < end:
        window_end = min(current + timedelta(days=30), end)
        endtime_str = window_end.strftime('%Y-%m-%d')
        n_windows += 1
        for attempt in range(3):
            try:
                r = requests.get(IOC_URL, params={
                    'code': code, 'output': 'tab',
                    'period': 30, 'endtime': endtime_str,
                }, timeout=60)
                r.raise_for_status()
                rows = parse_ioc_html(r.text)
                if rows:
                    n_with_data += 1
                    all_rows.extend(rows)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  warn window {endtime_str}: {e}")
                time.sleep(2 + attempt * 5)
        current = window_end
        time.sleep(1)  # Be polite to IOC server
        if n_windows % 5 == 0:
            print(f"  {name}: {n_windows} windows, {len(all_rows)} rows so far ({n_with_data} windows had data)", flush=True)

    if not all_rows:
        print(f"  {name}: NO DATA")
        return False

    df = pd.DataFrame(all_rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')
    # Resample to hourly mean (from 1-min data)
    df['time'] = pd.to_datetime(df['time'])
    # Nearest-hour rounding (avoids ~14.5° M2 phase lag).
    df = (df.set_index('time').shift(freq='30min')
            .resample('1h').mean().dropna().reset_index())
    df['time'] = df['time'].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    df.to_csv(csv_path, index=False)
    years = len(df) / (24 * 365.25)
    print(f"  {name}: {len(df)} hourly values ({years:.1f}y, "
          f"{df['time'].iloc[0][:10]} - {df['time'].iloc[-1][:10]})")
    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("Pakistan water level data: UHSLC + IOC SLSMF")
    print("=" * 70)

    print("\n--- UHSLC ---")
    for s in UHSLC_STATIONS:
        download_uhslc(s)

    print("\n--- IOC SLSMF ---")
    for s in IOC_STATIONS:
        download_ioc_station(s)

    print("\n--- Summary ---")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.csv'):
            path = OUTPUT_DIR / f
            n = sum(1 for _ in open(path)) - 1
            size_kb = path.stat().st_size / 1024
            print(f"  {f}: {size_kb:.0f} KB, {n} values")


if __name__ == '__main__':
    main()
