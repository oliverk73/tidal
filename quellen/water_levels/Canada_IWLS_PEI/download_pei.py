#!/usr/bin/env python3
"""Download water level data from Canadian IWLS API for PEI stations."""

import requests
import csv
import os
import time
from datetime import datetime, timedelta

OUTPUT_DIR = "/home/oliver/water_levels/Canada_IWLS_PEI"
API_BASES = [
    "https://api-iwls.dfo-mpo.gc.ca/api/v1",
    "https://api-sine.dfo-mpo.gc.ca/api/v1",
]
RATE_LIMIT = 2.2

session = requests.Session()
session.headers.update({"Accept": "application/json"})

API_BASE = None

def try_apis():
    """Find working API base."""
    global API_BASE
    for base in API_BASES:
        try:
            print(f"Trying {base} ...")
            r = session.get(f"{base}/stations", params={"limit": 1}, timeout=15)
            if r.status_code == 200:
                print(f"  -> Working! Status {r.status_code}")
                API_BASE = base
                return True
            else:
                print(f"  -> Status {r.status_code}")
        except Exception as e:
            print(f"  -> Error: {e}")
    return False

def find_station(code):
    """Find station by code."""
    # Try searching
    r = session.get(f"{API_BASE}/stations", params={"code": code}, timeout=30)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            for s in data:
                if s.get("code") == code:
                    return s
            # If exact match not found, return first
            return data[0]

    # Try getting all stations and filtering
    r = session.get(f"{API_BASE}/stations", timeout=60)
    if r.status_code == 200:
        data = r.json()
        for s in data:
            if s.get("code") == code:
                return s
    return None

def get_holdings(station_id):
    """Get data holdings for a station."""
    r = session.get(f"{API_BASE}/stations/{station_id}/holdings", timeout=30)
    if r.status_code == 200:
        return r.json()
    return None

def download_data(station_id, ts_code, from_dt, to_dt):
    """Download data month by month."""
    all_data = []
    current = from_dt
    while current < to_dt:
        # End of month
        if current.month == 12:
            next_month = current.replace(year=current.year+1, month=1)
        else:
            next_month = current.replace(month=current.month+1)
        end = min(next_month, to_dt)

        from_str = current.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"    Fetching {ts_code} {from_str} to {end_str} ...", end=" ", flush=True)

        params = {
            "time-series-code": ts_code,
            "from": from_str,
            "to": end_str,
            "resolution": "FIFTEEN_MINUTES",
        }

        try:
            r = session.get(f"{API_BASE}/stations/{station_id}/data", params=params, timeout=60)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    print(f"{len(data)} records")
                    all_data.extend(data)
                else:
                    print(f"Unexpected format: {type(data)}")
            else:
                print(f"HTTP {r.status_code}")
                if r.status_code == 404:
                    print(f"      Response: {r.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")

        time.sleep(RATE_LIMIT)
        current = next_month

    return all_data

def save_csv(data, filepath):
    """Save data to CSV."""
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "waterlevel_m"])
        for record in data:
            t = record.get("eventDate") or record.get("timeStamp") or record.get("time", "")
            v = record.get("value") or record.get("qcFlagCode")
            # Try different field names
            if v is None:
                v = record.get("value", "")
            writer.writerow([t, v])
    print(f"    Saved {len(data)} records to {os.path.basename(filepath)}")

