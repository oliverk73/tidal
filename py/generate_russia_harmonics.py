#!/usr/bin/env python3
"""
Generate harmonic constants for Russian Pacific coast stations from IOC SLSMF data.
"""
from datetime import datetime
from pathlib import Path
import pandas as pd
import utide

from generate_south_africa_harmonics import (
    load_csv_water_levels, harmonic_analysis_utide, read_header_from_template,
)

DATA_DIR = Path('/home/oliver/water_levels/Russia_IOC')
R2_MIN = 0.5  # drop stations below this (weak tidal signal / gappy data)

STATIONS = [
    {'code': 'khol', 'name': 'Kholmsk',             'lat': 47.0506, 'lon': 142.0439},
    {'code': 'kors', 'name': 'Korsakov',            'lat': 46.6333, 'lon': 142.7667},
    {'code': 'kuri', 'name': "Kuril'sk",            'lat': 45.2300, 'lon': 147.8800},
    {'code': 'naho', 'name': 'Nakhodka',            'lat': 42.7800, 'lon': 132.8600},
    {'code': 'nksk', 'name': "Nikol'skoe",          'lat': 55.2000, 'lon': 166.0200},
    {'code': 'petr', 'name': 'Petropavlovsk',       'lat': 53.0167, 'lon': 158.6500},
    {'code': 'poro', 'name': 'Poronajsk',           'lat': 49.2200, 'lon': 143.0900},
    {'code': 'posi', 'name': "Pos'et",              'lat': 42.6500, 'lon': 130.8000},
    {'code': 'preo', 'name': 'Preobrazheniye',      'lat': 42.9092, 'lon': 133.9225},
    {'code': 'rudn', 'name': 'Rudnaya Pristan',     'lat': 44.3500, 'lon': 135.8000},
    {'code': 'sosu', 'name': 'Sosunovo',            'lat': 46.5300, 'lon': 138.3300},
    {'code': 'sove', 'name': "Sovetskaya Gavan'",   'lat': 48.9700, 'lon': 140.2900},
    {'code': 'star', 'name': 'Starodubskoe',        'lat': 47.4100, 'lon': 142.8200},
    {'code': 'ugle', 'name': 'Uglegorsk',           'lat': 49.0800, 'lon': 142.0700},
    {'code': 'vlad', 'name': 'Vladivostok',         'lat': 43.1300, 'lon': 131.9200},
]


def format_station_block(station, results, data):
    name = station['name']
    full_name = f"{name}, Russia"
    src = f"IOC-{station['code']}"
    lines = []
    lines.append(f"# Harmonic constants derived from {src} sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Russia")
    lines.append(f"# source: Derived from {src} data with UTide harmonic analysis")
    lines.append(f"# station_id_context: {src}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {station['lon']:.6f}")
    lines.append(f"# !latitude: {station['lat']:.6f}")
    lines.append(full_name)
    lines.append(f"+00:00 :UTC")
    lines.append(f"{results['mean']:.4f} meters")
    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(lines)


def main():
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt')
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_russia.txt')
    print("=" * 70)
    print("Generate Russia Harmonics with UTide")
    print("=" * 70)
    header = read_header_from_template(template_path)
    blocks = []
    for i, s in enumerate(STATIONS):
        safe = s['name'].replace(' ', '_').replace("'", '').replace('.', '').replace(',', '')
        csv_path = DATA_DIR / f"ioc_{s['code']}_{safe}.csv"
        print(f"\n[{i+1}/{len(STATIONS)}] {s['name']} ({s['code']})...", end='', flush=True)
        if not csv_path.exists():
            print(" NO FILE")
            continue
        data = load_csv_water_levels(str(csv_path), max_years=3.0)
        if data is None:
            print(" INSUFFICIENT")
            continue
        print(f" {data['n_obs']} obs ({data['years']:.1f}y)", flush=True)
        res = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], s['lat'])
        if res is None:
            print(" ANALYSIS FAILED")
            continue
        m2 = next((c['amplitude'] for c in res['constituents'] if c['name'] == 'M2'), 0)
        if res['r_squared'] < R2_MIN:
            print(f"  R²={res['r_squared']:.3f}, M2={m2:.3f}m — DROP (below {R2_MIN})")
            continue
        blocks.append((s, res, format_station_block(s, res, data)))
        print(f"  R²={res['r_squared']:.3f}, M2={m2:.3f}m, constit={res['n_analyzed']}")

    print(f"\n{'='*70}\nStations: {len(blocks)}/{len(STATIONS)}")
    print("\nQuality summary (sorted by R²):")
    for s, res, _ in sorted(blocks, key=lambda x: x[1]['r_squared']):
        m2 = next((c['amplitude'] for c in res['constituents'] if c['name'] == 'M2'), 0)
        print(f"  R²={res['r_squared']:.3f}  M2={m2:.3f}m  {s['name']}")

    if not blocks:
        return
    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for _, _, b in blocks:
            f.write(b)
            f.write('\n')
    print(f"\nWrote {output_path}")


if __name__ == '__main__':
    main()
