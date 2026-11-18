#!/usr/bin/env python3
"""
Download CHS annual HW/LW tide predictions for stations in the
Petitcodiac River / Chignecto Bay / Amherst Basin area.

Parses the HTML tables from tides.gc.ca and saves as JSON.
"""

import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUTPUT_DIR = Path("/home/oliver/water_levels/CHS_NB")

# Stations with regular HW/LW annual predictions (tables=25)
STATIONS_HWLW = {
    "00150": {"name": "Cape Enrage", "lat": 45.593584, "lon": -64.780225},
    "00160": {"name": "Grindstone Island", "lat": 45.72187, "lon": -64.621207},
    "00170": {"name": "Hopewell Cape", "lat": 45.860104, "lon": -64.57907},
    "00172": {"name": "Belliveau Village", "lat": 45.937102, "lon": -64.619739},
    "00173": {"name": "Dover", "lat": 45.992446, "lon": -64.686416},
    "00190": {"name": "Pecks Point", "lat": 45.741838, "lon": -64.479898},
    "00215": {"name": "Joggins", "lat": 45.660547, "lon": -64.488192},
    "00225": {"name": "Cape Capstan", "lat": 45.474004, "lon": -64.853811},
}

# Bore stations (different format - relative height 1-4 instead of meters)
STATIONS_BORE = {
    "00175": {"name": "Moncton", "lat": 46.087883, "lon": -64.771888},
    "00210": {"name": "Maccan", "lat": 45.724667, "lon": -64.259833},
    "00211": {"name": "River Hebert", "lat": 45.690167, "lon": -64.373833},
}

# Stations without annual tables (no predictions available)
STATIONS_NO_ANNUAL = {
    "00145": {"name": "Alma", "lat": 45.583333, "lon": -64.966667},
    "00155": {"name": "Harvey Bank", "lat": 45.733333, "lon": -64.7},
    "00174": {"name": "Dieppe (Irving Wharf)", "lat": 46.1, "lon": -64.766667},
    "00176": {"name": "Moncton (Causeway)", "lat": 46.066667, "lon": -64.816667},
    "00180": {"name": "Boundary Creek", "lat": None, "lon": None},
    "00185": {"name": "Memramcook", "lat": 45.978865, "lon": -64.55205},
    "00200": {"name": "Sackville", "lat": 45.882118, "lon": -64.340647},
    "00203": {"name": "Fort Lawrence", "lat": 45.8, "lon": -64.383333},
    "00206": {"name": "Amherst Basin", "lat": 45.833333, "lon": -64.283333},
    "00226": {"name": "Apple River", "lat": 45.466667, "lon": -64.783333},
}


