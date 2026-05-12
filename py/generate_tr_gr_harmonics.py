#!/usr/bin/env python3
"""
Generate harmonic constants for Turkey + Greece IOC stations.

Mediterranean stations are microtidal (~5-20 cm). Detrend with 30-day
rolling median to remove storm-surge baseline drift.
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
from download_ioc_tr_gr import STATIONS

DATA_DIR = Path('/tmp/ioc_tr_gr')
R2_MIN = 0.40  # Mediterranean microtidal → noise floor higher


def load_ioc_csv(csv_path, max_years=10.0, detrend_window_days=30):
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
    tz_zone = 'Europe/Istanbul' if country == 'Turkey' else 'Europe/Athens'
    L = []
    L.append("# Harmonic constants derived from IOC sea level data")
    L.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations")
    L.append(f"# from {data['start_time'].strftime('%Y-%m-%d')} to {data['end_time'].strftime('%Y-%m-%d')}")
    L.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    L.append(f"# Constituents analyzed: {results['n_analyzed']}")
    L.append("#")
    L.append(f"# {full_name}")
    L.append("# BEGIN HOT COMMENTS")
    L.append(f"# country: {country}")
    L.append("# source: IOC sea level data; UTide harmonic analysis")
    L.append(f"# station_id_context: IOC-{station['code']}-{country.lower()[:2]}")
    L.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    L.append("# datum: Station Datum (detrended residual)")
    L.append("# confidence: 7")
    L.append("# !units: meters")
    L.append(f"# !longitude: {station['lon']:.6f}")
    L.append(f"# !latitude: {station['lat']:.6f}")
    L.append(full_name)
    L.append(f"+00:00 :{tz_zone}")
    L.append(f"{results['mean']:.4f} meters")
    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            L.append("x 0 0")
        else:
            L.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")
    return '\n'.join(L)


def main():
    output_path = Path('/home/oliver/harmonics/utide/harmonics_utide_tr_gr.txt')
    template_path = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
    header = read_header_from_template(template_path)
    blocks = []
    rejected = []
    no_data = []
    for station in STATIONS:
        code = station['code']; name = station['name']
        country = station['country']
        full_name = f"{name}, {country}"
        files = list(DATA_DIR.glob(f"{code}_*.csv"))
        if not files:
            no_data.append(full_name)
            continue
        csv_path = files[0]
        print(f"\n{'='*60}\nProcessing: {full_name} ({code})")
        data = load_ioc_csv(csv_path)
        if data is None:
            print("  Insufficient data, skipping.")
            no_data.append(full_name)
            continue
        print(f"  {data['n_obs']} obs, {data['years']:.1f}y")
        results = harmonic_analysis_utide(data['datetimes_utc'], data['levels'], station['lat'])
        if results is None:
            print("  Analysis failed.")
            continue
        print(f"  R²={results['r_squared']:.4f}, RMS={results['rms_error']:.4f} m")
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
            for b in blocks:
                f.write('\n' + b + '\n')
        print(f"\n{'='*60}\nWrote {len(blocks)} stations to {output_path}")
    print(f"\nNo data: {len(no_data)}")
    for n in no_data:
        print(f"  {n}")
    if rejected:
        print(f"\nRejected (R²<{R2_MIN}):")
        for n, r in rejected:
            print(f"  {n}: {r:.3f}")


if __name__ == '__main__':
    main()
