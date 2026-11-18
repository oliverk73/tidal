#!/usr/bin/env python3
"""Download WLP predictions for all PEI stations that have them."""

import requests
import csv
import os
import time
from datetime import datetime

OUTPUT_DIR = "/home/oliver/water_levels/Canada_IWLS_PEI"
API_BASE = "https://api-iwls.dfo-mpo.gc.ca/api/v1"
RATE_LIMIT = 2.2

session = requests.Session()
session.headers.update({"Accept": "application/json"})

# Already downloaded
ALREADY_DONE = {"01896", "01918"}

def download_data(station_id, ts_code, from_dt, to_dt):
    """Download data month by month."""
    all_data = []
    current = from_dt
    while current < to_dt:
        if current.month == 12:
            next_month = current.replace(year=current.year+1, month=1)
        else:
            next_month = current.replace(month=current.month+1)
        end = min(next_month, to_dt)

        from_str = current.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"    {from_str[:7]} ...", end=" ", flush=True)

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
                    print(f"{len(data)} rec", flush=True)
                    all_data.extend(data)
                else:
                    print(f"unexpected", flush=True)
            else:
                print(f"HTTP {r.status_code}", flush=True)
        except Exception as e:
            print(f"Error: {e}", flush=True)

        time.sleep(RATE_LIMIT)
        current = next_month

    return all_data

def save_csv(data, filepath):
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "waterlevel_m"])
        for record in data:
            t = record.get("eventDate") or record.get("timeStamp") or record.get("time", "")
            v = record.get("value", "")
            writer.writerow([t, v])
    print(f"    -> Saved {len(data)} records to {os.path.basename(filepath)}")

def main():
    print("Fetching all stations...")
    r = session.get(f"{API_BASE}/stations", timeout=60)
    all_stations = r.json()
    print(f"Total: {len(all_stations)}")

    # Find PEI stations
    pei_stations = []
    for s in all_stations:
        code = s.get("code", "")
        lat = s.get("latitude", 0)
        lon = s.get("longitude", 0)
        if 45.9 <= lat <= 47.1 and -64.5 <= lon <= -61.9:
            pei_stations.append(s)

    print(f"PEI stations: {len(pei_stations)}")

    # Check each for WLP via station detail
    wlp_to_download = []
    for s in sorted(pei_stations, key=lambda x: x.get("code", "")):
        code = s.get("code", "")
        sid = s.get("id", "")
        name = s.get("officialName") or s.get("name", "???")

        if code in ALREADY_DONE:
            print(f"  {code} {name}: already done, skip")
            continue

        # Check timeSeries in station detail
        ts_list = s.get("timeSeries", [])
        has_wlp = any(ts.get("code") == "wlp" for ts in ts_list)

        if not has_wlp:
            # Need to fetch station detail
            time.sleep(RATE_LIMIT)
            r2 = session.get(f"{API_BASE}/stations/{sid}", timeout=30)
            if r2.status_code == 200:
                detail = r2.json()
                ts_list = detail.get("timeSeries", [])
                has_wlp = any(ts.get("code") == "wlp" for ts in ts_list)

        ts_codes = [ts.get("code", "?") for ts in ts_list]
        status = "HAS WLP" if has_wlp else "no wlp"
        print(f"  {code} {name}: {ts_codes} -> {status}")

        if has_wlp:
            wlp_to_download.append((code, name, sid))

    print(f"\nStations with WLP to download: {len(wlp_to_download)}")
    for code, name, sid in wlp_to_download:
        print(f"  {code} {name}")

    # Download WLP for each
    from_dt = datetime(2025, 1, 1)
    to_dt = datetime(2025, 12, 31, 23, 59, 59)

    for code, name, sid in wlp_to_download:
        safe_name = name.replace("/", "-").replace(" ", "_")
        filepath = os.path.join(OUTPUT_DIR, f"{code}_{safe_name}_wlp.csv")

        if os.path.exists(filepath):
            print(f"\n--- {code} {name}: file exists, skipping ---")
            continue

        print(f"\n--- Downloading WLP for {code} {name} ---")
        data = download_data(sid, "wlp", from_dt, to_dt)
        if data:
            save_csv(data, filepath)
        else:
            print("    No data received")

    # Summary
    print("\n" + "=" * 60)
    print("ALL CSV FILES:")
    csvfiles = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".csv")])
    for f in csvfiles:
        fpath = os.path.join(OUTPUT_DIR, f)
        with open(fpath) as fh:
            lines = sum(1 for _ in fh) - 1
        print(f"  {f}: {lines} records")

if __name__ == "__main__":
    main()
