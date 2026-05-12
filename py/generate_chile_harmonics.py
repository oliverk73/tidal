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
    # Added 2026-05-12: 12 additional coastal stations + 5 DART buoys
    {'code': 'toco', 'name': 'Tocopilla', 'lat': -22.0937, 'lon': -70.2115},
    {'code': 'huas', 'name': 'Huasco', 'lat': -28.4689, 'lon': -71.2499},
    {'code': 'quir', 'name': 'Quiriquina', 'lat': -36.6361, 'lon': -73.0573},
    {'code': 'ptch', 'name': 'Punta de Choros', 'lat': -29.2459, 'lon': -71.4687},
    {'code': 'ntue', 'name': 'Nehuentúe', 'lat': -38.7499, 'lon': -73.4081},
    {'code': 'quel', 'name': 'Queule', 'lat': -39.3976, 'lon': -73.2151},
    {'code': 'pmel', 'name': 'Puerto Melinka', 'lat': -43.8985, 'lon': -73.7482},
    {'code': 'pagi', 'name': 'Puerto Aguirre', 'lat': -45.1646, 'lon': -73.5211},
    {'code': 'pedn', 'name': 'Puerto Edén', 'lat': -49.1298, 'lon': -74.4086},
    {'code': 'pnat', 'name': 'Puerto Natales', 'lat': -51.7291, 'lon': -72.5157},
    {'code': 'cmet', 'name': 'Caleta Meteoro', 'lat': -52.9610, 'lon': -74.0722},
    {'code': 'greg', 'name': 'Bahía Gregorio', 'lat': -52.6481, 'lon': -70.2092},
    # DART tsunami buoys — offshore, deep ocean
    {'code': 'dchi', 'name': 'DART West of Iquique', 'lat': -20.4417, 'lon': -73.4217},
    {'code': 'dch2', 'name': 'DART West of Antofagasta', 'lat': -23.1694, 'lon': -72.0663},
    {'code': 'dcld', 'name': 'DART West of Caldera', 'lat': -26.7448, 'lon': -73.9845},
    {'code': 'dval', 'name': 'DART NW of Valparaíso', 'lat': -32.1299, 'lon': -73.7962},
    {'code': 'dch3', 'name': 'DART NW of Concepción', 'lat': -35.7470, 'lon': -75.2838},
]

# Stations to retry with a post-earthquake window (2016+) — previous full-history
# fits had R² < 0.5 due to large vertical jumps from 2010/2014/2015 quakes.
RETRY_WINDOW_START = {
    'pisa':  '2016-01-01',
    'meji':  '2016-01-01',
    'const': '2016-01-01',
}

# DART buoys: deep-ocean pressure (not a sea-level dataset). Override datum.
DART_CODES = {'dchi', 'dch2', 'dcld', 'dval', 'dch3'}

DATA_DIR = Path('/tmp/ioc_chile')

# Stations already in harmonics_utide_observations.txt — skip to avoid duplicate work.
# (Per user instruction 2026-05-11: don't reprocess stations already covered by UTide.)
SKIP_EXISTING_UTIDE = {
    'iqui',  # Iquique
    'coqu',  # Coquimbo
    'sano',  # San Antonio
    'talc',  # Talcahuano
    'corr',  # Corral
    'ancu',  # Ancud
    'pcha',  # Puerto Chacabuco
    'ptar',  # Punta Arenas
}


