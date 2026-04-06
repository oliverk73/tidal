#!/usr/bin/env python3
"""Download hourly sea level data from UHSLC for all Portuguese stations."""

import os
import requests
import csv
from datetime import datetime

OUTPUT_DIR = "/home/oliver/water_levels/Portugal_UHSLC"
os.makedirs(OUTPUT_DIR, exist_ok=True)

STATIONS = [
    # Fast Delivery
    {"id": "h209", "name": "cascais", "url": "https://uhslc.soest.hawaii.edu/data/csv/fast/hourly/h209.csv"},
    {"id": "h210", "name": "flores_santa_cruz", "url": "https://uhslc.soest.hawaii.edu/data/csv/fast/hourly/h210.csv"},
    {"id": "h211", "name": "ponta_delgada", "url": "https://uhslc.soest.hawaii.edu/data/csv/fast/hourly/h211.csv"},
    {"id": "h218", "name": "funchal", "url": "https://uhslc.soest.hawaii.edu/data/csv/fast/hourly/h218.csv"},
    # Research Quality
    {"id": "h212a", "name": "horta", "url": "https://uhslc.soest.hawaii.edu/data/csv/rqds/atlantic/hourly/h212a.csv"},
    {"id": "h213a", "name": "flores_lajes", "url": "https://uhslc.soest.hawaii.edu/data/csv/rqds/atlantic/hourly/h213a.csv"},
    {"id": "h215a", "name": "angra_do_heroismo", "url": "https://uhslc.soest.hawaii.edu/data/csv/rqds/atlantic/hourly/h215a.csv"},
    {"id": "h723a", "name": "lagos", "url": "https://uhslc.soest.hawaii.edu/data/csv/rqds/atlantic/hourly/h723a.csv"},
]

MISSING = -32767

for st in STATIONS:
    print(f"\n{'='*60}")
    print(f"Downloading {st['id']} — {st['name']}")
    print(f"  URL: {st['url']}")

    try:
        resp = requests.get(st["url"], timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ERROR downloading: {e}")
        continue

    lines = resp.text.strip().splitlines()
    print(f"  Raw lines: {len(lines)}")
    if len(lines) < 3:
        print("  ERROR: Too few lines in file")
        continue

    # Print first few lines for debugging
    for i, line in enumerate(lines[:5]):
        print(f"  Line {i}: {line[:120]}")

    # Parse CSV
    records = []
    reader = csv.reader(lines)
    header = next(reader)  # header line

    # Detect format from header
    header_lower = [h.strip().lower() for h in header]
    print(f"  Header: {header_lower}")

    # Check if there's a units line (second line not starting with digit)
    # Peek at second line
    second_line = lines[1].strip()
    skip_units = False
    if second_line and not second_line[0].isdigit() and not second_line[0] == '-':
        skip_units = True
        next(reader)  # skip units line
        print(f"  Skipping units line: {second_line[:80]}")

    for row in reader:
        if not row or len(row) < 2:
            continue
        try:
            # Try format 1: ISO datetime string + sea_level
            if 'time' in header_lower or '-' in row[0]:
                dt = datetime.fromisoformat(row[0].strip())
                level = int(float(row[1].strip()))
            else:
                # Format 2: year, month, day, hour, level
                year = int(row[0].strip())
                month = int(row[1].strip())
                day = int(row[2].strip())
                hour = int(row[3].strip())
                level = int(float(row[4].strip()))
                dt = datetime(year, month, day, hour)

            if level != MISSING:
                records.append((dt, level))
        except Exception as e:
            # silently skip malformed rows
            continue

    if not records:
        print("  WARNING: No valid records parsed!")
        continue

    # Sort by datetime
    records.sort(key=lambda x: x[0])

    # Save
    outfile = os.path.join(OUTPUT_DIR, f"{st['id']}_{st['name']}.csv")
    with open(outfile, 'w') as f:
        f.write("datetime_utc,level_mm\n")
        for dt, level in records:
            f.write(f"{dt.strftime('%Y-%m-%d %H:%M')},{level}\n")

    # Report
    dt_min = records[0][0]
    dt_max = records[-1][0]
    levels = [r[1] for r in records]
    mean_level = sum(levels) / len(levels)

    print(f"  Valid data points: {len(records)}")
    print(f"  Date range: {dt_min.strftime('%Y-%m-%d')} to {dt_max.strftime('%Y-%m-%d')}")
    print(f"  Mean level: {mean_level:.1f} mm")
    print(f"  Saved to: {outfile}")

print(f"\n{'='*60}")
print("Done!")