def fetch_url(url):
    """Fetch URL content with retries."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; TideBot/1.0)"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            if attempt < 2:
                print(f"  Retry {attempt+1} for {url}: {e}")
                time.sleep(2)
            else:
                raise


def parse_annual_hwlw(html, year):
    """Parse CHS annual HW/LW prediction tables.

    Tables have structure:
    - One table per half-month (24 tables for 12 months, 2 halves each)
    - Each row: Day | Times (br-separated) | Heights (br-separated)
    - Times are HHMM format, heights in metres
    - HW/LW alternates: first entry of year determines pattern by height
    """
    entries = []

    # Find all tables with their month info
    # Table IDs like: day-table-2025-01, day-table-2025-02, etc.
    table_pattern = re.compile(
        r'id="day-table-(\d{4})-(\d{2})".*?<tbody>(.*?)</tbody>',
        re.DOTALL
    )

    row_pattern = re.compile(
        r'<td><strong class="day-number">(\d+)</strong>.*?</td>\s*'
        r'<td>(.*?)</td>\s*'
        r'<td>(.*?)</td>',
        re.DOTALL
    )

    for table_match in table_pattern.finditer(html):
        table_year = int(table_match.group(1))
        month = int(table_match.group(2))
        tbody = table_match.group(3)

        for row_match in row_pattern.finditer(tbody):
            day = int(row_match.group(1))
            times_raw = row_match.group(2)
            heights_raw = row_match.group(3)

            # Extract times and heights (split by <br> or <br/>)
            times = [t.strip() for t in re.split(r'<br\s*/?>', times_raw) if t.strip()]
            heights = [h.strip() for h in re.split(r'<br\s*/?>', heights_raw) if h.strip()]

            if len(times) != len(heights):
                print(f"  WARNING: Mismatch day {day}/{month}: {len(times)} times vs {len(heights)} heights")
                continue

            for t, h in zip(times, heights):
                # Parse time: HHMM -> HH:MM
                t = t.strip()
                if len(t) == 4 and t.isdigit():
                    time_str = f"{t[:2]}:{t[2:]}"
                elif len(t) == 3 and t.isdigit():
                    time_str = f"0{t[0]}:{t[1:]}"
                else:
                    print(f"  WARNING: Bad time format: '{t}'")
                    continue

                try:
                    height = float(h)
                except ValueError:
                    print(f"  WARNING: Bad height: '{h}'")
                    continue

                date_str = f"{table_year}-{month:02d}-{day:02d}"
                entries.append({
                    "date": date_str,
                    "time": time_str,
                    "height_m": height,
                })

    return entries


def classify_hwlw(entries):
    """Classify entries as HW or LW based on height threshold.

    Bay of Fundy stations have extreme tidal range with a clear gap
    between HW and LW heights. Using the mean height as threshold
    is robust (no dependence on strict alternation which breaks
    when a day has 3 instead of 4 entries).
    """
    if len(entries) < 2:
        return entries

    # Sort by date+time
    entries.sort(key=lambda e: e["date"] + e["time"])

    # Use mean height as threshold
    heights = [e["height_m"] for e in entries]
    mean_h = sum(heights) / len(heights)

    for e in entries:
        e["type"] = "HW" if e["height_m"] > mean_h else "LW"

    hw_heights = [e["height_m"] for e in entries if e["type"] == "HW"]
    lw_heights = [e["height_m"] for e in entries if e["type"] == "LW"]
    print(f"    HW: n={len(hw_heights)}, avg={sum(hw_heights)/len(hw_heights):.2f}m")
    print(f"    LW: n={len(lw_heights)}, avg={sum(lw_heights)/len(lw_heights):.2f}m")

    return entries


def parse_annual_bore(html, year):
    """Parse CHS annual bore prediction tables.

    Same table structure but heights are relative (1-4 scale).
    """
    entries = []

    table_pattern = re.compile(
        r'id="day-table-(\d{4})-(\d{2})".*?<tbody>(.*?)</tbody>',
        re.DOTALL
    )

    row_pattern = re.compile(
        r'<td><strong class="day-number">(\d+)</strong>.*?</td>\s*'
        r'<td>(.*?)</td>\s*'
        r'<td>(.*?)</td>',
        re.DOTALL
    )

    for table_match in table_pattern.finditer(html):
        table_year = int(table_match.group(1))
        month = int(table_match.group(2))
        tbody = table_match.group(3)

        for row_match in row_pattern.finditer(tbody):
            day = int(row_match.group(1))
            times_raw = row_match.group(2)
            heights_raw = row_match.group(3)

            times = [t.strip() for t in re.split(r'<br\s*/?>', times_raw) if t.strip()]
            heights = [h.strip() for h in re.split(r'<br\s*/?>', heights_raw) if h.strip()]

            if len(times) != len(heights):
                continue

            for t, h in zip(times, heights):
                t = t.strip()
                if len(t) == 4 and t.isdigit():
                    time_str = f"{t[:2]}:{t[2:]}"
                elif len(t) == 3 and t.isdigit():
                    time_str = f"0{t[0]}:{t[1:]}"
                else:
                    continue

                try:
                    rel_height = float(h)
                except ValueError:
                    continue

                date_str = f"{table_year}-{month:02d}-{day:02d}"
                entries.append({
                    "date": date_str,
                    "time": time_str,
                    "relative_height": rel_height,
                    "type": "BORE",
                })

    return entries


def download_station(station_id, info, is_bore=False):
    """Download annual predictions for a station.

    Note: CHS ignores the year parameter and always shows predictions
    for the current prediction year (2026 as of 2026-04). We download
    once and use the year from the table IDs.
    """
    name = info["name"]
    safe_name = name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("'", "")
    filename = f"{safe_name}_{station_id}.json"
    outpath = OUTPUT_DIR / filename

    all_entries = []

    url = f"https://tides.gc.ca/en/stations/{station_id}/predictions/annual?year=2026"
    print(f"  Downloading {name} ({station_id})...")

    try:
        html = fetch_url(url)
    except Exception as e:
        print(f"  ERROR: Could not fetch {url}: {e}")
        return None

    if is_bore:
        entries = parse_annual_bore(html, 2026)
    else:
        entries = parse_annual_hwlw(html, 2026)

    print(f"    Parsed {len(entries)} entries")
    all_entries.extend(entries)

    if not all_entries:
        print(f"  No entries for {name} - skipping")
        return None

    # Classify HW/LW for non-bore stations
    if not is_bore:
        all_entries = classify_hwlw(all_entries)

    # Sort entries
    all_entries.sort(key=lambda e: e["date"] + e["time"])

    # Remove duplicates (tables may overlap at half-month boundary)
    seen = set()
    unique_entries = []
    for e in all_entries:
        key = (e["date"], e["time"])
        if key not in seen:
            seen.add(key)
            unique_entries.append(e)

    result = {
        "name": name,
        "station_id": station_id,
        "lat": info["lat"],
        "lon": info["lon"],
        "timezone": "America/Moncton",
        "prediction_type": "bore" if is_bore else "hwlw",
        "entries": unique_entries,
    }

    with open(outpath, "w") as f:
        json.dump(result, f, indent=2)

    print(f"  Saved {len(unique_entries)} entries to {outpath}")
    return outpath


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Downloading HW/LW stations ===")
    for sid, info in sorted(STATIONS_HWLW.items()):
        download_station(sid, info, is_bore=False)
        time.sleep(1)  # Be polite

    print("\n=== Downloading Bore stations ===")
    for sid, info in sorted(STATIONS_BORE.items()):
        download_station(sid, info, is_bore=True)
        time.sleep(1)

    print("\n=== Stations without annual predictions (skipped) ===")
    for sid, info in sorted(STATIONS_NO_ANNUAL.items()):
        print(f"  {sid} {info['name']} - no annual tables")

    print("\nDone!")


if __name__ == "__main__":
    main()
