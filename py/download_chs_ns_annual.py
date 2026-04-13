#!/usr/bin/env python3
"""
Download HW/LW annual tide predictions from Canadian Hydrographic Service (CHS)
for stations in the Cobequid Bay / Minas Basin / Bay of Fundy area (Nova Scotia).

Parses HTML tables from https://tides.gc.ca/en/stations/XXXXX/predictions/annual
and saves as JSON.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

OUTPUT_DIR = "/home/oliver/water_levels/CHS_NS"

# Stations to download: (id, name, lat, lon) - from CHS website
# Only stations WITH annual predictions available
STATIONS = [
    ("00225", "Cape Capstan", 45.474004, -64.853811),
    ("00235", "West Advocate", 45.345678, -64.816617),
    ("00240", "Cape d'Or", 45.290438, -64.774936),
    ("00242", "Spencers Island", 45.35476, -64.710035),
    ("00245", "Port Greville", 45.404321, -64.541522),
    ("00247", "Diligent River", 45.390396, -64.454776),
    ("00250", "Cape Sharp", 45.364449, -64.391893),
    ("00290", "Cape Blomidon", 45.30484, -64.349067),
    ("00300", "Scots Bay", 45.315444, -64.440747),
    ("00305", "Baxters Harbour", 45.230788, -64.514883),
    ("00312", "Ile Haute", 45.253894, -64.990928),
]

# Bore-only stations (no HW/LW height data, only tidal bore arrival times):
# 00265 Truro, 00267 Maitland, 00281 Tidal View Farm
# Stations without annual predictions:
# 00280 Windsor, 00285 Horton Bluff, 00287 Port Williams, 00288 Pereau, 00289 Blomidon

# Year for predictions
YEAR = 2026

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

import calendar


def fetch_url(url, retries=3):
    """Fetch URL with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; TidePredictionDownloader/1.0)'
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode('utf-8')
        except Exception as e:
            if attempt < retries - 1:
                print(f"  Retry {attempt+1} for {url}: {e}")
                time.sleep(2)
            else:
                raise


def get_station_coords(station_id):
    """Fetch coordinates from station main page."""
    url = f"https://tides.gc.ca/en/stations/{station_id}"
    html = fetch_url(url)

    # Look for latitude (typically 44-46 for Nova Scotia)
    lat_match = re.search(r'(4[4-6]\.\d{2,8})', html)
    # Look for longitude (typically -63 to -65)
    lon_match = re.search(r'(-6[3-5]\.\d{2,8})', html)

    lat = float(lat_match.group(1)) if lat_match else None
    lon = float(lon_match.group(1)) if lon_match else None
    return lat, lon


def parse_annual_predictions(html, year):
    """
    Parse CHS annual predictions HTML.

    Structure:
    - Months identified by data-month="01" etc.
    - 2 tables per month (days 1-15, days 16-end)
    - Each row: <td><strong class="day-number">1</strong><br>Thu</td>
                <td>0424<br>1034<br>1702<br>2308</td>
                <td>1.933<br>11.216<br>1.358<br>10.657</td>
    """
    entries = []

    # Split by month containers
    month_pattern = r'data-month="(\d{2})">(.*?)(?=data-month="|$)'
    month_sections = re.findall(month_pattern, html, re.DOTALL)

    if not month_sections:
        print("  WARNING: No month sections found!")
        return entries

    for month_str, section_html in month_sections:
        month = int(month_str)

        # Find all table rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', section_html, re.DOTALL)

        for row in rows:
            # Extract cells
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cells) < 3:
                continue

            # Day number
            day_match = re.search(r'class="day-number">(\d+)<', cells[0])
            if not day_match:
                continue
            day = int(day_match.group(1))

            # Times (HHMM format, separated by <br>)
            times_raw = re.findall(r'(\d{4})', cells[1])

            # Heights (separated by <br>)
            heights_raw = re.findall(r'([\d.]+)', cells[2])

            if len(times_raw) != len(heights_raw):
                print(f"  WARNING: Mismatch day {day} month {month}: {len(times_raw)} times vs {len(heights_raw)} heights")
                continue

            for time_str, height_str in zip(times_raw, heights_raw):
                height = float(height_str)
                hh = time_str[:2]
                mm = time_str[2:]
                time_formatted = f"{hh}:{mm}"

                # Determine HW/LW by comparing with neighbors
                # We'll do this after collecting all entries for the day
                try:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    # Validate date
                    datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    continue

                entries.append({
                    "date": date_str,
                    "time": time_formatted,
                    "height_m": height,
                })

    # Determine HW/LW: alternating pattern, classify by comparing adjacent values
    if entries:
        for i, entry in enumerate(entries):
            # Compare with previous and next
            prev_h = entries[i-1]["height_m"] if i > 0 else None
            next_h = entries[i+1]["height_m"] if i < len(entries)-1 else None

            is_high = True
            if prev_h is not None and next_h is not None:
                is_high = entry["height_m"] > prev_h and entry["height_m"] > next_h
            elif prev_h is not None:
                is_high = entry["height_m"] > prev_h
            elif next_h is not None:
                is_high = entry["height_m"] > next_h

            entry["type"] = "HW" if is_high else "LW"

    return entries


