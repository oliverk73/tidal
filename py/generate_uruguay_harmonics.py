#!/usr/bin/env python3
"""
Generate Harmonic Constants from DINAGUA (Uruguay) water level data.
Uses UTide for harmonic analysis. Outputs 175 XTide-compatible constituents.

Data source: https://catalogodatos.gub.uy/
DINAGUA = Dirección Nacional de Aguas, Uruguay
"""
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import utide
import csv
import sys

# Import shared constituent list from South Africa script
sys.path.insert(0, str(Path(__file__).parent))
from generate_south_africa_harmonics import (
    CONSTITUENTS_175, find_xtide_match, harmonic_analysis_utide,
    read_header_from_template
)

# Uruguay coastal stations with coordinates
STATIONS = [
    {'id': '0900', 'name': 'La Paloma', 'lat': -34.6539, 'lon': -54.1461,
     'tz_offset': -3, 'iana_tz': 'America/Montevideo'},
    {'id': '0830', 'name': 'Punta del Este', 'lat': -34.9667, 'lon': -54.9500,
     'tz_offset': -3, 'iana_tz': 'America/Montevideo'},
    {'id': '0920', 'name': 'Puerto Colonia', 'lat': -34.4700, 'lon': -57.8400,
     'tz_offset': -3, 'iana_tz': 'America/Montevideo'},
    {'id': '1300', 'name': 'Juan Lacaze', 'lat': -34.4333, 'lon': -57.4500,
     'tz_offset': -3, 'iana_tz': 'America/Montevideo'},
    {'id': '1910', 'name': 'Barra del Chuy', 'lat': -33.7467, 'lon': -53.4572,
     'tz_offset': -3, 'iana_tz': 'America/Montevideo'},
    {'id': '0190', 'name': 'Carmelo', 'lat': -34.0033, 'lon': -58.2833,
     'tz_offset': -3, 'iana_tz': 'America/Montevideo'},
    {'id': '0380', 'name': 'Nueva Palmira', 'lat': -33.8767, 'lon': -58.4167,
     'tz_offset': -3, 'iana_tz': 'America/Montevideo'},
]

DATA_DIR = Path('/tmp')
CSV_FILES = [
    DATA_DIR / 'uruguay_nivel_2017.csv',
    DATA_DIR / 'uruguay_nivel_2018.csv',
    DATA_DIR / 'uruguay_nivel_2019.csv',
]


def parse_dinagua_csv(filepath):
    """Parse DINAGUA CSV, handling 2018's different quoting format."""
    rows = []
    with open(filepath, 'r', encoding='latin-1') as f:
        content = f.read()

    lines = content.strip().split('\n')
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        if line.startswith('"') and ',""' in line:
            # 2018 format: "field1,""field2"",""field3""..."
            line = line.strip('"')
            parts = line.split(',""')
            parts = [p.strip('"') for p in parts]
            if len(parts) >= 6:
                rows.append(parts)
        else:
            try:
                parsed = list(csv.reader([line]))[0]
                if len(parsed) >= 6:
                    rows.append(parsed)
            except:
                continue
    return rows


def load_station_data(station_id, tz_offset):
    """Load and combine all years of data for a station, convert to UTC."""
    all_times = []
    all_levels = []

    for csv_file in CSV_FILES:
        if not csv_file.exists():
            continue
        rows = parse_dinagua_csv(csv_file)
        for row in rows:
            if row[0].strip() != station_id:
                continue
            try:
                val = float(row[3].strip())
                date_str = row[5].strip()
                # DINAGUA timestamps are already in UTC (verified by
                # correlation analysis against SOHMA official predictions)
                utc_time = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                all_times.append(utc_time)
                all_levels.append(val)
            except (ValueError, IndexError):
                continue

    if len(all_times) < 2000:
        return None

    # Sort by time
    pairs = sorted(zip(all_times, all_levels))
    times = np.array([p[0] for p in pairs])
    levels = np.array([p[1] for p in pairs])

    # Remove duplicates (keep last)
    _, unique_idx = np.unique(times, return_index=True)
    times = times[unique_idx]
    levels = levels[unique_idx]

    # Remove obvious outliers (> 5 sigma from mean)
    mean_level = np.mean(levels)
    std_level = np.std(levels)
    valid = np.abs(levels - mean_level) < 5 * std_level
    times = times[valid]
    levels = levels[valid]

    first = times[0]
    last = times[-1]
    years = (last - first).total_seconds() / (365.25 * 86400)

    return {
        'datetimes_utc': times,
        'levels': levels,
        'start_time': first,
        'end_time': last,
        'n_obs': len(times),
        'years': years,
    }


def format_station_block(station, results, data):
    """Format a single station as XTide harmonics text block."""
    name = station['name']
    full_name = f"{name}, Uruguay"
    tz_offset = station['tz_offset']
    iana_tz = station['iana_tz']

    # Phases are Greenwich (UTC input to UTide) → meridian +00:00
    meridian = "+00:00"

    lines = []
    lines.append(f"# Harmonic constants derived from DINAGUA sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Uruguay")
    lines.append(f"# source: Derived from DINAGUA data with UTide harmonic analysis")
    lines.append(f"# station_id_context: DINAGUA-{station['id']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Station Datum")
    lines.append(f"# confidence: 6")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {station['lon']:.6f}")
    lines.append(f"# !latitude: {station['lat']:.6f}")
    lines.append(full_name)
    lines.append(f"{meridian} :{iana_tz}")
    lines.append(f"{results['mean']:.4f} meters")
    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append("x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(lines)


def main():
    output_path = Path('harmonics/utide/harmonics_utide_uruguay.txt')
    template_path = Path('harmonics/utide/harmonics_utide_south_africa.txt')

    # Read header from template
    header = read_header_from_template(template_path)
    header = header.replace('South Africa', 'Uruguay').replace('UHSLC', 'DINAGUA')

    blocks = []
    for station in STATIONS:
        print(f"\n{'='*60}")
        print(f"Processing: {station['name']} (ID: {station['id']})")

        data = load_station_data(station['id'], station['tz_offset'])
        if data is None:
            print(f"  Insufficient data, skipping.")
            continue

        print(f"  {data['n_obs']} observations, {data['years']:.1f} years")
        print(f"  {data['start_time']} to {data['end_time']}")

        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print(f"  Analysis failed, skipping.")
            continue

        print(f"  R² = {results['r_squared']:.4f}, RMS = {results['rms_error']:.4f} m")
        print(f"  {results['n_analyzed']} constituents analyzed")
        print(f"  M2: ", end='')
        for c in results['constituents']:
            if c['name'] == 'M2':
                print(f"A={c['amplitude']:.4f} m, phase={c['phase']:.1f}°")
                break

        blocks.append(format_station_block(station, results, data))

    if blocks:
        with open(output_path, 'w', encoding='latin-1') as f:
            f.write(header)
            for block in blocks:
                f.write('\n' + block + '\n')
        print(f"\n{'='*60}")
        print(f"Written {len(blocks)} stations to {output_path}")
    else:
        print("\nNo stations analyzed successfully!")


if __name__ == '__main__':
    main()
