#!/usr/bin/env python3
"""
Download sea level data from DMI (Danish Meteorological Institute) Open Data API.
Downloads 'sealev_dvr' (DVR90 datum) at 10-min intervals.
Saves as NPZ files for UTide analysis.

API docs: https://opendataapi.dmi.dk/v2/oceanObs/swagger-ui/index.html
"""

import json
import numpy as np
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT_DIR = Path("/home/oliver/water_levels/Denmark_DMI/npz")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://opendataapi.dmi.dk/v2/oceanObs/collections/observation/items"
STATION_API = "https://opendataapi.dmi.dk/v2/oceanObs/collections/station/items"

# Parameter: sealev_dvr = sea level relative to DVR90 (Danish Vertical Reference)
PARAM = "sealev_dvr"

# Download in chunks of ~200 days (limit=300000, at 10-min = ~208 days)
CHUNK_DAYS = 200
LIMIT = 300000


def get_stations():
    """Fetch active primary tide gauge stations with sealev_dvr data."""
    resp = requests.get(STATION_API, params={
        'status': 'Active',
        'type': 'Tide-gauge-primary',
        'limit': 200,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Deduplicate by stationId, keep only stations with sealev_dvr
    seen = {}
    for f in data['features']:
        p = f['properties']
        sid = p['stationId']
        params = p.get('parameterId', [])
        if PARAM not in params:
            continue
        if p.get('operationTo') is not None:
            continue  # Skip discontinued stations

        coords = f['geometry']['coordinates']
        if sid not in seen:
            seen[sid] = {
                'stationId': sid,
                'name': p['name'],
                'lat': coords[1],
                'lon': coords[0],
                'operationFrom': p.get('operationFrom', ''),
            }

    return list(seen.values())


def download_station(station, start_year=2006):
    """Download sea level data for a station in chunks."""
    sid = station['stationId']
    name = station['name']
    npz_path = OUTPUT_DIR / f"{sid}.npz"

    if npz_path.exists():
        d = np.load(npz_path, allow_pickle=True)
        print(f"  schon vorhanden ({len(d['levels_m'])} Werte)")
        return True

    # Determine start date
    op_from = station.get('operationFrom', '')
    if op_from:
        station_start = datetime.fromisoformat(op_from.replace('Z', '+00:00')).replace(tzinfo=None)
        start_dt = max(station_start, datetime(start_year, 1, 1))
    else:
        start_dt = datetime(start_year, 1, 1)

    end_dt = datetime(2025, 12, 31)
    all_times = []
    all_values = []

    current = start_dt
    while current < end_dt:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS), end_dt)
        dt_range = f"{current.strftime('%Y-%m-%dT%H:%M:%SZ')}/{chunk_end.strftime('%Y-%m-%dT%H:%M:%SZ')}"

        try:
            resp = requests.get(API_BASE, params={
                'stationId': sid,
                'parameterId': PARAM,
                'datetime': dt_range,
                'limit': LIMIT,
            }, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            features = data.get('features', [])
            for f in features:
                p = f['properties']
                val = p.get('value')
                obs = p.get('observed')
                if val is not None and obs is not None:
                    dt = datetime.fromisoformat(obs.replace('Z', '+00:00')).replace(tzinfo=None)
                    all_times.append(dt)
                    all_values.append(float(val) / 100.0)  # cm → m

            chunk_str = f"{current.strftime('%Y-%m-%d')}→{chunk_end.strftime('%Y-%m-%d')}"
            print(f"    {chunk_str}: {len(features)} Werte", flush=True)

        except Exception as e:
            print(f"    FEHLER {current.strftime('%Y-%m-%d')}: {e}")

        current = chunk_end
        time.sleep(0.5)  # Rate limiting

    if not all_times:
        print(f"  ✗ Keine Daten")
        return False

    # Sort by time and remove duplicates
    times_arr = np.array(all_times, dtype='datetime64[s]')
    values_arr = np.array(all_values, dtype=np.float64)

    # Sort
    sort_idx = np.argsort(times_arr)
    times_arr = times_arr[sort_idx]
    values_arr = values_arr[sort_idx]

    # Remove duplicates
    _, unique_idx = np.unique(times_arr, return_index=True)
    times_arr = times_arr[unique_idx]
    values_arr = values_arr[unique_idx]

    # Save NPZ
    np.savez_compressed(npz_path,
                        datetimes_utc=times_arr,
                        levels_m=values_arr,
                        station_id=sid,
                        name=name,
                        latitude=station['lat'],
                        longitude=station['lon'],
                        datum='DVR90',
                        )

    years = len(times_arr) / (6 * 24 * 365.25)
    print(f"  ✓ {len(times_arr)} Werte ({years:.1f} Jahre) → {npz_path.name}")
    return True


def main():
    print("=" * 70)
    print("Download DMI Pegelstationen — Dänemark")
    print("=" * 70)

    stations = get_stations()
    print(f"\n{len(stations)} aktive Stationen mit {PARAM}\n")

    for i, s in enumerate(sorted(stations, key=lambda x: x['name']), 1):
        print(f"\n[{i}/{len(stations)}] {s['stationId']} | {s['name']} "
              f"({s['lat']:.4f}°N, {s['lon']:.4f}°E)")
        download_station(s)

    print(f"\n\nFertig. NPZ-Dateien in: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
