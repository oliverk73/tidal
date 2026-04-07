#!/usr/bin/env python3
"""
Download sea level data from IOC Sea Level Monitoring for Moroccan stations.
Stations: El Jadida (elja1) and Saidia Marina (said)
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta

OUTPUT_DIR = "/home/oliver/water_levels/Morocco_IOC"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "http://www.ioc-sealevelmonitoring.org/bgraph.php"

STATIONS = [
    {
        "code": "elja1",
        "name": "El Jadida",
        "filename": "elja1_el_jadida.csv",
        "start": "2023-01-01",
        "end": "2026-03-01",
    },
    {
        "code": "said",
        "name": "Saidia Marina",
        "filename": "said_saidia.csv",
        "start": "2016-01-01",
        "end": "2022-05-01",
    },
]

# Pattern to match table rows with datetime and numeric value
# Typical: <td>2024-01-15 12:30:00</td><td...>1.234</td>
ROW_PATTERN = re.compile(
    r'<td[^>]*>\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*</td>\s*<td[^>]*>\s*([-\d.]+)\s*</td>',
    re.IGNORECASE
)


def fetch_chunk(station_code, endtime_str, retry=True):
    """Fetch 30-day chunk ending at endtime_str (YYYY-MM-DD)."""
    params = {
        "code": station_code,
        "output": "tab",
        "period": 30,
        "endtime": endtime_str,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        if retry:
            print(f"  Retry after error: {e}")
            time.sleep(2)
            return fetch_chunk(station_code, endtime_str, retry=False)
        else:
            print(f"  FAILED: {e}")
            return None


def parse_data(html):
    """Extract (datetime_str, value) tuples from HTML response."""
    rows = []
    for match in ROW_PATTERN.finditer(html):
        dt_str = match.group(1).strip()
        val_str = match.group(2).strip()
        # Skip invalid values
        if not val_str or val_str == "-999" or val_str.lower() == "nan":
            continue
        try:
            val = float(val_str)
        except ValueError:
            continue
        if val == -999.0:
            continue
        rows.append((dt_str, val))
    return rows


def download_station(station):
    code = station["code"]
    name = station["name"]
    filename = station["filename"]
    start_date = datetime.strptime(station["start"], "%Y-%m-%d")
    end_date = datetime.strptime(station["end"], "%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"Station: {name} ({code})")
    print(f"Period: {station['start']} to {station['end']}")
    print(f"{'='*60}")

    all_data = {}  # datetime_str -> value (dict for dedup)
    current_end = end_date
    chunk_num = 0

    while current_end > start_date:
        chunk_num += 1
        endtime_str = current_end.strftime("%Y-%m-%d")
        chunk_start = current_end - timedelta(days=30)
        print(f"  Chunk {chunk_num}: {chunk_start.strftime('%Y-%m-%d')} to {endtime_str}")

        html = fetch_chunk(code, endtime_str)
        if html:
            rows = parse_data(html)
            for dt_str, val in rows:
                all_data[dt_str] = val
            print(f"    -> {len(rows)} rows parsed, {len(all_data)} total unique")
        else:
            print(f"    -> No data returned")

        current_end -= timedelta(days=30)
        time.sleep(1)

    # Sort by datetime and write CSV
    sorted_data = sorted(all_data.items(), key=lambda x: x[0])

    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        f.write("datetime_utc,level_m\n")
        for dt_str, val in sorted_data:
            f.write(f"{dt_str},{val:.4f}\n")

    print(f"\nResult for {name}:")
    print(f"  Total data points: {len(sorted_data)}")
    if sorted_data:
        print(f"  Date range: {sorted_data[0][0]} to {sorted_data[-1][0]}")
    else:
        print(f"  No data found!")
    print(f"  Saved to: {filepath}")

    return len(sorted_data), sorted_data


if __name__ == "__main__":
    for station in STATIONS:
        download_station(station)
    print("\nDone.")
