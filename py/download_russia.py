#!/usr/bin/env python3
"""
Download sea level data for Russian Pacific coast stations from IOC SLSMF.
Scrapes 1-min data, resamples to hourly.
"""
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

OUTPUT_DIR = Path('/home/oliver/water_levels/Russia_IOC')
IOC_URL = 'http://www.ioc-sealevelmonitoring.org/bgraph.php'

# Scrape 2023-01-01 .. 2025-10-14 (most active stations have data to this range)
DEFAULT_START = '2023-01-01'
DEFAULT_END = '2025-10-14'

STATIONS = [
    {'code': 'khol', 'name': 'Kholmsk',             'lat': 47.0506, 'lon': 142.0439},
    {'code': 'kors', 'name': 'Korsakov',            'lat': 46.6333, 'lon': 142.7667},
    {'code': 'kuri', 'name': "Kuril'sk",            'lat': 45.2300, 'lon': 147.8800},
    {'code': 'naho', 'name': 'Nakhodka',            'lat': 42.7800, 'lon': 132.8600},
    {'code': 'nksk', 'name': "Nikol'skoe",          'lat': 55.2000, 'lon': 166.0200},
    {'code': 'petr', 'name': 'Petropavlovsk',       'lat': 53.0167, 'lon': 158.6500},
    {'code': 'poro', 'name': 'Poronajsk',           'lat': 49.2200, 'lon': 143.0900},
    {'code': 'posi', 'name': "Pos'et",              'lat': 42.6500, 'lon': 130.8000},
    {'code': 'preo', 'name': 'Preobrazheniye',      'lat': 42.9092, 'lon': 133.9225},
    {'code': 'rudn', 'name': 'Rudnaya Pristan',     'lat': 44.3500, 'lon': 135.8000},
    {'code': 'sosu', 'name': 'Sosunovo',            'lat': 46.5300, 'lon': 138.3300},
    {'code': 'sove', 'name': "Sovetskaya Gavan'",   'lat': 48.9700, 'lon': 140.2900},
    {'code': 'star', 'name': 'Starodubskoe',        'lat': 47.4100, 'lon': 142.8200},
    {'code': 'ugle', 'name': 'Uglegorsk',           'lat': 49.0800, 'lon': 142.0700},
    {'code': 'vlad', 'name': 'Vladivostok',         'lat': 43.1300, 'lon': 131.9200},
]


def parse_ioc_html(html, sensor_priority=('pr1', 'prs', 'rad', 'pwl', 'bub')):
    header_match = re.search(r'<tr>(<td[^>]*>[^<]*</td>)+</tr>', html)
    if not header_match:
        return []
    header_row = header_match.group(0)
    col_names = re.findall(r'<td[^>]*>([^<]+)</td>', header_row)
    sensor_cols = [c.split('(')[0] for c in col_names[1:]]
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
    for row in row_pattern.findall(html)[1:]:
        cells = re.findall(r'<td[^>]*>([^<]*)</td>', row)
        if len(cells) < 2:
            continue
        ts = cells[0].strip()
        val_str = cells[1 + sensor_idx].strip() if len(cells) > 1 + sensor_idx else ''
        if not val_str or val_str == '-':
            continue
        try:
            rows.append((ts, float(val_str)))
        except ValueError:
            pass
    return rows


def download_station(station, start_str=DEFAULT_START, end_str=DEFAULT_END):
    code = station['code']
    name = station['name']
    safe = name.replace(' ', '_').replace("'", '').replace('.', '').replace(',', '')
    csv_path = OUTPUT_DIR / f'ioc_{code}_{safe}.csv'
    if csv_path.exists() and csv_path.stat().st_size > 10000:
        n = sum(1 for _ in open(csv_path))
        print(f"  {name}: already {n} lines, skip")
        return True
    start = datetime.strptime(start_str, '%Y-%m-%d')
    end = datetime.strptime(end_str, '%Y-%m-%d')
    all_rows = []
    current = start
    n_win, n_ok = 0, 0
    while current < end:
        w_end = min(current + timedelta(days=30), end)
        endtime_str = w_end.strftime('%Y-%m-%d')
        n_win += 1
        for attempt in range(3):
            try:
                r = requests.get(IOC_URL, params={
                    'code': code, 'output': 'tab',
                    'period': 30, 'endtime': endtime_str,
                }, timeout=60)
                r.raise_for_status()
                rows = parse_ioc_html(r.text)
                if rows:
                    n_ok += 1
                    all_rows.extend(rows)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  warn {code}@{endtime_str}: {e}")
                time.sleep(2 + attempt * 5)
        current = w_end
        time.sleep(0.8)
    if not all_rows:
        print(f"  {name}: NO DATA")
        return False
    df = pd.DataFrame(all_rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').resample('1h').mean().dropna().reset_index()
    df['time'] = df['time'].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    df.to_csv(csv_path, index=False)
    years = len(df) / (24 * 365.25)
    print(f"  {name}: {len(df)} hourly values ({years:.1f}y, "
          f"{df['time'].iloc[0][:10]} - {df['time'].iloc[-1][:10]}, "
          f"{n_ok}/{n_win} windows with data)")
    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print(f"Russia IOC SLSMF: {len(STATIONS)} stations, {DEFAULT_START} .. {DEFAULT_END}")
    print("=" * 70)
    ok = 0
    for i, s in enumerate(STATIONS):
        print(f"\n[{i+1}/{len(STATIONS)}] {s['name']} ({s['code']}):", flush=True)
        if download_station(s):
            ok += 1
    print(f"\n{'='*70}\nResult: {ok}/{len(STATIONS)} successful")


if __name__ == '__main__':
    main()
