#!/usr/bin/env python3
"""
Download sea level data from IOC Sea Level Monitoring for Cayman Islands stations.
Iterates backwards in 30-day chunks, parses HTML table responses.
Resamples minute data to 6-minute intervals to keep file sizes manageable.
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta
from collections import defaultdict

OUTPUT_DIR = "/home/oliver/water_levels/Cayman_IOC"
os.makedirs(OUTPUT_DIR, exist_ok=True)

STATIONS = [
    {"code": "cagt", "name": "George_Town_Grand_Cayman", "lat": 19.295, "lon": -81.383, "end": "2024-01-15"},
    {"code": "cagb", "name": "Gun_Bay_Grand_Cayman",    "lat": 19.312, "lon": -81.089, "end": "2024-07-15"},
    {"code": "cacb", "name": "Cayman_Brac",              "lat": 19.743, "lon": -79.770, "end": "2023-05-15"},
    {"code": "calc", "name": "Little_Cayman",             "lat": 19.668, "lon": -80.104, "end": "2023-02-15"},
]

START_YEAR = 2018

BASE_URL = "http://www.ioc-sealevelmonitoring.org/bgraph.php"

# Regex to parse rows: <tr><td>DATETIME</td><td>VALUE</td></tr>
# or with multiple columns: <tr><td>DATETIME</td><td>VAL1</td><td>VAL2</td></tr>
ROW_RE = re.compile(
    r'<tr>\s*<td>([\d]{4}-[\d]{2}-[\d]{2}\s+[\d]{2}:[\d]{2}:[\d]{2})</td>'
    r'((?:\s*<td>[^<]*</td>)+)\s*</tr>',
    re.IGNORECASE
)
TD_RE = re.compile(r'<td>([^<]*)</td>', re.IGNORECASE)
HEADER_RE = re.compile(r"<td\s+class=field>(.*?)</td>", re.IGNORECASE)


def fetch_chunk(code, end_date_str):
    """Fetch one 30-day chunk. Returns raw HTML text or None."""
    params = {
        "code": code,
        "output": "tab",
        "period": 30,
        "endtime": end_date_str,
    }
    for attempt in range(2):
        try:
            r = requests.get(BASE_URL, params=params, timeout=60)
            if r.status_code == 200:
                return r.text
            print(f"  HTTP {r.status_code} for {end_date_str}")
        except Exception as e:
            print(f"  Error for {end_date_str}: {e}")
        if attempt == 0:
            time.sleep(2)
    return None


def detect_preferred_column(html):
    """Detect which column index to prefer (rad > aqt > prs > first)."""
    headers = HEADER_RE.findall(html)
    if not headers:
        return 0

    # Prefer rad, then aqt, then prs, then first
    priority = ['rad', 'aqt', 'prs', 'enc', 'flt', 'bwl']
    for pref in priority:
        for i, h in enumerate(headers):
            if pref in h.lower():
                return i
    return 0


def parse_html_table(html, col_idx=0):
    """
    Parse IOC HTML table. Returns list of (datetime_str, value_float).
    col_idx: which value column to use (0-based among value columns).
    """
    rows = []
    for m in ROW_RE.finditer(html):
        dt_str = m.group(1)
        value_cells = TD_RE.findall(m.group(2))

        if not value_cells:
            continue

        idx = min(col_idx, len(value_cells) - 1)
        val_str = value_cells[idx].strip()

        if not val_str or val_str == '-':
            continue
        try:
            v = float(val_str)
        except ValueError:
            continue

        if v == -999 or v == -9999:
            continue

        rows.append((dt_str, v))
    return rows


def resample_6min(data_dict):
    """
    Resample minute data to 6-minute intervals.
    Groups by 6-min bins and averages.
    """
    bins = defaultdict(list)
    for dt_str, val in sorted(data_dict.items()):
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        # Round down to 6-min bin
        minute_bin = (dt.minute // 6) * 6
        bin_dt = dt.replace(minute=minute_bin, second=0)
        bins[bin_dt].append(val)

    result = []
    for bin_dt in sorted(bins):
        vals = bins[bin_dt]
        avg = sum(vals) / len(vals)
        result.append((bin_dt.strftime("%Y-%m-%d %H:%M:%S"), round(avg, 4)))
    return result


def download_station(station):
    code = station["code"]
    name = station["name"]
    end_str = station["end"]

    print(f"\n{'='*60}")
    print(f"Station: {code} — {name}")
    print(f"Fetching backwards from {end_str} to {START_YEAR}")

    all_data = {}  # datetime_str -> value (dict for dedup)

    end_date = datetime.strptime(end_str, "%Y-%m-%d")
    start_limit = datetime(START_YEAR, 1, 1)

    current_end = end_date
    empty_count = 0
    col_idx = None

    while current_end > start_limit:
        end_tag = current_end.strftime("%Y-%m-%d")
        html = fetch_chunk(code, end_tag)

        if html:
            # Detect preferred column on first successful fetch
            if col_idx is None:
                col_idx = detect_preferred_column(html)
                # Show which sensor we're using
                headers = HEADER_RE.findall(html)
                if headers:
                    print(f"  Sensors: {headers}, using index {col_idx}")

            rows = parse_html_table(html, col_idx)
            if rows:
                empty_count = 0
                before = len(all_data)
                for dt_str, val in rows:
                    if dt_str not in all_data:
                        all_data[dt_str] = val
                new = len(all_data) - before
                print(f"  {end_tag}: {len(rows)} rows, {new} new (total: {len(all_data)})")
            else:
                empty_count += 1
                print(f"  {end_tag}: no data")
        else:
            empty_count += 1
            print(f"  {end_tag}: fetch failed")

        if empty_count >= 3:
            print(f"  3 consecutive empty chunks — stopping.")
            break

        current_end -= timedelta(days=30)
        time.sleep(1)

    if not all_data:
        print(f"  NO DATA for {code}!")
        return

    # Resample to 6-min intervals
    resampled = resample_6min(all_data)

    outfile = os.path.join(OUTPUT_DIR, f"{code}_{name}.csv")
    with open(outfile, "w") as f:
        f.write("datetime_utc,level_m\n")
        for dt_str, val in resampled:
            f.write(f"{dt_str},{val}\n")

    print(f"\n  Saved: {outfile}")
    print(f"  Raw data points: {len(all_data)}")
    print(f"  Resampled (6-min): {len(resampled)}")
    print(f"  Date range: {resampled[0][0]} — {resampled[-1][0]}")


def main():
    print("IOC Sea Level Monitoring — Cayman Islands Download")
    print(f"Output directory: {OUTPUT_DIR}")

    for station in STATIONS:
        download_station(station)

    print(f"\n{'='*60}")
    print("Done!")


if __name__ == "__main__":
    main()
