#!/usr/bin/env python3
"""
Generate harmonic constants for 7 Russian Far East stations from IOC data.

Modeled on generate_chile_harmonics.py. Inputs from /tmp/ioc_russia/.
Output: appendable harmonics file in iso-8859-1.
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

STATIONS = [
    {'code': 'khol', 'name': 'Kholmsk',          'lat': 47.0506, 'lon': 142.0439},
    {'code': 'kors', 'name': 'Korsakov',         'lat': 46.6333, 'lon': 142.7667},
    {'code': 'kuri', 'name': "Kuril'sk",         'lat': 45.2300, 'lon': 147.8800},
    {'code': 'poro', 'name': 'Poronajsk',        'lat': 49.2200, 'lon': 143.0900},
    {'code': 'preo', 'name': 'Preobrazheniye',   'lat': 42.9092, 'lon': 133.9225},
    {'code': 'rudn', 'name': 'Rudnaya Pristan',  'lat': 44.3500, 'lon': 135.8000},
    {'code': 'sosu', 'name': 'Sosunovo',         'lat': 46.5300, 'lon': 138.3300},
]

DATA_DIR = Path('/tmp/ioc_russia')
R2_MIN = 0.50


def load_ioc_csv(csv_path, max_years=12.0, detrend_window_days=30):
    """Load + filter. Sea of Japan stations are microtidal (M2 = 5-20 cm),
    so non-tidal noise (storm surge, baseline drift) easily dominates. We
    subtract a rolling median to remove sub-tidal drift while preserving
    the harmonic signal (which has periods << detrend_window).
    """
    df = pd.read_csv(csv_path)
    times = pd.to_datetime(df['time'], utc=True)
    levels = df['waterlevel_m'].values
    last_time = times.iloc[-1]
    cutoff = last_time - pd.Timedelta(days=int(max_years * 365.25))
    mask = times >= cutoff
    times = times[mask].reset_index(drop=True)
    levels = levels[mask]
    valid = ~np.isnan(levels)
    times = times[valid].reset_index(drop=True)
    levels = levels[valid]
    # Drop gross outliers tighter than 5σ — these RU stations have spikes
    # to multiple meters from typhoons / sensor errors.
    median = np.median(levels)
    keep = np.abs(levels - median) < 3.0  # ±3 m around median
    times = times[keep].reset_index(drop=True)
    levels = levels[keep]
    # Rolling-median detrend (like DART)
    if detrend_window_days > 0:
        s = pd.Series(levels, index=times)
        rolling = s.rolling(f'{detrend_window_days}D', center=True, min_periods=24).median()
        levels = (s - rolling).values
        valid2 = ~np.isnan(levels)
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
    name = station['name']
    full_name = f"{name}, Russia"
    L = []
    L.append("# Harmonic constants derived from IOC sea level data")
    L.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    L.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    L.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    L.append(f"# Constituents analyzed: {results['n_analyzed']}")
    L.append("#")
    L.append(f"# {full_name}")
    L.append("# BEGIN HOT COMMENTS")
    L.append("# country: Russia")
    L.append("# source: IOC sea level data; UTide harmonic analysis")
    L.append(f"# station_id_context: IOC-{station['code']}-rus")
    L.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    L.append("# datum: Station Datum")
    L.append("# confidence: 7")
    L.append("# !units: meters")
    L.append(f"# !longitude: {station['lon']:.6f}")
    L.append(f"# !latitude: {station['lat']:.6f}")
    L.append(full_name)
    L.append("+00:00 :Asia/Vladivostok")
    L.append(f"{results['mean']:.4f} meters")
    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append("x 0 0")
        else:
            L.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(L)


def main():
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_russia_v2.txt')
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
    header = read_header_from_template(template_path)
    blocks = []
    rejected = []
    for station in STATIONS:
        code = station['code']
        name = station['name']
        full_name = f"{name}, Russia"
        files = list(DATA_DIR.glob(f"{code}_*.csv"))
        if not files:
            print(f"-- No CSV for {name} ({code})")
            continue
        csv_path = files[0]
        print(f"\n{'='*60}\nProcessing: {name} ({code}) — {csv_path.name}")
        data = load_ioc_csv(csv_path)
        if data is None:
            print("  Insufficient data, skipping.")
            continue
        print(f"  {data['n_obs']} obs, {data['years']:.1f}y, {data['start_time']} → {data['end_time']}")
        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print("  Analysis failed.")
            continue
        print(f"  R²={results['r_squared']:.4f}, RMS={results['rms_error']:.4f} m, {results['n_analyzed']} constituents")
        for c in results['constituents']:
            if c['name'] == 'M2':
                print(f"  M2: A={c['amplitude']:.4f} m, phase={c['phase']:.1f}°")
                break
        if results['r_squared'] < R2_MIN:
            print(f"  REJECTED R²<{R2_MIN}")
            rejected.append((full_name, results['r_squared']))
            continue
        blocks.append(format_station_block(station, results, data))
    if blocks:
        with open(output_path, 'w', encoding='latin-1') as f:
            f.write(header)
            for block in blocks:
                f.write('\n' + block + '\n')
        print(f"\nWrote {len(blocks)} stations to {output_path}")
    if rejected:
        print(f"\nRejected (R²<{R2_MIN}):")
        for n, r in rejected:
            print(f"  {n}: {r:.3f}")


if __name__ == '__main__':
    main()