def download_station(station_id, name, lat, lon):
    """Download and parse annual predictions for one station."""
    print(f"\nDownloading {name} ({station_id})...")

    url = f"https://tides.gc.ca/en/stations/{station_id}/predictions/annual"

    try:
        html = fetch_url(url)
    except Exception as e:
        print(f"  ERROR fetching {url}: {e}")
        return None

    # Check if it's a bore prediction page (Truro) or no data
    if "Relative Height" in html or "bore" in html.lower():
        print(f"  SKIP: {name} appears to be a bore prediction station (no HW/LW data)")
        return None

    if "Metres" not in html:
        print(f"  SKIP: {name} has no height data in metres")
        return None

    entries = parse_annual_predictions(html, YEAR)

    if not entries:
        print(f"  SKIP: No entries parsed for {name}")
        return None

    # Verify coordinates from website if needed
    if lat is None or lon is None:
        print(f"  Fetching coordinates for {name}...")
        lat_web, lon_web = get_station_coords(station_id)
        if lat_web: lat = lat_web
        if lon_web: lon = lon_web

    # Count HW/LW
    hw_count = sum(1 for e in entries if e["type"] == "HW")
    lw_count = sum(1 for e in entries if e["type"] == "LW")
    print(f"  Parsed {len(entries)} entries: {hw_count} HW, {lw_count} LW")
    print(f"  Height range: {min(e['height_m'] for e in entries):.1f} - {max(e['height_m'] for e in entries):.1f} m")

    result = {
        "name": name,
        "station_id": station_id,
        "lat": lat,
        "lon": lon,
        "timezone": "America/Halifax",
        "source": "CHS",
        "source_url": url,
        "year": YEAR,
        "time_standard": "AST (UTC-4)",
        "entries": entries
    }

    return result


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []

    for station_id, name, lat, lon in STATIONS:
        result = download_station(station_id, name, lat, lon)
        if result:
            # Save individual station file
            safe_name = name.replace("'", "").replace(" ", "_")
            filename = f"CHS_{station_id}_{safe_name}.json"
            filepath = os.path.join(OUTPUT_DIR, filename)

            with open(filepath, 'w') as f:
                json.dump(result, f, indent=2)

            print(f"  Saved: {filepath}")
            results.append(result)

        time.sleep(1)  # Be polite

    print(f"\n{'='*60}")
    print(f"Downloaded {len(results)} stations to {OUTPUT_DIR}")
    for r in results:
        print(f"  {r['station_id']}: {r['name']} ({len(r['entries'])} entries, "
              f"{r['lat']:.4f}, {r['lon']:.4f})")


if __name__ == "__main__":
    main()
