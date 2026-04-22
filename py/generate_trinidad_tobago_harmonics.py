#!/usr/bin/env python3
"""
Generate XTide-compatible harmonic constants for Trinidad & Tobago tide stations
from UHSLC Research Quality hourly sea-level data using UTide.

Stations (UHSLC):
  - 248 Port of Spain, Trinidad and Tobago
  - 728 Point Fortin,  Trinidad and Tobago
"""
import numpy as np
from datetime import datetime
from pathlib import Path
import pandas as pd
import utide

UHSLC_STATIONS = [
    {'uhslc_id': 248, 'name': 'Port of Spain', 'country': 'Trinidad and Tobago',
     'lat': 10.6500, 'lon': -61.5170, 'water': 'Gulf of Paria / Caribbean Sea',
     'csv': '/home/oliver/water_levels/TrinidadTobago_UHSLC/h248_port_of_spain.csv'},
    {'uhslc_id': 728, 'name': 'Point Fortin', 'country': 'Trinidad and Tobago',
     'lat': 10.1900, 'lon': -61.6890, 'water': 'Gulf of Paria / Caribbean Sea',
     'csv': '/home/oliver/water_levels/TrinidadTobago_UHSLC/h728_point_fortin.csv'},
]

from generate_caribbean_harmonics import (
    CONSTITUENTS_175, find_xtide_match, load_uhslc_csv,
    harmonic_analysis_utide, read_header_from_template,
)


def format_station_block(station, results, data, source_label):
    name = station['name']
    full_name = f"{name}, {station['country']}"
    lines = []
    lines.append(f"# Harmonic constants derived from {source_label}")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: {station['country']}")
    lines.append(f"# water body: {station['water']}")
    lines.append(f"# source: Derived from UHSLC data with UTide harmonic analysis")
    lines.append(f"# station_id_context: UHSLC-{station['uhslc_id']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {station['lon']:.6f}")
    lines.append(f"# !latitude: {station['lat']:.6f}")
    lines.append(full_name)
    lines.append(f"+00:00 :UTC")
    lines.append(f"0.0000 meters")
    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(lines)


def main():
    template_path = Path('/home/oliver/harmonics/template/harmonics_template.txt')
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_trinidad_tobago.txt')

    print("=" * 70)
    print("Generate Trinidad & Tobago Harmonics with UTide (UHSLC RQ)")
    print("=" * 70)

    header = read_header_from_template(template_path)
    station_blocks = []
    processed = 0
    failed = 0

    for station in UHSLC_STATIONS:
        sid = station['uhslc_id']
        name = station['name']
        print(f"\n[UHSLC-{sid}] {name}...")

        csv_path = Path(station['csv'])
        if not csv_path.exists():
            print(f"  NO DATA FILE: {csv_path}")
            failed += 1
            continue

        data = load_uhslc_csv(csv_path)
        if data is None:
            print("  INSUFFICIENT DATA")
            failed += 1
            continue

        print(f"  {data['n_obs']} obs ({data['years']:.1f}y) from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
        print(f"  Running UTide...", end='', flush=True)

        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print(" FAILED")
            failed += 1
            continue

        m2 = next((c['amplitude'] for c in results['constituents'] if c['name'] == 'M2'), 0)
        m2p = next((c['phase'] for c in results['constituents'] if c['name'] == 'M2'), 0)
        print(f" OK (R^2={results['r_squared']:.3f}, M2={m2:.3f}m@{m2p:.1f}deg, constit={results['n_analyzed']})")

        block = format_station_block(station, results, data, "UHSLC sea level data")
        station_blocks.append(block)
        processed += 1

    print(f"\n{'='*70}")
    print(f"Processed: {processed}, Failed: {failed}")

    if not station_blocks:
        print("No stations processed!")
        return

    print(f"\nWriting {len(station_blocks)} stations to {output_path}...")
    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for block in station_blocks:
            f.write(block)
            f.write('\n')

    print(f"Done! {output_path}")


if __name__ == "__main__":
    main()
