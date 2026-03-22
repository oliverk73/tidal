#!/usr/bin/env python3
"""
Download 10-min sea level data from Queensland Government Open Data Portal.
Uses CKAN API to fetch tide gauge data from MSQ stations.
Saves as NPZ files for UTide analysis.
"""

import json
import numpy as np
import requests
import time
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("/home/oliver/water_levels/Australia_QLD/npz")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://www.data.qld.gov.au/api/3/action"

# Station datasets from QLD data portal (dataset_id → station info)
STATIONS = {
    'cairns': {
        'dataset': '1e96cbe0-771b-48d9-82cc-329607d3abba',
        'name': 'Cairns', 'lat': -16.92, 'lon': 145.77,
    },
    'townsville': {
        'dataset': '1e874768-43ed-4d82-8a2f-bb689c4eefd4',
        'name': 'Townsville', 'lat': -19.25, 'lon': 146.77,
    },
    'mackay': {
        'dataset': 'bc6ef33d-b3be-4e3f-ae4c-adb0601461a8',
        'name': 'Mackay', 'lat': -21.10, 'lon': 149.22,
    },
    'southport': {
        'dataset': 'd99c2929-e42c-49f0-8249-f4f20eb311f8',
        'name': 'Southport', 'lat': -27.94, 'lon': 153.43,
    },
    'bowen': {
        'dataset': '95ba8f5b-cdc2-4409-a701-fb9a38ac5017',
        'name': 'Bowen', 'lat': -20.02, 'lon': 148.25,
    },
    'bundaberg': {
        'dataset': 'a9ad661a-82ca-4d0d-9a1c-37a25bc1dfcc',
        'name': 'Bundaberg', 'lat': -24.76, 'lon': 152.39,
    },
    'urangan': {
        'dataset': 'cc83963c-dc50-4047-9d49-a1d5ef59c7c3',
        'name': 'Urangan', 'lat': -25.29, 'lon': 152.91,
    },
    'cooktown': {
        'dataset': '863abfda-ec9b-4408-b896-458cbf5a3388',
        'name': 'Cooktown', 'lat': -15.47, 'lon': 145.25,
    },
    'cardwell': {
        'dataset': 'aed24280-fbd4-49da-b2dc-6e87b6b256ba',
        'name': 'Cardwell', 'lat': -18.27, 'lon': 146.03,
    },
    'karumba': {
        'dataset': '179c7cc5-26a7-4f57-9e1e-3ec2ed5dd4de',
        'name': 'Karumba', 'lat': -17.49, 'lon': 140.84,
    },
    'mourilyan': {
        'dataset': '94174433-ac3e-474a-a03e-9c87f320c38c',
        'name': 'Mourilyan', 'lat': -17.60, 'lon': 146.10,
    },
    'mooloolaba': {
        'dataset': '43c33f0c-cd08-4281-b13e-a108101fc1cb',
        'name': 'Mooloolaba', 'lat': -26.68, 'lon': 153.12,
    },
    'weipa': {
        'dataset': '4a8b4b86-95dc-426c-a33f-02fdc8e58f8d',
        'name': 'Weipa', 'lat': -12.67, 'lon': 141.87,
    },
    'lucinda': {
        'dataset': '1b540272-464e-456e-b3d9-806dbd5538b4',
        'name': 'Lucinda', 'lat': -18.52, 'lon': 146.39,
    },
    'shorncliffe': {
        'dataset': '5473e4a2-a5ab-4d9c-906a-efdc0e099617',
        'name': 'Shorncliffe', 'lat': -27.33, 'lon': 153.08,
    },
    'scarborough': {
        'dataset': '43f307f6-522b-4507-a970-c074efceeca9',
        'name': 'Scarborough', 'lat': -27.19, 'lon': 153.10,
    },
}


def get_resources(dataset_id):
    """Get all CSV resources for a dataset."""
    url = f"{API_BASE}/package_show?id={dataset_id}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    pkg = resp.json()['result']
    resources = []
    for r in pkg.get('resources', []):
        if r.get('format', '').lower() == 'csv':
            resources.append({
                'id': r['id'],
                'name': r.get('name', ''),
                'url': r.get('url', ''),
            })
    return resources


