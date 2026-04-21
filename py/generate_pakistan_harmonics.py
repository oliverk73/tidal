#!/usr/bin/env python3
"""
Generate Harmonic Constants for Pakistan: Karachi (UHSLC), Gwadar + Ormara (IOC SLSMF).
Pattern follows generate_south_africa_harmonics.py.
"""
import numpy as np
from datetime import datetime
from pathlib import Path
import pandas as pd
import utide

from generate_south_africa_harmonics import (
    CONSTITUENTS_175, UTIDE_TO_XTIDE_NAME, XTIDE_BY_SPEED,
    find_xtide_match, load_csv_water_levels, harmonic_analysis_utide,
    read_header_from_template,
)

DATA_DIR = Path('/home/oliver/water_levels/Pakistan')

STATIONS = [
    {'file': 'uhslc_147_Karachi.csv',  'name': 'Karachi', 'lat': 24.812, 'lon': 66.975, 'country': 'Pakistan', 'source': 'UHSLC-147', 'max_years': 10.0},
    {'file': 'ioc_gwda_Gwadar.csv',    'name': 'Gwadar',  'lat': 25.1122, 'lon': 62.3394, 'country': 'Pakistan', 'source': 'IOC-gwda',  'max_years': 10.0},
    # Ormara dropped: R²=0.49, IOC data too gappy for reliable UTide fit
]


def format_station_block(station, results, data):
    name = station['name']
    country = station['country']
    full_name = f"{name}, {country}"
    lines = []
    lines.append(f"# Harmonic constants derived from {station['source']} sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: {country}")
    lines.append(f"# source: Derived from {station['source']} data with UTide harmonic analysis")
    lines.append(f"# station_id_context: {station['source']}")
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
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_pakistan.txt')

    print("=" * 70)
    print("Generate Pakistan Harmonics with UTide")
    print("=" * 70)

    header = read_header_from_template(template_path)
    station_blocks = []
    processed = 0

    for i, station in enumerate(STATIONS):
        csv_path = DATA_DIR / station['file']
        name = station['name']
        print(f"\n[{i+1}/{len(STATIONS)}] {name} ({station['source']})...", end='', flush=True)
        if not csv_path.exists():
            print(" NO FILE")
            continue
        data = load_csv_water_levels(str(csv_path), max_years=station['max_years'])
        if data is None:
            print(" INSUFFICIENT")
            continue
        print(f" {data['n_obs']} obs ({data['years']:.1f}y)", flush=True)
        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print(" ANALYSIS FAILED")
            continue
        station_blocks.append(format_station_block(station, results, data))
        m2 = next((c['amplitude'] for c in results['constituents'] if c['name'] == 'M2'), 0)
        print(f"  R²={results['r_squared']:.3f}, M2={m2:.3f}m, constit={results['n_analyzed']}")
        processed += 1

    print(f"\n{'='*70}")
    print(f"Processed: {processed}/{len(STATIONS)}")
    if not station_blocks:
        return

    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for block in station_blocks:
            f.write(block)
            f.write('\n')
    print(f"Wrote {output_path} ({processed} stations)")


if __name__ == '__main__':
    main()
