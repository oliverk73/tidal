#!/usr/bin/env python3
"""
Generate Harmonic Constants from IOC sea level data for Chilean stations.
Uses UTide for harmonic analysis. Outputs 175 XTide-compatible constituents.

Data source: IOC Sea Level Monitoring Facility (ioc-sealevelmonitoring.org)
Original data provider: SHOA (Servicio Hidrográfico y Oceanográfico de la Armada de Chile)
"""
import numpy as np
from datetime import datetime
from pathlib import Path
import pandas as pd
import utide
import sys

sys.path.insert(0, str(Path(__file__).parent))
from generate_south_africa_harmonics import (
    CONSTITUENTS_175, find_xtide_match, harmonic_analysis_utide,
    read_header_from_template
)

# Station metadata (from IOC and download_ioc_chile.py)
STATIONS = [
    {'code': 'aric', 'name': 'Arica', 'lat': -18.477, 'lon': -70.322},
    {'code': 'pisa', 'name': 'Pisagua', 'lat': -19.597, 'lon': -70.216},
    {'code': 'iqui', 'name': 'Iquique', 'lat': -20.206, 'lon': -70.149},
    {'code': 'pata', 'name': 'Patache', 'lat': -20.801, 'lon': -70.202},
    {'code': 'meji', 'name': 'Mejillones', 'lat': -23.097, 'lon': -70.454},
    {'code': 'anto', 'name': 'Antofagasta', 'lat': -23.654, 'lon': -70.405},
    {'code': 'papo', 'name': 'Paposo', 'lat': -25.010, 'lon': -70.468},
    {'code': 'talt', 'name': 'Taltal', 'lat': -25.410, 'lon': -70.485},
    {'code': 'chnr', 'name': 'Chañaral', 'lat': -26.351, 'lon': -70.627},
    {'code': 'cald', 'name': 'Caldera', 'lat': -27.065, 'lon': -70.825},
    {'code': 'coqu', 'name': 'Coquimbo', 'lat': -29.950, 'lon': -71.340},
    {'code': 'ptal', 'name': 'Puerto Aldea', 'lat': -30.290, 'lon': -71.613},
    {'code': 'pich', 'name': 'Pichidangui', 'lat': -32.137, 'lon': -71.530},
    {'code': 'qtro', 'name': 'Quintero', 'lat': -32.779, 'lon': -71.530},
    {'code': 'valp', 'name': 'Valparaíso', 'lat': -33.028, 'lon': -71.628},
    {'code': 'sano', 'name': 'San Antonio', 'lat': -33.577, 'lon': -71.618},
    {'code': 'boye', 'name': 'Boyeruca', 'lat': -34.690, 'lon': -72.055},
    {'code': 'const', 'name': 'Constitución', 'lat': -35.355, 'lon': -72.461},
    {'code': 'coli', 'name': 'Coliumo', 'lat': -36.545, 'lon': -72.959},
    {'code': 'talc', 'name': 'Talcahuano', 'lat': -36.700, 'lon': -73.106},
    {'code': 'crnl', 'name': 'Coronel', 'lat': -37.031, 'lon': -73.152},
    {'code': 'lebu', 'name': 'Lebu', 'lat': -37.594, 'lon': -73.660},
    {'code': 'corr', 'name': 'Corral', 'lat': -39.888, 'lon': -73.432},
    {'code': 'bmsa', 'name': 'Bahía Mansa', 'lat': -40.580, 'lon': -73.744},
    {'code': 'pmon', 'name': 'Puerto Montt', 'lat': -41.485, 'lon': -72.961},
    {'code': 'ancu', 'name': 'Ancud', 'lat': -41.870, 'lon': -73.830},
    {'code': 'cstr', 'name': 'Castro', 'lat': -42.480, 'lon': -73.764},
    {'code': 'pcha', 'name': 'Puerto Chacabuco', 'lat': -45.470, 'lon': -72.824},
    {'code': 'ptar', 'name': 'Punta Arenas', 'lat': -53.120, 'lon': -70.860},
    {'code': 'pwil', 'name': 'Puerto Williams', 'lat': -54.933, 'lon': -67.608},
]

DATA_DIR = Path('/tmp/ioc_chile')


def load_ioc_csv(csv_path, max_years=10.0):
    """Load hourly IOC data from CSV."""
    df = pd.read_csv(csv_path)
    times = pd.to_datetime(df['time'], utc=True)
    levels = df['waterlevel_m'].values

    # Cut to last max_years
    last_time = times.iloc[-1]
    cutoff = last_time - pd.Timedelta(days=int(max_years * 365.25))
    mask = times >= cutoff
    times = times[mask].reset_index(drop=True)
    levels = levels[mask]

    # Remove NaNs
    valid = ~np.isnan(levels)
    times = times[valid].reset_index(drop=True)
    levels = levels[valid]

    # Remove outliers (> 5 sigma)
    mean_l = np.mean(levels)
    std_l = np.std(levels)
    if std_l > 0:
        valid2 = np.abs(levels - mean_l) < 5 * std_l
        times = times[valid2].reset_index(drop=True)
        levels = levels[valid2]

    dt_list = [pd.Timestamp(t).to_pydatetime().replace(tzinfo=None) for t in times]
    n_obs = len(dt_list)
    if n_obs < 2000:
        return None

    first = dt_list[0]
    last = dt_list[-1]
    years = (last - first).total_seconds() / (365.25 * 86400)
    return {
        'datetimes_utc': np.array(dt_list),
        'levels': np.array(levels),
        'start_time': first, 'end_time': last,
        'n_obs': n_obs, 'years': years,
    }


def format_station_block(station, results, data):
    """Format a single station as XTide harmonics text block."""
    name = station['name']
    full_name = f"{name}, Chile"

    lines = []
    lines.append(f"# Harmonic constants derived from IOC/SHOA sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Chile")
    lines.append(f"# source: Derived from IOC/SHOA data with UTide harmonic analysis")
    lines.append(f"# station_id_context: IOC-{station['code']}-chl-shoa")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Station Datum")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {station['lon']:.6f}")
    lines.append(f"# !latitude: {station['lat']:.6f}")
    lines.append(full_name)
    # IOC data is in UTC → Greenwich phases → meridian +00:00
    lines.append(f"+00:00 :America/Santiago")
    lines.append(f"{results['mean']:.4f} meters")
    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append("x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(lines)


def main():
    output_path = Path('harmonics/utide/harmonics_utide_chile.txt')
    template_path = Path('harmonics/utide/harmonics_utide_south_africa.txt')

    header = read_header_from_template(template_path)
    header = header.replace('South Africa', 'Chile').replace('UHSLC', 'IOC/SHOA')

    blocks = []
    for station in STATIONS:
        code = station['code']
        name = station['name']

        # Find CSV file
        csv_candidates = list(DATA_DIR.glob(f"{code}_*.csv"))
        if not csv_candidates:
            continue

        csv_path = csv_candidates[0]
        print(f"\n{'='*60}")
        print(f"Processing: {name} ({code}) — {csv_path.name}")

        data = load_ioc_csv(csv_path)
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
        for c in results['constituents']:
            if c['name'] == 'M2':
                print(f"  M2: A={c['amplitude']:.4f} m, phase={c['phase']:.1f}°")
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
