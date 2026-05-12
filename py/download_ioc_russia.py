#!/usr/bin/env python3
"""
Download sea level data for 7 Russian Far East stations from IOC Sea Level
Monitoring (service.php JSON API). Resample to hourly.

Stations: Kholmsk, Korsakov, Kuril'sk, Poronajsk, Preobrazheniye,
Rudnaya Pristan, Sosunovo. All Primorye/Sakhalin/Kuril coast (Sea of Japan
and Sea of Okhotsk south).

Usage: python3 download_ioc_russia.py [--years N] [--stations code1,code2,...]
"""
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request

STATIONS = [
    {'code': 'khol', 'name': 'Kholmsk',          'lat': 47.0506, 'lon': 142.0439, 'start': 2014},
    {'code': 'kors', 'name': 'Korsakov',         'lat': 46.6333, 'lon': 142.7667, 'start': 2024},
    {'code': 'kuri', 'name': "Kuril'sk",         'lat': 45.2300, 'lon': 147.8800, 'start': 2024},
    {'code': 'poro', 'name': 'Poronajsk',        'lat': 49.2200, 'lon': 143.0900, 'start': 2014},
    {'code': 'preo', 'name': 'Preobrazheniye',   'lat': 42.9092, 'lon': 133.9225, 'start': 2014},
    {'code': 'rudn', 'name': 'Rudnaya Pristan',  'lat': 44.3500, 'lon': 135.8000, 'start': 2014},
    {'code': 'sosu', 'name': 'Sosunovo',         'lat': 46.5300, 'lon': 138.3300, 'start': 2014},
]

OUTPUT_DIR = Path('/tmp/ioc_russia')


def download_month(code, year, month):
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
            return json.loads(resp.read().decode())
    except Exception:
        return []


def download_station(station, max_years=12):
    code = station['code']
    name = station['name']
    safe = name.lower().replace(' ', '_').replace("'", '')
    output_file = OUTPUT_DIR / f"{code}_{safe}.csv"

    if output_file.exists():
        n = sum(1 for _ in open(output_file)) - 1
        if n > 1000:
            print(f"  Already downloaded ({n} rows), skipping.")
            return output_file

    end_year = 2026
    start_year = max(station['start'], end_year - max_years)

    print(f"  Downloading {start_year}-{end_year}...")
    all_data = []
    for year in range(start_year, end_year):
        for month in range(1, 13):
            if year == end_year - 1 and month > 3:
                break
            data = download_month(code, year, month)
            if data:
                all_data.extend(data)
                sys.stdout.write('.'); sys.stdout.flush()
            time.sleep(0.5)

    print(f" {len(all_data)} raw points")
    if not all_data:
        return None

    # Resample to hourly mean
    hourly = {}
    for p in all_data:
        try:
            t = datetime.strptime(p['stime'], '%Y-%m-%d %H:%M:%S')
            hk = t.replace(minute=0, second=0)
            hourly.setdefault(hk, []).append(float(p['slevel']))
        except (ValueError, KeyError):
            continue

    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    with open(output_file, 'w') as f:
        f.write('time,waterlevel_m\n')
        for t in sorted(hourly.keys()):
            vals = hourly[t]
            f.write(f"{t.strftime('%Y-%m-%d %H:%M:%S')},{sum(vals)/len(vals):.4f}\n")

    print(f"  {len(hourly)} hourly values → {output_file}")
    return output_file


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=int, default=12)
    ap.add_argument('--stations', type=str, default='')
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    stations = STATIONS
    if args.stations:
        codes = [c.strip() for c in args.stations.split(',')]
        stations = [s for s in STATIONS if s['code'] in codes]

    print(f"Downloading {len(stations)} Russian Far East IOC stations")
    for s in stations:
        print(f"\n{'='*50}\n{s['name']} ({s['code']}) — {s['lat']:.3f}, {s['lon']:.3f}")
        download_station(s, max_years=args.years)


if __name__ == '__main__':
    main()
