#!/usr/bin/env python3
"""
Download HW/LW tide predictions from badatime.com for South Korean stations.
Data source: KHOA (Korea Hydrographic and Oceanographic Agency), license #1146.
Times are in KST (UTC+9).
"""

import os
import re
import json
import time
import requests

OUTPUT_DIR = '/home/oliver/water_levels/Korea_badatime'
STATIONS_FILE = '/home/oliver/harmonics/help/badatime_selected.json'

HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}

YEARS_MONTHS = []
for year in [2025, 2026]:
    for month in range(1, 13):
        YEARS_MONTHS.append(f'{year}-{month:02d}')


def parse_daily_page(html, year, month):
    """Parse HW/LW data from badatime daily page HTML.
    Returns list of (date_str, time_str, height_cm, type) tuples.
    Type: 'HW' or 'LW'.
    """
    entries = []

    # Find table rows with tide data
    # Each day has manjo (HW) and ganjo (LW) cells
    # Pattern: day number, then HW/LW entries with time and height

    # Split by table rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

    for row in rows:
        # Extract day number
        day_match = re.search(r'<td[^>]*class="[^"]*day[^"]*"[^>]*>.*?(\d{1,2})', row, re.DOTALL)
        if not day_match:
            # Try alternative: first td with just a number
            day_match = re.search(r'<td[^>]*>\s*(\d{1,2})\s*\(', row)
        if not day_match:
            continue

        day = int(day_match.group(1))
        if day < 1 or day > 31:
            continue

        date_str = f'{year}-{month:02d}-{day:02d}'

        # Extract HW (manjo) entries
        manjo_cells = re.findall(r'<td[^>]*class="[^"]*manjo[^"]*"[^>]*>(.*?)</td>', row, re.DOTALL)
        for cell in manjo_cells:
            # Time and height: e.g., "08:05 (110)" or "<b>08:05 (&nbsp;110) </b>"
            matches = re.findall(r'(\d{1,2}:\d{2})\s*\(\s*(?:&nbsp;)?\s*(-?\d+)\s*\)', cell)
            for time_str, height in matches:
                entries.append((date_str, time_str, int(height), 'HW'))

        # Extract LW (ganjo) entries
        ganjo_cells = re.findall(r'<td[^>]*class="[^"]*ganjo[^"]*"[^>]*>(.*?)</td>', row, re.DOTALL)
        for cell in ganjo_cells:
            matches = re.findall(r'(\d{1,2}:\d{2})\s*\(\s*(?:&nbsp;)?\s*(-?\d+)\s*\)', cell)
            for time_str, height in matches:
                entries.append((date_str, time_str, int(height), 'LW'))

    return entries


def download_station(idx, name):
    """Download all monthly HW/LW data for one station."""
    safe_name = re.sub(r'[^\w]', '_', name)
    json_path = os.path.join(OUTPUT_DIR, f'{idx:04d}_{safe_name}.json')

    if os.path.exists(json_path) and os.path.getsize(json_path) > 1000:
        with open(json_path) as f:
            data = json.load(f)
        print(f"  schon vorhanden ({len(data)} Eintraege)")
        return True

    all_entries = []
    for ym in YEARS_MONTHS:
        year, month = int(ym[:4]), int(ym[5:7])
        url = f'https://badatime.com/{idx}/daily/{ym}'

        for attempt in range(3):
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code == 200:
                    entries = parse_daily_page(r.text, year, month)
                    all_entries.extend(entries)
                    break
                else:
                    if attempt < 2:
                        time.sleep(5)
            except Exception:
                if attempt < 2:
                    time.sleep(5)

        time.sleep(0.3)

    if not all_entries:
        print(f"  KEINE DATEN")
        return False

    # Save as JSON
    data = [{'date': d, 'time': t, 'height_cm': h, 'type': tp}
            for d, t, h, tp in all_entries]
    with open(json_path, 'w') as f:
        json.dump(data, f)

    n_hw = sum(1 for e in data if e['type'] == 'HW')
    n_lw = sum(1 for e in data if e['type'] == 'LW')
    first = data[0]['date'] if data else '?'
    last = data[-1]['date'] if data else '?'
    print(f"  {len(data)} Eintraege ({n_hw} HW, {n_lw} LW, {first} - {last})")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(STATIONS_FILE, encoding='utf-8') as f:
        stations = json.load(f)

    print("=" * 70)
    print("Download HW/LW Tide Data -- badatime.com (South Korea)")
    print("=" * 70)
    print(f"Stationen: {len(stations)}")
    print(f"Zeitraum: {YEARS_MONTHS[0]} bis {YEARS_MONTHS[-1]}")
    print()

    success = 0
    for i, s in enumerate(stations):
        print(f"[{i+1:2d}/{len(stations)}] {s['name']} (idx={s['idx']})")
        if download_station(s['idx'], s['name']):
            success += 1
        print()

    print(f"{'='*70}")
    print(f"Ergebnis: {success}/{len(stations)} erfolgreich")


if __name__ == '__main__':
    main()
