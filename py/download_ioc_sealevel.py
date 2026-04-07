#!/usr/bin/env python3
"""
Download sea level data from IOC Sea Level Monitoring for French Caribbean stations.

Stations:
  desh - Deshaies, Guadeloupe (16.3053, -61.7959) — sensor: rad(m)
  prec - Le Précheur, Martinique (14.8076, -61.2266) — sensor: prs(m)

API returns HTML table. We parse it to extract water level data.
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta

# Configuration
STATIONS = [
    {
        'code': 'desh',
        'name': 'Deshaies',
        'outdir': '/home/oliver/water_levels/Guadeloupe_IOC',
        'outfile': 'desh_deshaies.csv',
        'start_year': 2020,
        'end_date': '2026-04-06',
        'sensor_col': 'rad(m)',
    },
    {
        'code': 'prec',
        'name': 'Le Précheur',
        'outdir': '/home/oliver/water_levels/Martinique_IOC',
        'outfile': 'prec_le_precheur.csv',
        'start_year': 2020,
        'end_date': '2025-03-15',  # data stops around Feb/Mar 2025
        'sensor_col': 'prs(m)',
    },
]

BASE_URL = "http://www.ioc-sealevelmonitoring.org/bgraph.php"
CHUNK_DAYS = 30
DELAY = 1.0
TIMEOUT = 90


def parse_html_table(html_text, target_sensor):
    """Parse IOC HTML table response and extract (datetime_str, level_m) tuples.

    Args:
        html_text: Raw HTML response
        target_sensor: Column name to extract, e.g. 'rad(m)' or 'prs(m)'
    """
    rows = []

    # Find column headers: <td class=field>colname</td>
    field_matches = re.findall(r'<td class=field>(.*?)</td>', html_text[:1000])

    if not field_matches:
        return rows

    # Find target column index among field columns (0-based)
    target_idx = None
    for i, name in enumerate(field_matches):
        if name == target_sensor:
            target_idx = i
            break

    if target_idx is None:
        # Fallback: any column with (m) that isn't bat
        for i, name in enumerate(field_matches):
            if '(m)' in name and 'bat' not in name:
                target_idx = i
                break

    if target_idx is None:
        return rows

    # Parse data rows
    row_pattern = re.compile(
        r'<tr><td>(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})</td>(.*?)</tr>'
    )

    for match in row_pattern.finditer(html_text):
        dt_str = match.group(1)
        cells_html = match.group(2)
        cell_values = re.findall(r'<td[^>]*>(.*?)</td>', cells_html)

        if target_idx >= len(cell_values):
            continue

        val_str = cell_values[target_idx].strip()

        if not val_str or val_str == '&nbsp;' or val_str == '-9999' or val_str == '-':
            continue

        try:
            level = float(val_str)
        except ValueError:
            continue

        if level <= -9999 or level > 100 or level < -100:
            continue

        rows.append((dt_str, level))

    return rows


def download_station(station):
    """Download all available data for a station in 30-day chunks."""
    code = station['code']
    name = station['name']
    outdir = station['outdir']
    outfile = station['outfile']
    sensor_col = station['sensor_col']

    os.makedirs(outdir, exist_ok=True)

    end_date = datetime.strptime(station['end_date'], '%Y-%m-%d')
    start_date = datetime(station['start_year'], 1, 1)

    all_data = {}  # datetime_str -> level, for dedup

    current_end = end_date
    chunk_num = 0
    empty_count = 0

    print(f"\n{'='*60}")
    print(f"Downloading {name} ({code}) — sensor: {sensor_col}")
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"{'='*60}")

    while current_end > start_date:
        chunk_num += 1
        endtime_str = current_end.strftime('%Y-%m-%d')

        url = (f"{BASE_URL}?code={code}&output=tab"
               f"&period={CHUNK_DAYS}&endtime={endtime_str}")

        print(f"  Chunk {chunk_num:3d}: ending {endtime_str} ... ", end='', flush=True)

        success = False
        resp = None
        for attempt in range(2):
            try:
                resp = requests.get(url, timeout=TIMEOUT)
                if resp.status_code == 200:
                    success = True
                    break
                else:
                    print(f"HTTP {resp.status_code}", end=' ', flush=True)
            except requests.RequestException as e:
                print(f"Error: {e}", end=' ', flush=True)
            if attempt == 0:
                print("retrying...", end=' ', flush=True)
                time.sleep(3)

        if not success:
            print("FAILED")
            current_end -= timedelta(days=CHUNK_DAYS)
            time.sleep(DELAY)
            continue

        rows = parse_html_table(resp.text, sensor_col)
        new_count = 0
        for dt_str, level in rows:
            if dt_str not in all_data:
                all_data[dt_str] = level
                new_count += 1

        print(f"{len(rows):6d} rows ({new_count:6d} new) | total: {len(all_data)}")

        if len(rows) == 0:
            empty_count += 1
            if empty_count >= 5:
                print(f"  5 consecutive empty chunks, stopping early.")
                break
        else:
            empty_count = 0

        current_end -= timedelta(days=CHUNK_DAYS)
        time.sleep(DELAY)

    # Sort and write CSV
    if not all_data:
        print(f"\nNo data found for {name}!")
        return

    sorted_data = sorted(all_data.items())
    outpath = os.path.join(outdir, outfile)

    with open(outpath, 'w') as f:
        f.write('datetime_utc,level_m\n')
        for dt_str, level in sorted_data:
            f.write(f'{dt_str},{level}\n')

    first_dt = sorted_data[0][0]
    last_dt = sorted_data[-1][0]

    print(f"\n  === Results for {name} ===")
    print(f"    Total data points: {len(sorted_data):,}")
    print(f"    Date range: {first_dt} to {last_dt}")
    print(f"    Saved to: {outpath}")
    print(f"    File size: {os.path.getsize(outpath) / 1024:.1f} KB")


def main():
    print("IOC Sea Level Monitoring - Data Download")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    for station in STATIONS:
        download_station(station)

    print(f"\n{'='*60}")
    print("Done!")


if __name__ == '__main__':
    main()
