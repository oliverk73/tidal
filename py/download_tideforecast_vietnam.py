#!/usr/bin/env python3
"""
Download HW/LW tide predictions from tide-forecast.com for Vietnamese stations.
Extracts HW/LW times and heights from monthly HTML pages.
Downloads 2 years (2025-2026) of data per station.

Times are in local time (ICT = UTC+7).
"""

import os
import re
import json
import time
import requests
from datetime import datetime

OUTPUT_DIR = '/home/oliver/water_levels/Vietnam_tideforecast'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
}

# Vietnamese stations from tide-forecast.com (only new ones not in other sources)
STATIONS = [
    {'slug': 'Can-Gio', 'name': 'Can Gio'},
    {'slug': 'Dong-Hoi', 'name': 'Dong Hoi'},
    {'slug': 'Duong-GJong', 'name': 'Duong Dong'},
    {'slug': 'Ha-Tien', 'name': 'Ha Tien'},
    {'slug': 'Hoi-An', 'name': 'Hoi An'},
    {'slug': 'Hon-Nieu-Vietnam', 'name': 'Hon Nieu'},
    {'slug': 'Nhatrang', 'name': 'Nha Trang'},
    {'slug': 'Phan-Rang-Thap-Cham', 'name': 'Phan Rang'},
    {'slug': 'Phan-Thiet', 'name': 'Phan Thiet'},
    {'slug': 'Song-Cau', 'name': 'Song Cau'},
    {'slug': 'Tuy-Hoa', 'name': 'Tuy Hoa'},
]

MONTHS = []
for year in [2025, 2026]:
    for month in range(1, 13):
        MONTHS.append(f'{year}-{month:02d}')


def extract_coordinates(html):
    """Extract station coordinates from HTML."""
    # Look for lat/lng in the page
    lat_match = re.search(r'(\d+\.\d+)°\s*N', html)
    lon_match = re.search(r'(\d+\.\d+)°\s*E', html)
    lat = float(lat_match.group(1)) if lat_match else None
    lon = float(lon_match.group(1)) if lon_match else None
    return lat, lon


def parse_hwlw(html, year, month):
    """Parse HW/LW data from tide-forecast.com monthly page."""
    entries = []

    # Pattern: (High|Low) Tide ... time ... (day info) ... height m
    # Example: High Tide</td><td><b> 1:28 PM</b><span ...>(Fri 10 April)</span></td>...<b ...>1.48 m
    pattern = (
        r'(High|Low)\s+Tide</td>\s*<td><b>\s*([\d:]+\s*[AP]M)\s*</b>'
        r'<span[^>]*>\(.*?(\d{1,2})\s+(\w+)\)</span></td>'
        r'.*?<b[^>]*>([\d.]+)\s*m'
    )

    for m in re.finditer(pattern, html, re.DOTALL):
        tide_type = m.group(1)  # High or Low
        time_str = m.group(2).strip()
        day = int(m.group(3))
        month_name = m.group(4)

        height_m = float(m.group(5))

        # Parse time (12h format)
        try:
            t = datetime.strptime(time_str, '%I:%M %p')
            hour, minute = t.hour, t.minute
        except ValueError:
            try:
                t = datetime.strptime(time_str, '%I:%M%p')
                hour, minute = t.hour, t.minute
            except ValueError:
                continue

        # Determine the actual month from month_name (pages can span months)
        month_map = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4,
            'May': 5, 'June': 6, 'July': 7, 'August': 8,
            'September': 9, 'October': 10, 'November': 11, 'December': 12,
        }
        actual_month = month_map.get(month_name, month)

        # Determine year (handle Dec->Jan crossover)
        actual_year = year
        if month == 12 and actual_month == 1:
            actual_year = year + 1
        elif month == 1 and actual_month == 12:
            actual_year = year - 1

        try:
            date_str = f'{actual_year}-{actual_month:02d}-{day:02d}'
            time_str_out = f'{hour:02d}:{minute:02d}'
            entries.append({
                'date': date_str,
                'time': time_str_out,
                'height_m': height_m,
                'type': 'HW' if tide_type == 'High' else 'LW',
            })
        except ValueError:
            continue

    return entries


def download_station(station):
    """Download all monthly HW/LW data for one station."""
    slug = station['slug']
    name = station['name']
    safe_name = name.replace(' ', '_')
    json_path = os.path.join(OUTPUT_DIR, f'{safe_name}.json')

    if os.path.exists(json_path) and os.path.getsize(json_path) > 1000:
        with open(json_path) as f:
            data = json.load(f)
        print(f"  schon vorhanden ({len(data.get('entries', []))} Eintraege)")
        return True

    all_entries = []
    lat, lon = None, None

    for ym in MONTHS:
        year, month = int(ym[:4]), int(ym[5:7])
        url = f'https://www.tide-forecast.com/locations/{slug}/tides/{ym}'

        for attempt in range(3):
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code == 200:
                    if lat is None:
                        lat, lon = extract_coordinates(r.text)
                    entries = parse_hwlw(r.text, year, month)
                    all_entries.extend(entries)
                    break
                else:
                    if attempt < 2:
                        time.sleep(3)
            except Exception:
                if attempt < 2:
                    time.sleep(3)

        time.sleep(0.5)

    if not all_entries:
        print(f"  KEINE DATEN")
        return False

    # Remove duplicates (pages overlap at month boundaries)
    seen = set()
    unique_entries = []
    for e in all_entries:
        key = (e['date'], e['time'], e['type'])
        if key not in seen:
            seen.add(key)
            unique_entries.append(e)

    # Sort by date+time
    unique_entries.sort(key=lambda x: x['date'] + ' ' + x['time'])

    data = {
        'name': name,
        'lat': lat,
        'lon': lon,
        'entries': unique_entries,
    }

    with open(json_path, 'w') as f:
        json.dump(data, f)

    n_hw = sum(1 for e in unique_entries if e['type'] == 'HW')
    n_lw = sum(1 for e in unique_entries if e['type'] == 'LW')
    first = unique_entries[0]['date'] if unique_entries else '?'
    last = unique_entries[-1]['date'] if unique_entries else '?'
    print(f"  {len(unique_entries)} Eintraege ({n_hw} HW, {n_lw} LW, {first} - {last})")
    if lat:
        print(f"  Koordinaten: {lat:.4f}N, {lon:.4f}E")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download HW/LW Tide Data -- Vietnam (tide-forecast.com)")
    print("=" * 70)
    print(f"Stationen: {len(STATIONS)}")
    print(f"Zeitraum: {MONTHS[0]} bis {MONTHS[-1]}")
    print()

    success = 0
    for i, station in enumerate(STATIONS):
        print(f"[{i+1:2d}/{len(STATIONS)}] {station['name']}")
        if download_station(station):
            success += 1
        print()

    print(f"{'='*70}")
    print(f"Ergebnis: {success}/{len(STATIONS)} erfolgreich")


if __name__ == '__main__':
    main()