def main():
    if not try_apis():
        print("ERROR: No working API found!")
        return

    print(f"\nUsing API: {API_BASE}\n")

    # Step 1: Get all stations, find PEI ones
    print("=" * 60)
    print("Fetching station list...")
    time.sleep(RATE_LIMIT)
    r = session.get(f"{API_BASE}/stations", timeout=60)
    if r.status_code != 200:
        print(f"Failed to get stations: {r.status_code}")
        return

    all_stations = r.json()
    print(f"Total stations: {len(all_stations)}")

    # Find PEI stations (province code PE or by coordinates roughly 46-47N, 62-64W)
    pei_stations = []
    target_codes = {}

    for s in all_stations:
        code = s.get("code", "")
        name = s.get("officialName") or s.get("name", "")
        lat = s.get("latitude", 0)
        lon = s.get("longitude", 0)

        # PEI bounding box: roughly 45.9-47.1N, 61.9-64.5W
        is_pei = (45.9 <= lat <= 47.1 and -64.5 <= lon <= -61.9)

        if code in ("01650", "01680", "01896", "01918"):
            target_codes[code] = s
            if not is_pei:
                is_pei = True  # Force include

        if is_pei:
            pei_stations.append(s)

    print(f"\nPEI stations found: {len(pei_stations)}")
    for s in sorted(pei_stations, key=lambda x: x.get("code", "")):
        print(f"  {s.get('code', '???'):>6}  {s.get('id', '')[:12]:12}  {s.get('officialName') or s.get('name', '???')}")

    # Check target stations
    print("\n" + "=" * 60)
    print("Target stations:")
    for code in ("01650", "01680", "01896", "01918"):
        if code in target_codes:
            s = target_codes[code]
            print(f"  {code}: {s.get('officialName') or s.get('name', '???')} (ID: {s.get('id', '???')})")
        else:
            print(f"  {code}: NOT FOUND!")

    # Step 2: Check holdings and download
    print("\n" + "=" * 60)
    print("Checking holdings and downloading data...\n")

    # Track which stations have WLP
    wlp_stations = []

    for s in sorted(pei_stations, key=lambda x: x.get("code", "")):
        sid = s.get("id", "")
        code = s.get("code", "")
        name = s.get("officialName") or s.get("name", "???")

        print(f"\n--- {code} {name} (ID: {sid}) ---")

        time.sleep(RATE_LIMIT)
        holdings = get_holdings(sid)

        has_wlo = False
        has_wlp = False

        if holdings:
            for h in holdings:
                ts = h.get("timeSeriesCode") or h.get("code", "")
                print(f"  Holding: {ts}  from={h.get('from', '?')}  to={h.get('to', '?')}")
                if ts.lower() == "wlo":
                    has_wlo = True
                if ts.lower() == "wlp":
                    has_wlp = True
        else:
            print("  No holdings data available")
            # Try to get metadata
            time.sleep(RATE_LIMIT)
            r2 = session.get(f"{API_BASE}/stations/{sid}/metadata", timeout=30)
            if r2.status_code == 200:
                meta = r2.json()
                ts_list = meta.get("timeSeries", [])
                for ts in ts_list:
                    ts_code = ts.get("code", "")
                    print(f"  TimeSeries: {ts_code}")
                    if ts_code.lower() == "wlo":
                        has_wlo = True
                    if ts_code.lower() == "wlp":
                        has_wlp = True

        safe_name = name.replace("/", "-").replace(" ", "_")

        # Download WLO for target stations
        if code in ("01650", "01680"):
            if code == "01650":
                from_dt = datetime(2025, 5, 1)
            else:
                from_dt = datetime(2025, 1, 1)
            to_dt = datetime(2025, 12, 31, 23, 59, 59)

            print(f"  -> Downloading WLO from {from_dt.date()} to {to_dt.date()}")
            data = download_data(sid, "wlo", from_dt, to_dt)
            if data:
                filepath = os.path.join(OUTPUT_DIR, f"{code}_{safe_name}_wlo.csv")
                save_csv(data, filepath)
            else:
                print("    No WLO data received")

        # Download WLP for target stations and all PEI stations that have it
        if code in ("01896", "01918") or has_wlp:
            wlp_stations.append((code, name, sid))
            from_dt = datetime(2025, 1, 1)
            to_dt = datetime(2025, 12, 31, 23, 59, 59)

            print(f"  -> Downloading WLP from {from_dt.date()} to {to_dt.date()}")
            data = download_data(sid, "wlp", from_dt, to_dt)
            if data:
                filepath = os.path.join(OUTPUT_DIR, f"{code}_{safe_name}_wlp.csv")
                save_csv(data, filepath)
            else:
                print("    No WLP data received")
                # Also try for the two required stations even if holdings didn't show wlp
                if code in ("01896", "01918") and not has_wlp:
                    print("    (Was specifically requested, tried anyway)")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    csvfiles = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".csv")])
    for f in csvfiles:
        fpath = os.path.join(OUTPUT_DIR, f)
        with open(fpath) as fh:
            lines = sum(1 for _ in fh) - 1  # minus header
        print(f"  {f}: {lines} records")

    if not csvfiles:
        print("  No CSV files created!")

if __name__ == "__main__":
    main()
