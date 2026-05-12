#!/usr/bin/env python3
"""
Generate UTide harmonics for Adriatic stations:
- Trieste (UHSLC FD id=829, Italy, North Adriatic, M2 ~25 cm)
- Sobra (IOC, Croatia, Mljet, South Adriatic)
- Stari Grad (IOC, Croatia, Hvar, Central Adriatic)

Mid/South Adriatic is microtidal (M2 5-10 cm) — DART-style 30-day rolling-
median detrend to remove storm-surge baseline drift.
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
    {'code': 'trie',  'name': 'Trieste',     'country': 'Italy',   'lat': 45.647,  'lon': 13.760,  'tz': 'Europe/Rome'},
    {'code': 'sobr',  'name': 'Sobra',       'country': 'Croatia', 'lat': 42.793,  'lon': 17.620,  'tz': 'Europe/Zagreb'},
    {'code': 'stari', 'name': 'Stari Grad',  'country': 'Croatia', 'lat': 43.181,  'lon': 16.576,  'tz': 'Europe/Zagreb'},
]

DATA_DIR = Path('/tmp/adria')
R2_MIN = 0.40


def load_csv(csv_path, max_years=12.0, detrend_window_days=30):
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
    median = np.median(levels)
    keep = np.abs(levels - median) < 3.0
    times = times[keep].reset_index(drop=True)
    levels = levels[keep]
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
    first = dt_list[0]; last = dt_list[-1]
    years = (last - first).total_seconds() / (365.25 * 86400)
    return {
        'datetimes_utc': np.array(dt_list),
        'levels': np.array(levels),
        'start_time': first, 'end_time': last,
        'n_obs': n_obs, 'years': years,
    }


def format_station_block(station, results, data):
    name = station['name']
    country = station['country']
    full_name = f"{name}, {country}"
    L = []
    L.append("# Harmonic constants derived from IOC/UHSLC sea level data")
    L.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    L.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    L.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    L.append(f"# Constituents analyzed: {results['n_analyzed']}")
    L.append("#")
    L.append(f"# {full_name}")
    L.append("# BEGIN HOT COMMENTS")
    L.append(f"# country: {country}")
    src = 'UHSLC Fast Delivery' if station['code'] == 'trie' else 'IOC sea level data'
    L.append(f"# source: {src}; UTide harmonic analysis")
    L.append(f"# station_id_context: {station['code']}-{country.lower()[:2]}")
    L.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    L.append("# datum: Station Datum (detrended residual)")
    L.append("# confidence: 7")
    L.append("# !units: meters")
    L.append(f"# !longitude: {station['lon']:.6f}")
    L.append(f"# !latitude: {station['lat']:.6f}")
    L.append(full_name)
    L.append(f"+00:00 :{station['tz']}")
    L.append(f"{results['mean']:.4f} meters")
    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append("x 0 0")
        else:
            L.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(L)


def main():
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_adria.txt')
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
    header = read_header_from_template(template_path)
    blocks = []
    rejected = []
    for station in STATIONS:
        code = station['code']
        files = list(DATA_DIR.glob(f"{code}_*.csv"))
        if not files:
            print(f"-- no CSV for {code}")
            continue
        print(f"\n{'='*60}\n{station['name']}, {station['country']} ({code})")
        data = load_csv(files[0])
        if data is None:
            print("  Insufficient data")
            continue
        print(f"  {data['n_obs']} obs, {data['years']:.1f}y")
        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print("  fit failed")
            continue
        print(f"  R²={results['r_squared']:.4f}, RMS={results['rms_error']:.4f} m")
        for c in results['constituents']:
            if c['name'] == 'M2':
                print(f"  M2: A={c['amplitude']:.4f} m, phase={c['phase']:.1f}°")
                break
        if results['r_squared'] < R2_MIN:
            print(f"  REJECTED R²<{R2_MIN}")
            rejected.append((f"{station['name']}, {station['country']}", results['r_squared']))
            continue
        blocks.append(format_station_block(station, results, data))
    if blocks:
        with open(output_path, 'w', encoding='latin-1') as f:
            f.write(header)
            for b in blocks:
                f.write('\n' + b + '\n')
        print(f"\nWrote {len(blocks)} stations to {output_path}")
    if rejected:
        print(f"\nRejected: {rejected}")


if __name__ == '__main__':
    main()
