#!/usr/bin/env python3
"""
Download hourly sea level data from UHSLC ERDDAP for Indonesian stations.
Uses the combined fast+rq dataset where available, falls back to rq-only.
"""

import os
import requests
import time

OUTPUT_DIR = '/home/oliver/water_levels/Indonesia_UHSLC'

# Indonesian UHSLC stations with sufficient data for UTide
# Format: (uhslc_id, name, lat, lon, dataset)
# dataset: 'fast' = global_hourly_fast (combined FD+RQ), 'rq_indian'/'rq_pacific' = RQ only
STATIONS = [
    (33,  'Bitung',         1.438,  125.190, 'fast'),
    (107, 'Padang',        -1.000,  100.367, 'fast'),
    (122, 'Sibolga',        1.750,   98.767, 'fast'),
    (123, 'Sabang',         5.833,   95.333, 'fast'),
    (125, 'Prigi',         -8.283,  111.733, 'fast'),
    (133, 'Ambon',         -3.700,  128.200, 'fast'),
    (162, 'Cilacap',       -7.752,  109.017, 'fast'),
    (163, 'Benoa',         -8.745,  115.210, 'fast'),
    (416, 'Tanjung Lesung',-6.483,  105.667, 'fast'),
    (417, 'Sadeng',        -8.500,  110.783, 'fast'),
    (418, 'Waikelo',       -9.400,  119.233, 'fast'),
    (419, 'Lembar',        -8.732,  116.072, 'fast'),
    (420, 'Saumlaki',      -7.982,  131.290, 'fast'),
    (913, 'Telukdalam',     0.555,   97.822, 'fast'),
    (914, 'Meulaboh',       5.128,   96.132, 'fast'),
    # RQ-only (historical, but long enough for analysis)
    (160, 'Surabaya',      -7.208,  112.725, 'rq_indian'),
    (161, 'Jakarta',       -6.117,  106.850, 'rq_indian'),
]

ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap'

HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) TideResearch/1.0'}


def download_station(uhslc_id, name, dataset):
    """Download hourly data for one station."""
    safe_name = name.replace(' ', '_').replace("'", '')
    csv_path = os.path.join(OUTPUT_DIR, f'{uhslc_id}_{safe_name}.csv')

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 5000:
        print(f"  schon vorhanden")
        return True

    if dataset == 'fast':
        # Combined FD+RQ dataset
        url = (f"{ERDDAP_BASE}/global_hourly_fast.csv"
               f"?time,sea_level&uhslc_id={uhslc_id}&orderBy(%22time%22)")
    elif dataset == 'rq_indian':
        url = (f"{ERDDAP_BASE}/global_hourly_rqds.csv"
               f"?time,sea_level&uhslc_id={uhslc_id}&orderBy(%22time%22)")
    elif dataset == 'rq_pacific':
        url = (f"{ERDDAP_BASE}/global_hourly_rqds.csv"
               f"?time,sea_level&uhslc_id={uhslc_id}&orderBy(%22time%22)")
    else:
        print(f"  Unbekanntes Dataset: {dataset}")
        return False

    for attempt in range(3):
        try:
            print(f"  Downloading from {dataset}...", end='', flush=True)
            r = requests.get(url, headers=HEADERS, timeout=120)
            if r.status_code == 200:
                # Convert UHSLC format to our standard format
                lines = r.text.strip().split('\n')
                if len(lines) < 3:
                    print(f" Keine Daten")
                    return False

                # ERDDAP CSV: header, units, then data
                # time, sea_level -> time, waterlevel_m
                with open(csv_path, 'w') as f:
                    f.write('time,waterlevel_m\n')
                    for line in lines[2:]:  # skip header + units
                        parts = line.split(',')
                        if len(parts) >= 2:
                            time_str = parts[0]
                            level = parts[1].strip()
                            # UHSLC uses -32767 for missing
                            try:
                                val = float(level)
                                if val < -10000:
                                    continue
                                # Convert mm to meters
                                val_m = val / 1000.0
                                f.write(f"{time_str},{val_m:.4f}\n")
                            except ValueError:
                                continue

                # Count valid lines
                with open(csv_path) as f:
                    n_lines = sum(1 for _ in f) - 1

                if n_lines < 100:
                    print(f" Zu wenig Daten ({n_lines})")
                    os.remove(csv_path)
                    return False

                years = n_lines / (24 * 365.25)
                print(f" {n_lines} Werte ({years:.1f} Jahre)")
                return True
            else:
                print(f" HTTP {r.status_code}")
                if attempt < 2:
                    time.sleep(5)
        except Exception as e:
            print(f" Fehler: {e}")
            if attempt < 2:
                time.sleep(5)

    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("Download Hourly Sea Level -- Indonesia (UHSLC ERDDAP)")
    print("=" * 70)
    print(f"Stationen: {len(STATIONS)}")
    print()

    success = 0
    for i, (uid, name, lat, lon, ds) in enumerate(STATIONS):
        print(f"[{i+1:2d}/{len(STATIONS)}] {name} (UHSLC-{uid})")
        if download_station(uid, name, ds):
            success += 1
        time.sleep(1)
        print()

    print(f"{'='*70}")
    print(f"Ergebnis: {success}/{len(STATIONS)} erfolgreich")


if __name__ == '__main__':
    main()
