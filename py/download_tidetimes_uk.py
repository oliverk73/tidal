#!/usr/bin/env python3
"""
Download HW/LW tide predictions from tidetimes.co.uk for UK stations.
Downloads 2 years (2025-2026) of daily HW/LW data.
Times are in UK local time (GMT/BST).
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timedelta

OUTPUT_DIR = '/home/oliver/water_levels/UK_tidetimes'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
}

# Stations: slug for URL, name for output, coordinates from PSMSL/known sources
STATIONS = [
    {
        'slug': 'rosyth',
        'name': 'Rosyth',
        'lat': 56.0167, 'lon': -3.4500,
    },
    {
        'slug': 'dunbar',
        'name': 'Dunbar',
        'lat': 56.0060, 'lon': -2.5170,
    },
    {
        'slug': 'walton-on-the-naze',
        'name': 'Walton-on-the-Naze',
        'lat': 51.8500, 'lon': 1.2670,
    },
    {
        'slug': 'southend-on-sea',
        'name': 'Southend',
        'lat': 51.5145, 'lon': 0.7238,
    },
    {
        'slug': 'tilbury',
        'name': 'Tilbury',
        'lat': 51.4633, 'lon': 0.3583,
    },
    {
        'slug': 'swansea',
        'name': 'Swansea',
        'lat': 51.6170, 'lon': -3.9170,
    },
    {
        'slug': 'liverpool-alfred-dock',
        'name': 'Birkenhead (Alfred Dock)',
        'lat': 53.3917, 'lon': -3.0208,
    },
    {
        'slug': 'douglas',
        'name': 'Douglas',
        'lat': 54.1500, 'lon': -4.4670,
    },
    {
        'slug': 'belfast',
        'name': 'Belfast',
        'lat': 54.6000, 'lon': -5.9170,
    },
]

# Date range: 2025-01-01 to 2026-12-31
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2026, 12, 31)


def parse_hwlw(html, date_str):
    """Parse HW/LW data from tidetimes.co.uk daily page."""
    entries = []

    pattern = (
        r'<dt>(High Tide|Low Tide):</dt>\s*<dd>(\d{2}:\d{2})</dd>\s*'
        r'<dt>Height:</dt>\s*<dd>([\d.]+)m</dd>'
    )

    for m in re.finditer(pattern, html):
        tide_type = 'HW' if m.group(1) == 'High Tide' else 'LW'
        time_str = m.group(2)
        height_m = float(m.group(3))

        entries.append({
            'date': date_str,
            'time': time_str,
            'height_m': height_m,
            'type': tide_type,
        })

    return entries


def download_station(station):
    """Download all daily HW/LW data for one station."""
    slug = station['slug']
    name = station['name']
    safe_name = name.replace(' ', '_')
    json_path = os.path.join(OUTPUT_DIR, f'{safe_name}.json')

    if os.path.exists(json_path) and os.path.getsize(json_path) > 1000:
        with open(json_path) as f:
            data = json.load(f)
        n = len(data.get('entries', []))
        print(f"  schon vorhanden ({n} Eintraege)")
        return True

    all_entries = []
    current = START_DATE
    total_days = (END_DATE - START_DATE).days + 1
    day_count = 0
    errors = 0

    while current <= END_DATE:
        date_str = current.strftime('%Y-%m-%d')
        url_date = current.strftime('%Y%m%d')
        url = f'https://www.tidetimes.co.uk/{slug}-tide-times-{url_date}'

        for attempt in range(3):
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code == 200:
                    entries = parse_hwlw(r.text, date_str)
                    all_entries.extend(entries)
                    break
                elif r.status_code == 404:
                    # Station page doesn't exist for this date
                    break
                else:
                    if attempt < 2:
                        time.sleep(2)
            except Exception:
                if attempt < 2:
                    time.sleep(2)
                else:
                    errors += 1

        day_count += 1
        if day_count % 30 == 0:
            print(f"  {day_count}/{total_days} Tage, {len(all_entries)} Eintraege...",
                  flush=True)

        current += timedelta(days=1)
        time.sleep(0.3)  # Be polite

    if not all_entries:
        print(f"  KEINE DATEN")
        return False

    # Remove duplicates
    seen = set()
    unique_entries = []
    for e in all_entries:
        key = (e['date'], e['time'], e['type'])
        if key not in seen:
            seen.add(key)
            unique_entries.append(e)

    unique_entries.sort(key=lambda x: x['date'] + ' ' + x['time'])

    data = {
        'name': name,
        'lat': station['lat'],
        'lon': station['lon'],
        'timezone': 'Europe/London',
        'entries': unique_entries,
    }

    with open(json_path, 'w') as f:
        json.dump(data, f)

    n_hw = sum(1 for e in unique_entries if e['type'] == 'HW')
    n_lw = sum(1 for e in unique_entries if e['type'] == 'LW')
    first = unique_entries[0]['date'] if unique_entries else '?'
    last = unique_entries[-1]['date'] if unique_entries else '?'
    print(f"  {len(unique_entries)} Eintraege ({n_hw} HW, {n_lw} LW, {first} - {last})")
    if errors:
        print(f"  {errors} Fehler")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download HW/LW Tide Data -- UK (tidetimes.co.uk)")
    print("=" * 70)
    print(f"Stationen: {len(STATIONS)}")
    print(f"Zeitraum: {START_DATE.date()} bis {END_DATE.date()}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1:2d}/{len(STATIONS)}] {station['name']} ({station['slug']})")
        if download_station(station):
            success += 1
        print()

    print(f"{'='*70}")
    print(f"Ergebnis: {success}/{len(STATIONS)} erfolgreich")


if __name__ == '__main__':
    main()
