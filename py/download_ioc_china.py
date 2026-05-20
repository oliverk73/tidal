#!/usr/bin/env python3
"""
Download IOC sea level data for 3 China mainland stations.

Stations have intermittent data 2018-2024 then went offline. Same JSON-API
download as Russia/Chile.

Usage: python3 download_ioc_china.py [--years N] [--stations a,b,c]
"""
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request

STATIONS = [
    {'code': 'qing', 'name': 'Qinglan',  'lat': 19.57, 'lon': 110.82, 'start': 2018},
    {'code': 'shen', 'name': 'Shenzhen', 'lat': 22.47, 'lon': 113.88, 'start': 2018},
    {'code': 'zhap', 'name': 'Zhapo',    'lat': 21.58, 'lon': 111.82, 'start': 2018},
]

OUTPUT_DIR = Path('/tmp/ioc_china')


def download_month(code, year, month):
    start = f"{year}-{month:02d}-01T00:00"
    end = f"{year + (month==12)}-{(month % 12)+1:02d}-01T00:00"
    url = (f"http://www.ioc-sealevelmonitoring.org/service.php?"
           f"query=data&code={code}&timestart={start}&timestop={end}&format=json")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'TideResearch/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return []


def download_station(station, max_years=8):
    code = station['code']
    name = station['name']
    out = OUTPUT_DIR / f"{code}_{name.lower()}.csv"
    if out.exists() and out.stat().st_size > 100_000:
        n = sum(1 for _ in open(out)) - 1
        print(f"  Already downloaded ({n} rows), skipping.")
        return out

    end_year = 2025
    start_year = max(station['start'], end_year - max_years)
    print(f"  Downloading {start_year}-{end_year}...")
    all_data = []
    for year in range(start_year, end_year):
        for month in range(1, 13):
            data = download_month(code, year, month)
            if data:
                all_data.extend(data)
                sys.stdout.write('.'); sys.stdout.flush()
            time.sleep(0.5)
    print(f" {len(all_data)} raw points")
    if not all_data:
        return None

    hourly = {}
    for p in all_data:
        try:
            t = datetime.strptime(p['stime'], '%Y-%m-%d %H:%M:%S')
            # Nearest-hour rounding (avoids ~14.5° M2 phase lag).
            hk = t.replace(minute=0, second=0)
            if t.minute >= 30:
                hk += timedelta(hours=1)
            hourly.setdefault(hk, []).append(float(p['slevel']))
        except (ValueError, KeyError):
            continue
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    with open(out, 'w') as f:
        f.write('time,waterlevel_m\n')
        for t in sorted(hourly.keys()):
            vals = hourly[t]
            f.write(f"{t.strftime('%Y-%m-%d %H:%M:%S')},{sum(vals)/len(vals):.4f}\n")
    print(f"  {len(hourly)} hourly values → {out}")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=int, default=8)
    ap.add_argument('--stations', type=str, default='')
    args = ap.parse_args()
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    stations = STATIONS
    if args.stations:
        codes = [c.strip() for c in args.stations.split(',')]
        stations = [s for s in STATIONS if s['code'] in codes]
    print(f"Downloading {len(stations)} China IOC stations")
    for s in stations:
        print(f"\n{'='*50}\n{s['name']} ({s['code']}) — {s['lat']:.3f}, {s['lon']:.3f}")
        download_station(s, max_years=args.years)


if __name__ == '__main__':
    main()
