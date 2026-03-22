#!/usr/bin/env python3
"""
Download sea level data from Marine Institute Ireland ERDDAP.
Irish National Tide Gauge Network - 5-min intervals, LAT datum.
Saves as NPZ files for UTide analysis.
"""

import numpy as np
import requests
import time
from datetime import datetime
from pathlib import Path
from io import StringIO

OUTPUT_DIR = Path("/home/oliver/water_levels/Ireland_MI/npz")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ERDDAP_BASE = "https://erddap.marine.ie/erddap/tabledap/IrishNationalTideGaugeNetwork"

# Download in yearly chunks to avoid timeouts
CHUNK_YEARS = 2


def get_stations():
    """Get unique station list from ERDDAP."""
    url = f"{ERDDAP_BASE}.csv?station_id%2Clatitude%2Clongitude&distinct()"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    lines = resp.text.strip().split('\n')
    # Skip header and units rows
    stations = {}
    for line in lines[2:]:
        parts = line.split(',')
        if len(parts) >= 3:
            name = parts[0].strip()
            lat = float(parts[1])
            lon = float(parts[2])
            # Use name as key, deduplicate (keep first)
            base_name = name.rstrip(' 12')  # Remove " 2" suffix
            if base_name not in stations:
                stations[base_name] = {
                    'station_id': name,
                    'name': base_name,
                    'lat': lat,
                    'lon': lon,
                }
    return list(stations.values())


def download_station(station, start_year=2006):
    """Download sea level data for a station in yearly chunks."""
    sid = station['station_id']
    name = station['name']
    safe_name = name.replace('/', '_').replace(' ', '_')
    npz_path = OUTPUT_DIR / f"{safe_name}.npz"

    if npz_path.exists():
        d = np.load(npz_path, allow_pickle=True)
        n = len(d['levels_m'])
        years = n / (12 * 24 * 365.25)  # 5-min data
        print(f"  schon vorhanden ({n} Werte, {years:.1f}J)")
        return True

    all_times = []
    all_values = []

    current_year = start_year
    end_year = 2026

    while current_year < end_year:
        chunk_end = min(current_year + CHUNK_YEARS, end_year)
        start_dt = f"{current_year}-01-01T00:00:00Z"
        end_dt = f"{chunk_end}-01-01T00:00:00Z"

        # URL-encode the station_id (spaces, special chars)
        import urllib.parse
        encoded_sid = urllib.parse.quote(sid, safe='')

        url = (f"{ERDDAP_BASE}.csv?"
               f"time%2CWater_Level_LAT"
               f"&station_id=%22{encoded_sid}%22"
               f"&time>={start_dt}&time<{end_dt}"
               f"&orderBy(%22time%22)")

        try:
            resp = requests.get(url, timeout=300)
            if resp.status_code == 404:
                # No data for this period
                print(f"    {current_year}-{chunk_end}: keine Daten")
                current_year = chunk_end
                continue
            resp.raise_for_status()

            lines = resp.text.strip().split('\n')
            count = 0
            for line in lines[2:]:  # Skip header + units
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        dt = datetime.fromisoformat(parts[0].replace('Z', '+00:00')).replace(tzinfo=None)
                        val = float(parts[1])
                        if not np.isnan(val):
                            all_times.append(dt)
                            all_values.append(val)
                            count += 1
                    except (ValueError, IndexError):
                        pass
            print(f"    {current_year}-{chunk_end}: {count} Werte", flush=True)

        except requests.exceptions.HTTPError as e:
            if '404' in str(e):
                print(f"    {current_year}-{chunk_end}: keine Daten")
            else:
                print(f"    FEHLER {current_year}: {e}")
        except Exception as e:
            print(f"    FEHLER {current_year}: {e}")

        current_year = chunk_end
        time.sleep(1)  # Be nice to ERDDAP

    if not all_times:
        print(f"  ✗ Keine Daten")
        return False

    # Sort and deduplicate
    times_arr = np.array(all_times, dtype='datetime64[s]')
    values_arr = np.array(all_values, dtype=np.float64)

    sort_idx = np.argsort(times_arr)
    times_arr = times_arr[sort_idx]
    values_arr = values_arr[sort_idx]

    _, unique_idx = np.unique(times_arr, return_index=True)
    times_arr = times_arr[unique_idx]
    values_arr = values_arr[unique_idx]

    # Save NPZ
    np.savez_compressed(npz_path,
                        datetimes_utc=times_arr,
                        levels_m=values_arr,
                        station_id=safe_name,
                        name=name,
                        latitude=station['lat'],
                        longitude=station['lon'],
                        datum='LAT',
                        )

    years = len(times_arr) / (12 * 24 * 365.25)
    print(f"  ✓ {len(times_arr)} Werte ({years:.1f} Jahre) → {npz_path.name}")
    return True


def main():
    print("=" * 70)
    print("Download Marine Institute Ireland — Pegeldaten")
    print("=" * 70)

    stations = get_stations()
    print(f"\n{len(stations)} Stationen gefunden\n")

    for i, s in enumerate(sorted(stations, key=lambda x: x['name']), 1):
        print(f"\n[{i}/{len(stations)}] {s['name']} "
              f"({s['lat']:.4f}°N, {s['lon']:.4f}°E)")
        download_station(s)

    print(f"\n\nFertig. NPZ-Dateien in: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
