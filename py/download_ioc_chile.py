#!/usr/bin/env python3
"""
Download sea level data from IOC Sea Level Monitoring for Chilean stations.
Downloads monthly chunks, resamples to hourly, saves as CSV.

Usage: python3 download_ioc_chile.py [--years N] [--stations code1,code2,...]
"""
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request

# All Chilean IOC stations (sorted north to south)
# Only include stations with enough historical data (>= 2 years from start)
STATIONS = [
    {'code': 'aric', 'name': 'Arica', 'lat': -18.477, 'lon': -70.322, 'start': 2009},
    {'code': 'pisa', 'name': 'Pisagua', 'lat': -19.597, 'lon': -70.216, 'start': 2012},
    {'code': 'iqui', 'name': 'Iquique', 'lat': -20.206, 'lon': -70.149, 'start': 2009},
    {'code': 'pata', 'name': 'Patache', 'lat': -20.801, 'lon': -70.202, 'start': 2012},
    {'code': 'meji', 'name': 'Mejillones', 'lat': -23.097, 'lon': -70.454, 'start': 2012},
    {'code': 'anto', 'name': 'Antofagasta', 'lat': -23.654, 'lon': -70.405, 'start': 2009},
    {'code': 'papo', 'name': 'Paposo', 'lat': -25.010, 'lon': -70.468, 'start': 2014},
    {'code': 'talt', 'name': 'Taltal', 'lat': -25.410, 'lon': -70.485, 'start': 2020},
    {'code': 'chnr', 'name': 'Chañaral', 'lat': -26.351, 'lon': -70.627, 'start': 2013},
    {'code': 'cald', 'name': 'Caldera', 'lat': -27.065, 'lon': -70.825, 'start': 2009},
    {'code': 'coqu', 'name': 'Coquimbo', 'lat': -29.950, 'lon': -71.340, 'start': 2009},
    {'code': 'ptal', 'name': 'Puerto Aldea', 'lat': -30.290, 'lon': -71.613, 'start': 2020},
    {'code': 'pich', 'name': 'Pichidangui', 'lat': -32.137, 'lon': -71.530, 'start': 2019},
    {'code': 'qtro', 'name': 'Quintero', 'lat': -32.779, 'lon': -71.530, 'start': 2018},
    {'code': 'valp', 'name': 'Valparaíso', 'lat': -33.028, 'lon': -71.628, 'start': 2008},
    {'code': 'sano', 'name': 'San Antonio', 'lat': -33.577, 'lon': -71.618, 'start': 2009},
    {'code': 'boye', 'name': 'Boyeruca', 'lat': -34.690, 'lon': -72.055, 'start': 2021},
    {'code': 'const', 'name': 'Constitución', 'lat': -35.355, 'lon': -72.461, 'start': 2011},
    {'code': 'coli', 'name': 'Coliumo', 'lat': -36.545, 'lon': -72.959, 'start': 2020},
    {'code': 'talc', 'name': 'Talcahuano', 'lat': -36.700, 'lon': -73.106, 'start': 2009},
    {'code': 'crnl', 'name': 'Coronel', 'lat': -37.031, 'lon': -73.152, 'start': 2013},
    {'code': 'lebu', 'name': 'Lebu', 'lat': -37.594, 'lon': -73.660, 'start': 2011},
    {'code': 'corr', 'name': 'Corral', 'lat': -39.888, 'lon': -73.432, 'start': 2009},
    {'code': 'bmsa', 'name': 'Bahía Mansa', 'lat': -40.580, 'lon': -73.744, 'start': 2012},
    {'code': 'pmon', 'name': 'Puerto Montt', 'lat': -41.485, 'lon': -72.961, 'start': 2009},
    {'code': 'ancu', 'name': 'Ancud', 'lat': -41.870, 'lon': -73.830, 'start': 2009},
    {'code': 'cstr', 'name': 'Castro', 'lat': -42.480, 'lon': -73.764, 'start': 2012},
    {'code': 'pcha', 'name': 'Puerto Chacabuco', 'lat': -45.470, 'lon': -72.824, 'start': 2009},
    {'code': 'ptar', 'name': 'Punta Arenas', 'lat': -53.120, 'lon': -70.860, 'start': 2012},
    {'code': 'pwil', 'name': 'Puerto Williams', 'lat': -54.933, 'lon': -67.608, 'start': 2009},
    # Added 2026-05-12: 12 additional coastal stations + 5 DART buoys
    {'code': 'toco', 'name': 'Tocopilla', 'lat': -22.0937, 'lon': -70.2115, 'start': 2024},
    {'code': 'huas', 'name': 'Huasco', 'lat': -28.4689, 'lon': -71.2499, 'start': 2024},
    {'code': 'quir', 'name': 'Quiriquina', 'lat': -36.6361, 'lon': -73.0573, 'start': 2014},
    {'code': 'ptch', 'name': 'Punta de Choros', 'lat': -29.2459, 'lon': -71.4687, 'start': 2020},
    {'code': 'ntue', 'name': 'Nehuentúe', 'lat': -38.7499, 'lon': -73.4081, 'start': 2018},
    {'code': 'quel', 'name': 'Queule', 'lat': -39.3976, 'lon': -73.2151, 'start': 2014},
    {'code': 'pmel', 'name': 'Puerto Melinka', 'lat': -43.8985, 'lon': -73.7482, 'start': 2014},
    {'code': 'pagi', 'name': 'Puerto Aguirre', 'lat': -45.1646, 'lon': -73.5211, 'start': 2023},
    {'code': 'pedn', 'name': 'Puerto Edén', 'lat': -49.1298, 'lon': -74.4086, 'start': 2014},
    {'code': 'pnat', 'name': 'Puerto Natales', 'lat': -51.7291, 'lon': -72.5157, 'start': 2023},
    {'code': 'cmet', 'name': 'Caleta Meteoro', 'lat': -52.9610, 'lon': -74.0722, 'start': 2014},
    {'code': 'greg', 'name': 'Bahía Gregorio', 'lat': -52.6481, 'lon': -70.2092, 'start': 2018},
    # DART tsunami buoys (deep-ocean pressure ~4-5 km depth, 15-min sampling)
    {'code': 'dchi', 'name': 'DART West of Iquique', 'lat': -20.4417, 'lon': -73.4217, 'start': 2014},
    {'code': 'dch2', 'name': 'DART West of Antofagasta', 'lat': -23.1694, 'lon': -72.0663, 'start': 2021},
    {'code': 'dcld', 'name': 'DART West of Caldera', 'lat': -26.7448, 'lon': -73.9845, 'start': 2014},
    {'code': 'dval', 'name': 'DART NW of Valparaíso', 'lat': -32.1299, 'lon': -73.7962, 'start': 2021},
    {'code': 'dch3', 'name': 'DART NW of Concepción', 'lat': -35.7470, 'lon': -75.2838, 'start': 2022},
]

