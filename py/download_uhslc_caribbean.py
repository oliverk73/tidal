#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC for Caribbean stations.
- Fort-de-France (Martinique) #271 (Fast Delivery)
- Pointe-à-Pitre (Guadeloupe) #272 (Research Quality)
"""

import os
import requests
import csv
from datetime import datetime
from io import StringIO

STATIONS = [
    {
        "name": "Fort-de-France",
        "id": 271,
        "url": "https://uhslc.soest.hawaii.edu/data/csv/fast/hourly/h271.csv",
        "outdir": "/home/oliver/water_levels/Martinique_UHSLC",
        "outfile": "h271_fort_de_france.csv",
    },
    {
        "name": "Pointe-à-Pitre",
        "id": 272,
        "url": "https://uhslc.soest.hawaii.edu/data/csv/rqds/atlantic/hourly/h272a.csv",
        "outdir": "/home/oliver/water_levels/Guadeloupe_UHSLC",
        "outfile": "h272_pointe_a_pitre.csv",
    },
]

MISSING = -32767

for st in STATIONS:
    print(f"\n{'='*60}")
    print(f"Station: {st['name']} (UHSLC #{st['id']})")
    print(f"URL: {st['url']}")
    print(f"{'='*60}")

    # Download
    resp = requests.get(st["url"], timeout=60)
    if resp.status_code != 200:
        print(f"  ERROR: HTTP {resp.status_code}")
        continue
    print(f"  Downloaded {len(resp.content)} bytes")

    # Parse CSV
    reader = csv.reader(StringIO(resp.text))
    records = []
    for row in reader:
        if not row or len(row) < 5:
            continue
        try:
            year = int(row[0].strip())
            month = int(row[1].strip())
            day = int(row[2].strip())
            hour = int(row[3].strip())
            level_mm = int(row[4].strip())
        except (ValueError, IndexError):
            continue

        if level_mm == MISSING:
            continue

        dt = datetime(year, month, day, hour)
        records.append((dt, level_mm))

    if not records:
        print("  No valid data found!")
        continue

    records.sort(key=lambda x: x[0])

    # Stats
    n = len(records)
    dt_min = records[0][0]
    dt_max = records[-1][0]
    mean_mm = sum(r[1] for r in records) / n
    mean_m = mean_mm / 1000.0

    print(f"  Valid data points: {n}")
    print(f"  Date range: {dt_min:%Y-%m-%d %H:%M} to {dt_max:%Y-%m-%d %H:%M} UTC")
    print(f"  Mean level: {mean_mm:.1f} mm ({mean_m:.3f} m)")

    # Save
    os.makedirs(st["outdir"], exist_ok=True)
    outpath = os.path.join(st["outdir"], st["outfile"])
    with open(outpath, "w", newline="") as f:
        f.write("datetime_utc,level_mm\n")
        for dt, lev in records:
            f.write(f"{dt:%Y-%m-%d %H:%M},{lev}\n")
    print(f"  Saved to: {outpath}")

print("\nDone.")
