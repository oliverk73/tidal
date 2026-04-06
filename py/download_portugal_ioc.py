#!/usr/bin/env python3
"""
Download sea level data from IOC Sea Level Monitoring for Portuguese stations.
Downloads in 30-day chunks, parses HTML table response, saves as CSV.
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta

OUTPUT_DIR = "/home/oliver/water_levels/Portugal_IOC"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Station definitions: (code, name, lat, lon, start_date, end_date)
STATIONS = [
    # Active stations
    ("casc", "Cascais",         38.6932, -9.4154,  "2020-01-01", "2026-04-07"),
    ("lgos", "Lagos",           37.0988, -8.6668,  "2020-01-01", "2026-04-07"),
    ("pdas", "Ponta_Delgada",   37.73,   -25.68,   "2020-01-01", "2026-04-07"),
    # Inactive stations
    ("setu", "Setubal",         38.49,   -8.93,    "2018-01-01", "2020-12-19"),
    ("albu", "Albufeira",       37.0825, -8.2604,  "2018-01-01", "2022-03-22"),
    ("arri", "Arrifana",        37.2956, -8.8694,  "2018-01-01", "2022-10-24"),
    ("sagr", "Sagres",          37.0104, -8.9282,  "2018-01-01", "2021-07-02"),
    ("posa", "Porto_Santo",     33.0597, -16.3149, "2018-01-01", "2021-11-10"),
]

BASE_URL = "http://www.ioc-sealevelmonitoring.org/bgraph.php"


def parse_ioc_html(html_text):
    """Parse IOC HTML table response for datetime and sea level values."""
    records = []
    # Find all table rows with data
    # The HTML contains <tr><td>datetime</td><td>value</td>...</tr>
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) >= 2:
            dt_str = cells[0].strip()
            val_str = cells[1].strip()
            # Skip header rows or empty values
            if not val_str or val_str == '' or 'date' in dt_str.lower():
                continue
            try:
                # Try parsing datetime
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                val = float(val_str)
                # Convert mm to meters
                val_m = val / 1000.0
                records.append((dt, val_m))
            except (ValueError, TypeError):
                continue
    return records


def download_station(code, name, start_str, end_str):
    """Download data for one station in 30-day chunks."""
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")

    all_records = []
    current_end = start + timedelta(days=30)

    chunk_num = 0
    total_chunks = int((end - start).days / 30) + 1

    while current_end <= end + timedelta(days=30):
        actual_end = min(current_end, end)
        chunk_num += 1

        endtime_str = actual_end.strftime("%Y-%m-%d")
        params = {
            "code": code,
            "output": "tab",
            "period": 30,
            "endtime": endtime_str,
        }

        try:
            resp = requests.get(BASE_URL, params=params, timeout=60)
            resp.raise_for_status()
            records = parse_ioc_html(resp.text)
            all_records.extend(records)
            print(f"  Chunk {chunk_num}/{total_chunks}: endtime={endtime_str} -> {len(records)} records")
        except Exception as e:
            print(f"  Chunk {chunk_num}/{total_chunks}: endtime={endtime_str} -> ERROR: {e}")

        time.sleep(1)

        current_end += timedelta(days=30)
        if actual_end >= end:
            break

    # Deduplicate and sort
    unique = {}
    for dt, val in all_records:
        unique[dt] = val
    sorted_records = sorted(unique.items())

    return sorted_records


def save_csv(records, code, name):
    """Save records as CSV."""
    filepath = os.path.join(OUTPUT_DIR, f"{code}_{name}.csv")
    with open(filepath, "w") as f:
        f.write("datetime_utc,level_m\n")
        for dt, val in records:
            f.write(f"{dt.strftime('%Y-%m-%d %H:%M:%S')},{val:.4f}\n")
    return filepath


def main():
    print(f"Downloading Portuguese IOC sea level data to {OUTPUT_DIR}")
    print(f"{'='*70}")

    for code, name, lat, lon, start, end in STATIONS:
        print(f"\n{'─'*70}")
        print(f"Station: {code} ({name}) | {lat}°N, {lon}°E | {start} to {end}")
        print(f"{'─'*70}")

        records = download_station(code, name, start, end)

        if records:
            filepath = save_csv(records, code, name)
            first_dt = records[0][0].strftime("%Y-%m-%d")
            last_dt = records[-1][0].strftime("%Y-%m-%d")
            print(f"  => {len(records)} data points | {first_dt} to {last_dt}")
            print(f"  => Saved to {filepath}")
        else:
            print(f"  => No data retrieved for {code}")

    print(f"\n{'='*70}")
    print("Done!")


if __name__ == "__main__":
    main()
