#!/usr/bin/env python3
"""
Download monthly tide-table PDFs from CICESE (Mexico) for stations not yet
covered by our UTide observations. PDFs are at predmar.cicese.mx and contain
HW/LW (Pleamar/Bajamar) extremes for one month, 4 events/day.

Usage:
  python3 download_cicese_mexico.py [--year YYYY] [--stations a,b,c]
"""
import sys
import time
import urllib.request
from pathlib import Path

OUTPUT_DIR = Path('/home/oliver/weather/tide_tables/mexico_cicese')
BASE_URL = 'https://predmar.cicese.mx/calmen/pdf'

# 18 stations from CICESE not already in our UTide observations.
# Stars (⭐) are Mar de Cortés priority.
STATIONS = [
    {'code': 'alv', 'name': 'Alvarado',              'state': 'Veracruz',           'lat': 18.78,  'lon':  -95.76},
    {'code': 'byt', 'name': 'Puerto Bayeto',         'state': 'Nayarit',            'lat': 21.61,  'lon': -106.51},
    {'code': 'cal', 'name': 'Calica',                'state': 'Quintana Roo',       'lat': 20.56,  'lon':  -87.13},
    {'code': 'coz', 'name': 'Cozumel',               'state': 'Quintana Roo',       'lat': 20.51,  'lon':  -86.95},
    {'code': 'ctz', 'name': 'Coatzacoalcos',         'state': 'Veracruz',           'lat': 18.15,  'lon':  -94.41},
    {'code': 'fro', 'name': 'Frontera',              'state': 'Tabasco',            'lat': 18.53,  'lon':  -92.65},
    {'code': 'grn', 'name': 'Guerrero Negro',        'state': 'Baja California Sur','lat': 27.88,  'lon': -114.15},
    {'code': 'gsc', 'name': 'Golfo de Santa Clara',  'state': 'Sonora',             'lat': 31.70,  'lon': -114.50},  # ⭐
    {'code': 'hua', 'name': 'Huatulco',              'state': 'Oaxaca',             'lat': 15.66,  'lon':  -96.40},
    {'code': 'mat', 'name': 'Matamoros',             'state': 'Tamaulipas',         'lat': 25.88,  'lon':  -97.51},
    {'code': 'muj', 'name': 'Isla Mujeres',          'state': 'Quintana Roo',       'lat': 21.30,  'lon':  -86.50},
    {'code': 'ptp', 'name': 'Puerto Peñasco',        'state': 'Sonora',             'lat': 31.30,  'lon': -113.55},  # ⭐
    {'code': 'rfg', 'name': 'Puerto Refugio',        'state': 'Baja California',    'lat': 29.58,  'lon': -113.58},  # ⭐
    {'code': 'snb', 'name': 'San Blas',              'state': 'Nayarit',            'lat': 21.61,  'lon': -106.51},
    {'code': 'str', 'name': 'Santa Rosalía',         'state': 'Baja California Sur','lat': 27.25,  'lon': -112.20},  # ⭐
    {'code': 'szl', 'name': 'El Sauzal',             'state': 'Baja California',    'lat': 31.91,  'lon': -116.70},
    {'code': 'tib', 'name': 'Isla Tiburón',          'state': 'Sonora',             'lat': 28.78,  'lon': -112.46},  # ⭐
    {'code': 'txp', 'name': 'Tuxpam',                'state': 'Veracruz',           'lat': 20.71,  'lon':  -97.16},
]


def download_pdf(code, year, month):
    """Download single PDF, return path on success."""
    yy = year % 100
    fname = f"{code}{yy:02d}{month:02d}.pdf"
    out = OUTPUT_DIR / code / fname
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 100_000:
        return out
    url = f"{BASE_URL}/{code}/{fname}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'TideResearch/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 1000:
            return None
        with open(out, 'wb') as f:
            f.write(data)
        return out
    except Exception as e:
        print(f"    {fname}: {e}")
        return None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=2026)
    ap.add_argument('--stations', type=str, default='')
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stations = STATIONS
    if args.stations:
        codes = [c.strip() for c in args.stations.split(',')]
        stations = [s for s in STATIONS if s['code'] in codes]

    print(f"Downloading {args.year} for {len(stations)} CICESE stations")
    print(f"Output: {OUTPUT_DIR}")
    for i, s in enumerate(stations):
        code = s['code']; name = s['name']
        print(f"\n[{i+1}/{len(stations)}] {name} ({code}):", flush=True)
        ok = 0
        for m in range(1, 13):
            p = download_pdf(code, args.year, m)
            if p:
                sys.stdout.write('.'); sys.stdout.flush()
                ok += 1
            else:
                sys.stdout.write('!')
            time.sleep(0.5)
        print(f" {ok}/12")
    print(f"\nDone. Files in {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