OUTPUT_DIR = Path('/tmp/ioc_chile')


def download_month(code, year, month):
    """Download one month of data from IOC API."""
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
    except Exception as e:
        return []


def download_station(station, max_years=10):
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
            if year == end_year - 1 and month > 3:
                # Don't go past March of current year
                break
            data = download_month(code, year, month)
            if data:
                all_data.extend(data)
                sys.stdout.write('.')
                sys.stdout.flush()
            time.sleep(0.15)  # Be polite to the API

    print(f" {len(all_data)} raw points")

    if not all_data:
        print("  No data!")
        return None

    # Aggregate to hourly using nearest-hour rounding.
    # Naïve floor (HH:M -> HH:00 for any M) labels the mean of [HH:00, HH+1:00)
    # at HH:00 — which is actually centered at HH:30 in time. That introduces
    # a 30-min temporal lag, equivalent to a ~14.5° M2-phase bias (Δ=σ·0.5h).
    # Nearest-hour rounding instead labels the mean of [HH-:30, HH+:30) at HH:00,
    # which is genuinely centered on the full hour.
    hourly = {}
    for point in all_data:
        try:
            t = datetime.strptime(point['stime'], '%Y-%m-%d %H:%M:%S')
            hour_key = t.replace(minute=0, second=0)
            if t.minute >= 30:
                hour_key += timedelta(hours=1)
            level = float(point['slevel'])
            if hour_key not in hourly:
                hourly[hour_key] = []
            hourly[hour_key].append(level)
        except (ValueError, KeyError):
            continue

    # Write CSV
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w') as f:
        f.write('time,waterlevel_m\n')
        for t in sorted(hourly.keys()):
            vals = hourly[t]
            mean_val = sum(vals) / len(vals)
            f.write(f"{t.strftime('%Y-%m-%d %H:%M:%S')},{mean_val:.4f}\n")

    print(f"  {len(hourly)} hourly values saved to {output_file}")
    return output_file


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--years', type=int, default=10, help='Max years to download')
    parser.add_argument('--stations', type=str, default='', help='Comma-separated station codes')
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    stations = STATIONS
    if args.stations:
        codes = [c.strip() for c in args.stations.split(',')]
        stations = [s for s in STATIONS if s['code'] in codes]

    print(f"Downloading {len(stations)} Chilean stations (max {args.years} years each)")
    print(f"Output directory: {OUTPUT_DIR}\n")

    for station in stations:
        print(f"\n{'='*50}")
        print(f"{station['name']} ({station['code']}) — {station['lat']:.3f}, {station['lon']:.3f}")
        download_station(station, max_years=args.years)


if __name__ == '__main__':
    main()
