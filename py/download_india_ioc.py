#!/usr/bin/env python3
"""
Download sea level data from IOC Sea Level Monitoring for Indian stations.
Downloads monthly chunks via JSON API, resamples to hourly, saves as CSV.
"""
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request

STATIONS = [
    {'code': 'chenn', 'name': 'Chennai',        'lat': 13.0827, 'lon': 80.2707, 'start': 2007},
    {'code': 'vish',  'name': 'Visakhapatnam',   'lat': 17.6868, 'lon': 83.2785, 'start': 2007},
    {'code': 'ptbl',  'name': 'Port Blair',      'lat': 11.6834, 'lon': 92.7518, 'start': 2007},
    {'code': 'marm',  'name': 'Marmagao',        'lat': 15.4177, 'lon': 73.7990, 'start': 2007},
    {'code': 'coch',  'name': 'Cochin',          'lat':  9.9312, 'lon': 76.2673, 'start': 2007},
    {'code': 'veer',  'name': 'Veraval',         'lat': 20.9009, 'lon': 70.3634, 'start': 2007},
    {'code': 'mini',  'name': 'Minicoy',         'lat':  8.2744, 'lon': 73.0431, 'start': 2007},
    {'code': 'okha',  'name': 'Okha',            'lat': 22.4667, 'lon': 69.0833, 'start': 2007},
    {'code': 'kand',  'name': 'Kandla',          'lat': 23.0333, 'lon': 70.2167, 'start': 2007},
    {'code': 'para',  'name': 'Paradip',         'lat': 20.2644, 'lon': 86.6275, 'start': 2007},
    {'code': 'mang',  'name': 'Mangalore',       'lat': 12.8475, 'lon': 74.8199, 'start': 2007},
    {'code': 'tuti',  'name': 'Tuticorin',       'lat':  8.7642, 'lon': 78.1348, 'start': 2007},
    {'code': 'mumb',  'name': 'Mumbai',          'lat': 18.9067, 'lon': 72.8147, 'start': 2007},
]

OUTPUT_DIR = Path('/home/oliver/water_levels/India_IOC')


def download_month(code, year, month):
    """Download one month of data from IOC JSON API."""
    start = f"{year}-{month:02d}-01T00:00"
    if month == 12:
        end = f"{year+1}-01-01T00:00"
    else:
        end = f"{year}-{month+1:02d}-01T00:00"

    url = (f"http://www.ioc-sealevelmonitoring.org/service.php?"
           f"query=data&code={code}&timestart={start}&timestop={end}&format=json")

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'TideResearch/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data
    except Exception:
        return []


def download_station(station, max_years=19):
    """Download all available data for a station, save as hourly CSV."""
    code = station['code']
    name = station['name']
    output_file = OUTPUT_DIR / f"{code}_{name.lower().replace(' ', '_')}.csv"

    if output_file.exists():
        lines = output_file.read_text().strip().split('\n')
        if len(lines) > 1000:
            print(f"  Already downloaded ({len(lines)-1} rows), skipping.")
            return output_file

    end_year = 2026
    start_year = max(station['start'], end_year - max_years)

    print(f"  Downloading {start_year}-{end_year}...")
    all_data = []

    for year in range(start_year, end_year):
        for month in range(1, 13):
            if year == 2026 and month > 4:
                break
            data = download_month(code, year, month)
            if data:
                all_data.extend(data)
                sys.stdout.write('.')
                sys.stdout.flush()
            else:
                sys.stdout.write('x')
                sys.stdout.flush()
            time.sleep(0.5)

    print(f" {len(all_data)} raw points")

    if not all_data:
        print("  No data!")
        return None

    # Convert to hourly: take mean of all values within each hour
    hourly = {}
    for point in all_data:
        try:
            t = datetime.strptime(point['stime'], '%Y-%m-%d %H:%M:%S')
            # Nearest-hour rounding: mean-of-hour centered at HH:00,
            # not labeled at start (avoids ~14.5° M2 phase lag).
            hour_key = t.replace(minute=0, second=0)
            if t.minute >= 30:
                hour_key += timedelta(hours=1)
            level = float(point['slevel'])
            if level <= -9999 or level > 100 or level < -100:
                continue
            if hour_key not in hourly:
                hourly[hour_key] = []
            hourly[hour_key].append(level)
        except (ValueError, KeyError):
            continue

    # Write CSV
    with open(output_file, 'w') as f:
        f.write('datetime_utc,level_m\n')
        for t in sorted(hourly.keys()):
            vals = hourly[t]
            mean_val = sum(vals) / len(vals)
            f.write(f"{t.strftime('%Y-%m-%d %H:%M:%S')},{mean_val:.4f}\n")

    print(f"  {len(hourly)} hourly values saved to {output_file}")
    return output_file


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {len(STATIONS)} Indian IOC stations")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'='*60}")

    for i, station in enumerate(STATIONS):
        print(f"\n[{i+1}/{len(STATIONS)}] {station['code']} — {station['name']} "
              f"({station['lat']:.4f}°N, {station['lon']:.4f}°E)")
        download_station(station)

    print(f"\n{'='*60}")
    print("Done!")


if __name__ == '__main__':
    main()
