#!/usr/bin/env python3
"""
Generate Harmonic Constants from UHSLC hourly water level data for Papua New Guinea.
Uses UTide for harmonic analysis. Outputs 175 XTide-compatible constituents.
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

STATIONS = [
    {'uhslc_id':  10, 'name': 'Rabaul',              'lat':  -4.200, 'lon': 152.175, 'country': 'Papua New Guinea'},
    {'uhslc_id':  48, 'name': 'Anewa Bay',           'lat':  -6.183, 'lon': 155.883, 'country': 'Papua New Guinea'},
    {'uhslc_id':  63, 'name': 'Wewak',               'lat':  -3.570, 'lon': 143.633, 'country': 'Papua New Guinea'},
    {'uhslc_id':  64, 'name': 'Port Moresby',        'lat':  -9.478, 'lon': 147.140, 'country': 'Papua New Guinea'},
    {'uhslc_id':  65, 'name': 'Manus',               'lat':  -2.013, 'lon': 147.272, 'country': 'Papua New Guinea'},
    {'uhslc_id':  66, 'name': 'Madang',              'lat':  -5.200, 'lon': 145.800, 'country': 'Papua New Guinea'},
    {'uhslc_id':  67, 'name': 'Lae',                 'lat':  -6.733, 'lon': 146.983, 'country': 'Papua New Guinea'},
    {'uhslc_id':  68, 'name': 'Kavieng',             'lat':  -2.585, 'lon': 150.795, 'country': 'Papua New Guinea'},
    {'uhslc_id':  69, 'name': 'Alotau',              'lat': -10.317, 'lon': 150.453, 'country': 'Papua New Guinea'},
    {'uhslc_id': 400, 'name': 'Lombrum, Manus Is.',  'lat':  -2.037, 'lon': 147.375, 'country': 'Papua New Guinea'},
]


def format_station_block(station, results, data):
    name = station['name']
    country = station['country']
    full_name = f"{name}, {country}"
    lines = []
    lines.append(f"# Harmonic constants derived from UHSLC sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: {country}")
    lines.append(f"# source: Derived from UHSLC data with UTide harmonic analysis")
    lines.append(f"# station_id_context: UHSLC-{station['uhslc_id']}")
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
    data_dir = Path('/home/oliver/water_levels/PapuaNewGuinea_UHSLC')
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt')
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_png.txt')

    print("=" * 70)
    print("Generate Papua New Guinea Harmonics with UTide")
    print("=" * 70)

    print(f"\nReading header from {template_path.name}...")
    header = read_header_from_template(template_path)

    csv_files = {int(f.name.split('_')[0]): f for f in data_dir.glob('*.csv')}
    print(f"Found {len(csv_files)} CSV files")
    print(f"\nProcessing {len(STATIONS)} stations...\n")

    station_blocks = []
    processed = 0
    failed = 0

    for i, station in enumerate(STATIONS):
        sid = station['uhslc_id']
        name = station['name']
        print(f"[{i+1}/{len(STATIONS)}] {name} (UHSLC {sid})...", end='', flush=True)

        if sid not in csv_files:
            print(" NO DATA FILE")
            failed += 1
            continue

        data = load_csv_water_levels(str(csv_files[sid]), max_years=10.0)
        if data is None:
            print(" INSUFFICIENT DATA")
            failed += 1
            continue

        print(f" {data['n_obs']} obs ({data['years']:.1f}y)...", end='', flush=True)

        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print(" ANALYSIS FAILED")
            failed += 1
            continue

        block = format_station_block(station, results, data)
        station_blocks.append(block)

        m2_amp = 0
        for c in results['constituents']:
            if c['name'] == 'M2':
                m2_amp = c['amplitude']
                break

        print(f" OK (R²={results['r_squared']:.3f}, M2={m2_amp:.3f}m, constit={results['n_analyzed']})")
        processed += 1

    print(f"\n{'='*70}")
    print(f"Processed: {processed}, Failed: {failed}")

    if not station_blocks:
        print("No stations processed.")
        return

    print(f"\nWriting output to {output_path}...")
    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for block in station_blocks:
            f.write(block)
            f.write('\n')

    print(f"Done! Created {output_path}")
    print(f"Total stations: {len(station_blocks)}")


if __name__ == "__main__":
    main()
