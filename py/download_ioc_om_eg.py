#!/usr/bin/env python3
"""
Download IOC sea level data for Oman + Egypt stations.

Oman: 9 active IOC stations (country code OMA). We keep the 3 UHSLC-based
production entries (Masirah/Muscat/Salalah), but still download all 9 for
verification — fit only the 6 we don't have.

Egypt: 6 IOC station codes (3 of them — alex/alex2/alex3 — co-located at
Alexandria, already covered by UHSLC). New targets: marn1 (Marina El
Alamein), matr (Marsa Matruh), psai (Port Saïd). All Mediterranean
microtidal → low expected hit rate.

Usage: python3 download_ioc_om_eg.py [--years N]
"""
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request

STATIONS = [
    # Oman — Arabian Sea / Gulf of Oman (all active May 2026)
    {'code': 'ashk',  'name': 'Ashkhara',         'country': 'Oman',  'lat': 21.8500, 'lon': 59.5700, 'start': 2018},
    {'code': 'duqm',  'name': 'Duqm',             'country': 'Oman',  'lat': 19.6600, 'lon': 57.7200, 'start': 2018},
    {'code': 'maji',  'name': 'Majis',            'country': 'Oman',  'lat': 24.5180, 'lon': 56.6060, 'start': 2018},
    {'code': 'masi2', 'name': 'Masirah',          'country': 'Oman',  'lat': 20.6830, 'lon': 58.8670, 'start': 2018},
    {'code': 'musc3', 'name': 'Muscat',           'country': 'Oman',  'lat': 23.6330, 'lon': 58.5670, 'start': 2018},
    {'code': 'qura',  'name': 'Qurayat',          'country': 'Oman',  'lat': 23.2600, 'lon': 58.9250, 'start': 2018},
    {'code': 'sala',  'name': 'Salalah',          'country': 'Oman',  'lat': 16.9350, 'lon': 54.0070, 'start': 2018},
    {'code': 'suro',  'name': 'Sur',              'country': 'Oman',  'lat': 22.5700, 'lon': 59.5200, 'start': 2018},
    {'code': 'wuda',  'name': 'Khawr Wudam',      'country': 'Oman',  'lat': 23.8200, 'lon': 57.5200, 'start': 2018},

    # Egypt — Mediterranean coast (microtidal)
    {'code': 'alex2', 'name': 'Alexandria',          'country': 'Egypt', 'lat': 31.2124, 'lon': 29.8849, 'start': 2014},
    {'code': 'alex3', 'name': 'Alexandria',          'country': 'Egypt', 'lat': 31.2125, 'lon': 29.8853, 'start': 2018},
    {'code': 'marn1', 'name': 'Marina El Alamein',   'country': 'Egypt', 'lat': 30.8439, 'lon': 28.9773, 'start': 2018},
    {'code': 'matr',  'name': 'Marsa Matruh',        'country': 'Egypt', 'lat': 31.3700, 'lon': 27.2039, 'start': 2018},
    {'code': 'psai',  'name': 'Port Saïd',           'country': 'Egypt', 'lat': 31.2583, 'lon': 32.3092, 'start': 2014},
]

OUTPUT_DIR = Path('/tmp/ioc_om_eg')


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


def download_station(station, max_years=10):
    code = station['code']
    out = OUTPUT_DIR / f"{code}_{station['country'].lower()[:2]}.csv"
    if out.exists() and out.stat().st_size > 100_000:
        n = sum(1 for _ in open(out)) - 1
        print(f"  Already downloaded ({n} rows), skipping.")
        return out

    end_year = 2026
    start_year = max(station['start'], end_year - max_years)
    print(f"  Downloading {start_year}-{end_year}...")
    all_data = []
    consecutive_empty = 0
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            if year == end_year and month > 5:
                break
            data = download_month(code, year, month)
            if data:
                all_data.extend(data)
                sys.stdout.write('.'); sys.stdout.flush()
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                if consecutive_empty > 36:
                    print(f" gave up after {consecutive_empty} empty months")
                    break
            time.sleep(0.4)
        else:
            continue
        break
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
    ap.add_argument('--years', type=int, default=10)
    ap.add_argument('--stations', type=str, default='')
    args = ap.parse_args()
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    stations = STATIONS
    if args.stations:
        codes = [c.strip() for c in args.stations.split(',')]
        stations = [s for s in STATIONS if s['code'] in codes]
    print(f"Downloading {len(stations)} Oman+Egypt IOC stations")
    for i, s in enumerate(stations):
        print(f"\n[{i+1}/{len(stations)}] {s['name']}, {s['country']} ({s['code']}):", flush=True)
        download_station(s, max_years=args.years)


if __name__ == '__main__':
    main()
