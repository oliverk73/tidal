#!/usr/bin/env python3
"""
Download IOC sea level data for Turkey + Greece stations.

Turkey: 18 active stations 2024+.
Greece: 6 active + 11 currently-offline (BGAN-based). For offline stations,
the script still tries — IOC keeps historical data even when station goes
offline.

Usage: python3 download_ioc_tr_gr.py [--years N]
"""
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request

STATIONS = [
    # Turkey — all active 2024
    {'code': 'amas', 'name': 'Amasra',              'country': 'Turkey', 'lat': 41.7444, 'lon': 32.3918, 'start': 2018},
    {'code': 'anta', 'name': 'Antalya',             'country': 'Turkey', 'lat': 36.8355, 'lon': 30.6126, 'start': 2018},
    {'code': 'arsu', 'name': 'Arsuz (Hatay)',       'country': 'Turkey', 'lat': 36.4156, 'lon': 35.8852, 'start': 2018},
    {'code': 'bodr', 'name': 'Bodrum',              'country': 'Turkey', 'lat': 37.0322, 'lon': 27.4235, 'start': 2018},
    {'code': 'bozy', 'name': 'Bozyazi',             'country': 'Turkey', 'lat': 36.0974, 'lon': 32.9413, 'start': 2018},
    {'code': 'erdek', 'name': 'Erdek',              'country': 'Turkey', 'lat': 40.3899, 'lon': 27.8452, 'start': 2018},
    {'code': 'erdem', 'name': 'Erdemli',            'country': 'Turkey', 'lat': 36.5637, 'lon': 34.2554, 'start': 2018},
    {'code': 'gokc', 'name': 'Gokceada',            'country': 'Turkey', 'lat': 40.2314, 'lon': 25.8936, 'start': 2018},
    {'code': 'igne', 'name': 'Igneada',             'country': 'Turkey', 'lat': 41.8888, 'lon': 28.0237, 'start': 2018},
    {'code': 'ista', 'name': 'Istanbul',            'country': 'Turkey', 'lat': 41.1598, 'lon': 29.0741, 'start': 2018},
    {'code': 'maer', 'name': 'Marmara Ereglisi',    'country': 'Turkey', 'lat': 40.9690, 'lon': 27.9622, 'start': 2018},
    {'code': 'ment', 'name': 'Mentes',              'country': 'Turkey', 'lat': 38.4277, 'lon': 26.7166, 'start': 2018},
    {'code': 'mrms', 'name': 'Marmaris',            'country': 'Turkey', 'lat': 36.8380, 'lon': 28.3848, 'start': 2018},
    {'code': 'sile', 'name': 'Sile',                'country': 'Turkey', 'lat': 41.1798, 'lon': 29.6039, 'start': 2018},
    {'code': 'sino', 'name': 'Sinop',               'country': 'Turkey', 'lat': 42.0167, 'lon': 35.1500, 'start': 2018},
    {'code': 'tasu', 'name': 'Tasucu',              'country': 'Turkey', 'lat': 36.2815, 'lon': 33.8362, 'start': 2018},
    {'code': 'trab', 'name': 'Trabzon',             'country': 'Turkey', 'lat': 41.0019, 'lon': 39.7445, 'start': 2018},
    {'code': 'yalo', 'name': 'Yalova',              'country': 'Turkey', 'lat': 40.6620, 'lon': 29.2777, 'start': 2018},
    # Greece — mix of active and offline
    {'code': 'amor',  'name': 'Katapola, Amorgos',         'country': 'Greece', 'lat': 36.8309, 'lon': 25.8640, 'start': 2014},
    {'code': 'asty',  'name': 'Astypalaia island',         'country': 'Greece', 'lat': 36.5734, 'lon': 26.3410, 'start': 2014},
    {'code': 'corn1', 'name': 'Corinth',                   'country': 'Greece', 'lat': 37.9425, 'lon': 22.9336, 'start': 2014},
    {'code': 'delo',  'name': 'Delos Island',              'country': 'Greece', 'lat': 37.3986, 'lon': 25.2648, 'start': 2014},
    {'code': 'iera',  'name': 'Ierapetra, Crete',          'country': 'Greece', 'lat': 35.0037, 'lon': 25.7385, 'start': 2014},
    {'code': 'itea',  'name': 'Itea, Central Greece',      'country': 'Greece', 'lat': 38.4304, 'lon': 22.4228, 'start': 2014},
    {'code': 'kala',  'name': 'Kalamata',                  'country': 'Greece', 'lat': 37.0215, 'lon': 22.1098, 'start': 2014},
    {'code': 'kaps',  'name': 'Kapsali, Kythira',          'country': 'Greece', 'lat': 36.1429, 'lon': 22.9993, 'start': 2014},
    {'code': 'kaso',  'name': 'Kasos Island',              'country': 'Greece', 'lat': 35.4186, 'lon': 26.9218, 'start': 2014},
    {'code': 'kata',  'name': 'Katakolo',                  'country': 'Greece', 'lat': 37.6405, 'lon': 21.3192, 'start': 2014},
    {'code': 'koro',  'name': 'Koroni, Peloponnese',       'country': 'Greece', 'lat': 36.7975, 'lon': 21.9563, 'start': 2014},
    {'code': 'kos3',  'name': 'Kos, South Aegean',         'country': 'Greece', 'lat': 36.8910, 'lon': 27.3036, 'start': 2014},
    {'code': 'myko',  'name': 'Tourlos, Mykonos',          'country': 'Greece', 'lat': 37.4655, 'lon': 25.3222, 'start': 2014},
    {'code': 'pale',  'name': 'Paleochora, Crete',         'country': 'Greece', 'lat': 35.2302, 'lon': 23.6835, 'start': 2014},
    {'code': 'peir',  'name': 'Peiraias',                  'country': 'Greece', 'lat': 37.9347, 'lon': 23.6212, 'start': 2014},
    {'code': 'prev1', 'name': 'Preveza, Epirus',           'country': 'Greece', 'lat': 38.9495, 'lon': 20.7287, 'start': 2014},
    {'code': 'syro',  'name': 'Syros',                     'country': 'Greece', 'lat': 37.4380, 'lon': 24.9411, 'start': 2014},
]

OUTPUT_DIR = Path('/tmp/ioc_tr_gr')


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

    end_year = 2025
    start_year = max(station['start'], end_year - max_years)
    print(f"  Downloading {start_year}-{end_year}...")
    all_data = []
    consecutive_empty = 0
    for year in range(start_year, end_year):
        for month in range(1, 13):
            data = download_month(code, year, month)
            if data:
                all_data.extend(data)
                sys.stdout.write('.'); sys.stdout.flush()
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                if consecutive_empty > 36:  # 3 years of empty → quit early
                    print(f" gave up after {consecutive_empty} empty months")
                    break
            time.sleep(0.5)
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
    print(f"Downloading {len(stations)} Turkey+Greece IOC stations")
    for i, s in enumerate(stations):
        print(f"\n[{i+1}/{len(stations)}] {s['name']}, {s['country']} ({s['code']}):", flush=True)
        download_station(s, max_years=args.years)


if __name__ == '__main__':
    main()