def download_resource(resource_id, max_records=100000):
    """Download all records from a CKAN datastore resource."""
    all_records = []
    offset = 0
    limit = 32000  # CKAN default max

    while True:
        url = f"{API_BASE}/datastore_search"
        params = {
            'resource_id': resource_id,
            'limit': limit,
            'offset': offset,
        }
        try:
            resp = requests.get(url, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            if not data.get('success'):
                break

            records = data['result']['records']
            if not records:
                break

            all_records.extend(records)
            offset += len(records)

            if len(records) < limit:
                break
            if offset >= max_records:
                break

        except Exception as e:
            print(f"      FEHLER bei offset {offset}: {e}")
            break

        time.sleep(0.3)

    return all_records


def parse_records(records):
    """Parse CKAN datastore records into datetime/level arrays."""
    times = []
    values = []

    for rec in records:
        try:
            date_str = rec.get('Date', '').strip()
            time_str = rec.get('Time', '').strip()
            reading = rec.get('Reading', '')

            if not date_str or not time_str or not reading:
                continue

            val = float(reading)
            if val < -10 or val > 50:  # Invalid
                continue

            # Parse various date formats
            dt_str = f"{date_str} {time_str}"
            for fmt in ['%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M', '%d-%m-%Y %H:%M']:
                try:
                    dt = datetime.strptime(dt_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                continue

            times.append(dt)
            values.append(val)

        except (ValueError, TypeError):
            pass

    return times, values


def download_station(key, station):
    """Download all data for a station."""
    name = station['name']
    npz_path = OUTPUT_DIR / f"{name}.npz"

    if npz_path.exists():
        d = np.load(npz_path, allow_pickle=True)
        n = len(d['levels_m'])
        years = n / (6 * 24 * 365.25)
        print(f"  schon vorhanden ({n} Werte, {years:.1f}J)")
        return True

    # Get all CSV resources for this dataset
    resources = get_resources(station['dataset'])
    print(f"  {len(resources)} Ressourcen gefunden")

    all_times = []
    all_values = []

    for i, res in enumerate(resources):
        res_name = res.get('name', res['id'][:20])
        records = download_resource(res['id'])
        if records:
            times, values = parse_records(records)
            all_times.extend(times)
            all_values.extend(values)
            print(f"    [{i+1}/{len(resources)}] {res_name[:50]}: {len(times)} Werte",
                  flush=True)
        else:
            print(f"    [{i+1}/{len(resources)}] {res_name[:50]}: keine Daten")
        time.sleep(0.5)

    if not all_times:
        print(f"  ✗ Keine Daten")
        return False

    times_arr = np.array(all_times, dtype='datetime64[s]')
    values_arr = np.array(all_values, dtype=np.float64)

    sort_idx = np.argsort(times_arr)
    times_arr = times_arr[sort_idx]
    values_arr = values_arr[sort_idx]

    _, unique_idx = np.unique(times_arr, return_index=True)
    times_arr = times_arr[unique_idx]
    values_arr = values_arr[unique_idx]

    np.savez_compressed(npz_path,
                        datetimes_utc=times_arr,
                        levels_m=values_arr,
                        station_id=key,
                        name=name,
                        latitude=station['lat'],
                        longitude=station['lon'],
                        datum='LAT_QLD',
                        )

    years = len(times_arr) / (6 * 24 * 365.25)
    print(f"  ✓ {len(times_arr)} Werte ({years:.1f} Jahre) → {npz_path.name}")
    return True


def main():
    print("=" * 70)
    print("Download Queensland MSQ — Pegeldaten")
    print("=" * 70)
    print(f"\n{len(STATIONS)} Stationen\n")

    for i, (key, station) in enumerate(sorted(STATIONS.items(), key=lambda x: x[1]['name']), 1):
        print(f"\n[{i}/{len(STATIONS)}] {station['name']} "
              f"({station['lat']:.2f}°S, {station['lon']:.2f}°E)")
        download_station(key, station)

    print(f"\n\nFertig. NPZ-Dateien in: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