def load_ioc_csv(csv_path, max_years=10.0, start_date=None, is_dart=False):
    """Load hourly IOC data from CSV.

    start_date: optional ISO date string (e.g. "2016-01-01") — overrides max_years
    by clamping to >= start_date. Used to skip pre-earthquake data.
    is_dart: if True, apply DART-specific cleaning (median window filter + detrend
    against rolling median) since DART buoys have multi-meter deployment jumps.
    """
    df = pd.read_csv(csv_path)
    times = pd.to_datetime(df['time'], utc=True)
    levels = df['waterlevel_m'].values

    if start_date is not None:
        cutoff = pd.Timestamp(start_date, tz='UTC')
    else:
        last_time = times.iloc[-1]
        cutoff = last_time - pd.Timedelta(days=int(max_years * 365.25))
    mask = times >= cutoff
    times = times[mask].reset_index(drop=True)
    levels = levels[mask]

    # Remove NaNs
    valid = ~np.isnan(levels)
    times = times[valid].reset_index(drop=True)
    levels = levels[valid]

    if is_dart:
        # DART buoys sit at ~4 km depth; absolute pressure changes by meters
        # between deployments. Step 1: drop any sample > 5 m from the global
        # median (gross outliers, sensor errors). Step 2: subtract a 30-day
        # rolling median to remove inter-deployment drift while preserving
        # sub-daily tidal signal. Result: tidal-only residual centered on zero.
        median = np.median(levels)
        keep = np.abs(levels - median) < 5.0
        times = times[keep].reset_index(drop=True)
        levels = levels[keep]
        s = pd.Series(levels, index=times)
        rolling = s.rolling('30D', center=True, min_periods=24).median()
        levels = (s - rolling).values
        valid2 = ~np.isnan(levels)
        times = times[valid2].reset_index(drop=True)
        levels = levels[valid2]
    else:
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
    code = station['code']
    is_dart = code in DART_CODES
    # DART buoys aren't in Chilean waters proper; suffix " (DART)" disambiguates
    # them in search results from a real port and tells users this is offshore.
    full_name = f"{name}, Chile"
    if is_dart:
        datum_label = 'Seafloor (DART pressure sensor depth)'
        source_label = 'NDBC DART buoy via IOC; UTide harmonic analysis'
        station_id = f"IOC-{code}-dart"
    else:
        datum_label = 'Station Datum'
        source_label = 'IOC/SHOA data; UTide harmonic analysis'
        station_id = f"IOC-{code}-chl-shoa"

    lines = []
    lines.append(f"# Harmonic constants derived from IOC sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    lines.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {full_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Chile")
    lines.append(f"# source: {source_label}")
    lines.append(f"# station_id_context: {station_id}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: {datum_label}")
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


R2_MIN = 0.50  # Quality cut — below this we reject the harmonic fit


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--only-new', action='store_true',
                        help='Only process stations not in harmonics_utide_observations.txt')
    parser.add_argument('--output', default='/home/oliver/harmonics/utide/harmonics_utide_chile_v2.txt',
                        help='Output path for harmonics file')
    args = parser.parse_args()

    output_path = Path(args.output)
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')

    header = read_header_from_template(template_path)

    # Which station names are already present in observations.txt? We re-fit only
    # the stations the user is asking about (not the full STATIONS list).
    existing_names = set()
    if args.only_new:
        with open(template_path, 'r', encoding='latin-1') as f:
            for line in f:
                if line.startswith('# ') or line.startswith('#') or '!' in line[:8]:
                    continue
                stripped = line.strip()
                if stripped.endswith(', Chile'):
                    existing_names.add(stripped)

    blocks = []
    rejected = []
    for station in STATIONS:
        code = station['code']
        name = station['name']
        full_name = f"{name}, Chile"

        if code in SKIP_EXISTING_UTIDE:
            print(f"\n--- Skipping {name} ({code}): already in UTide observations ---")
            continue
        if args.only_new and full_name in existing_names and code not in RETRY_WINDOW_START:
            print(f"\n--- Skipping {full_name}: already in observations.txt ---")
            continue

        # Find CSV file
        csv_candidates = list(DATA_DIR.glob(f"{code}_*.csv"))
        if not csv_candidates:
            print(f"\n--- No CSV for {name} ({code}), skipping ---")
            continue

        csv_path = csv_candidates[0]
        print(f"\n{'='*60}")
        print(f"Processing: {name} ({code}) — {csv_path.name}")

        # Apply retry window if this station previously had a bad fit
        retry_start = RETRY_WINDOW_START.get(code)
        is_dart = code in DART_CODES
        if retry_start:
            print(f"  Retry window: starting at {retry_start}")
            data = load_ioc_csv(csv_path, start_date=retry_start, is_dart=is_dart)
        else:
            data = load_ioc_csv(csv_path, is_dart=is_dart)
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

        if results['r_squared'] < R2_MIN:
            print(f"  REJECTED: R² {results['r_squared']:.3f} < {R2_MIN}")
            rejected.append((full_name, results['r_squared']))
            continue

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

    if rejected:
        print(f"\nRejected (R² < {R2_MIN}):")
        for n, r in rejected:
            print(f"  {n}: R²={r:.3f}")


if __name__ == '__main__':
    main()
