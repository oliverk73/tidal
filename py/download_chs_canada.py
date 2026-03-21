#!/usr/bin/env python3
"""
Download water level observations from Canadian Hydrographic Service (IWLS API)
for selected tide stations. Data at 15-min resolution, downloaded month by month.

API docs: https://api-sine.dfo-mpo.gc.ca/swagger-ui/index.html
Rate limits: 3 req/s, 30 req/min
"""

import os
import json
import time
import datetime
import requests
import pandas as pd

API_BASE = 'https://api-sine.dfo-mpo.gc.ca/api/v1'
OUTPUT_DIR = '/home/oliver/water_levels/Canada'

# 5 stations covering different tidal regimes
STATIONS = {
    '07120': {'name': 'Victoria Harbour', 'desc': 'Pacific, mixed tides'},
    '00490': {'name': 'Halifax', 'desc': 'Atlantic, semidiurnal'},
    '00065': {'name': 'Saint John', 'desc': 'Bay of Fundy, extreme semidiurnal'},
    '02985': {'name': 'Rimouski', 'desc': 'St. Lawrence estuary'},
    '05010': {'name': 'Churchill', 'desc': 'Hudson Bay, subarctic'},
}

RESOLUTION = 'FIFTEEN_MINUTES'


def get_station_info(code):
    """Get station ID, name, lat, lon from API."""
    resp = requests.get(f'{API_BASE}/stations', params={'code': code}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    s = data[0]
    return {
        'id': s['id'],
        'name': s['officialName'],
        'code': code,
        'lat': s.get('latitude', 0),
        'lon': s.get('longitude', 0),
    }


def get_wlo_holdings(station_id):
    """Get date range of wlo data."""
    resp = requests.get(f'{API_BASE}/stations/{station_id}/holdings', timeout=15)
    resp.raise_for_status()
    holdings = resp.json()

    # Find wlo time series by checking which has the most data
    earliest = '9999-12-31'
    latest = '0000-01-01'
    for h in holdings:
        for dh in h['dataHoldings']:
            if dh['dateStart'][:10] < earliest:
                earliest = dh['dateStart'][:10]
            if dh['dateEnd'][:10] > latest:
                latest = dh['dateEnd'][:10]
    return earliest, latest


def download_station(code, station_info, output_dir):
    """Download wlo data month by month at 15-min resolution."""
    safe_name = code + '_' + station_info['name'].replace(' ', '_').replace('/', '_')
    csv_path = os.path.join(output_dir, f'{safe_name}.csv')

    # Skip if already downloaded
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 10000:
        n_lines = sum(1 for _ in open(csv_path))
        print(f"  ✓ Bereits vorhanden ({n_lines} Zeilen), überspringe.")
        return True

    station_id = station_info['id']
    earliest, latest = get_wlo_holdings(station_id)
    print(f"  Daten verfügbar: {earliest} bis {latest}")

    # Generate month ranges
    start = datetime.date.fromisoformat(earliest)
    end = datetime.date.fromisoformat(latest)
    if end > datetime.date.today():
        end = datetime.date.today()

    months = []
    current = start.replace(day=1)
    while current <= end:
        next_month = (current.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        month_end = next_month - datetime.timedelta(days=1)
        if month_end > end:
            month_end = end
        months.append((current, month_end))
        current = next_month

    print(f"  {len(months)} Monate herunterzuladen...")

    all_rows = []
    for i, (m_start, m_end) in enumerate(months):
        from_dt = f'{m_start}T00:00:00Z'
        to_dt = f'{m_end}T23:59:59Z'

        for attempt in range(3):
            try:
                resp = requests.get(
                    f'{API_BASE}/stations/{station_id}/data',
                    params={
                        'time-series-code': 'wlo',
                        'from': from_dt,
                        'to': to_dt,
                        'resolution': RESOLUTION,
                    },
                    timeout=30,
                )
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    print(f' [429, warte {wait}s]', end='', flush=True)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                for d in data:
                    all_rows.append((d['eventDate'], d['value']))
                break

            except requests.exceptions.HTTPError as e:
                if '429' in str(e):
                    time.sleep(10 * (attempt + 1))
                else:
                    break
            except Exception as e:
                break

        # Rate limit: stay under 30/min
        time.sleep(2.1)

        if (i + 1) % 12 == 0 or (i + 1) == len(months):
            print(f"    {i+1}/{len(months)} Monate, {len(all_rows)} Werte", flush=True)

    if not all_rows:
        print("  KEINE DATEN")
        return False

    df = pd.DataFrame(all_rows, columns=['time', 'waterlevel_m'])
    df = df.drop_duplicates(subset='time').sort_values('time')

    # Clean timestamps
    df['time'] = pd.to_datetime(df['time']).dt.strftime('%Y-%m-%d %H:%M:%S+00:00')

    df.to_csv(csv_path, index=False)
    n_rows = len(df)
    years = n_rows / (4 * 24 * 365.25)  # 15-min = 4/hour
    print(f"  ✓ {n_rows} Werte ({years:.1f} Jahre) gespeichert")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 65)
    print("Download Water Level Observations — Canadian Hydrographic Service")
    print("=" * 65)
    print(f"Auflösung: {RESOLUTION}")
    print(f"Ausgabe: {OUTPUT_DIR}")
    print()

    # Get station metadata
    station_infos = {}
    for code, meta in STATIONS.items():
        info = get_station_info(code)
        if info:
            station_infos[code] = info
            print(f"  {code} | {info['name']:25s} | {info['lat']:.4f}, {info['lon']:.4f} | {meta['desc']}")
        else:
            print(f"  {code} | NICHT GEFUNDEN")
        time.sleep(0.5)

    print(f"\n{'='*65}\n")

    success = 0
    for code, info in station_infos.items():
        print(f"[{success+1}/{len(station_infos)}] {info['name']} ({STATIONS[code]['desc']})")
        if download_station(code, info, OUTPUT_DIR):
            success += 1
        print()

    print(f"{'='*65}")
    print(f"Ergebnis: {success}/{len(station_infos)} erfolgreich")

    # Show file sizes
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.csv'):
            path = os.path.join(OUTPUT_DIR, f)
            size_mb = os.path.getsize(path) / (1024*1024)
            print(f"  {f}: {size_mb:.1f} MB")


if __name__ == '__main__':
    main()
