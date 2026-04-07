#!/usr/bin/env python3
"""
UTide harmonic analysis for Indian tide stations from IOC sea level data.
Hourly CSV data, checkpoint/resume per station.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import pickle
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

DATA_DIR = Path("/home/oliver/water_levels/India_IOC")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_mod.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_india.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_india")

CONSTIT_93 = [
    'J1', 'K1', 'O1', 'OO1', 'P1', 'Q1', '2Q1', 'RHO1', 'ALP1', 'BET1',
    'CHI1', 'NO1', 'PHI1', 'PI1', 'PSI1', 'SIG1', 'SO1', 'THE1', '2PO1',
    'TAU1', 'UPS1',
    'K2', 'L2', 'M2', 'N2', '2N2', 'R2', 'S2', 'T2', 'LDA2', 'MU2',
    'NU2', 'EPS2', 'ETA2', '2SM2', '2NS2', 'SKM2', 'OP2', 'MKS2', 'MSN2',
    'OQ2',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3', 'NO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4', 'N4', 'SL4', '3MS4',
    '2MK5', '2SK5', '2MO5', 'MNO5', 'MSK5', '3KM5', '2MP5', '3MP5', 'MNK5',
    'M6', '2MN6', '2MS6', '2MK6', '2NM6', '2SM6', 'MSK6', 'MSN6', 'S6',
    'M7', '3MK7',
    'M8', '3MN8', '3MS8', '3MK8',
    '4MK9', 'M10', 'M12',
    'H1', 'H2', 'S1',
]

# Station definitions matching download_india_ioc.py
STATIONS = [
    {'code': 'chenn', 'name': 'Chennai',        'lat': 13.0827, 'lon': 80.2707, 'state': 'Tamil Nadu'},
    {'code': 'vish',  'name': 'Visakhapatnam',   'lat': 17.6868, 'lon': 83.2785, 'state': 'Andhra Pradesh'},
    {'code': 'ptbl',  'name': 'Port Blair',      'lat': 11.6834, 'lon': 92.7518, 'state': 'Andaman and Nicobar'},
    {'code': 'marm',  'name': 'Marmagao',        'lat': 15.4177, 'lon': 73.7990, 'state': 'Goa'},
    {'code': 'coch',  'name': 'Cochin',          'lat':  9.9312, 'lon': 76.2673, 'state': 'Kerala'},
    {'code': 'veer',  'name': 'Veraval',         'lat': 20.9009, 'lon': 70.3634, 'state': 'Gujarat'},
    {'code': 'mini',  'name': 'Minicoy',         'lat':  8.2744, 'lon': 73.0431, 'state': 'Lakshadweep'},
    {'code': 'okha',  'name': 'Okha',            'lat': 22.4667, 'lon': 69.0833, 'state': 'Gujarat'},
    {'code': 'kand',  'name': 'Kandla',          'lat': 23.0333, 'lon': 70.2167, 'state': 'Gujarat'},
    {'code': 'para',  'name': 'Paradip',         'lat': 20.2644, 'lon': 86.6275, 'state': 'Odisha'},
    # Mangalore: IOC data unusable (sensor offset, no tidal signal)
    # {'code': 'mang',  'name': 'Mangalore',       'lat': 12.8475, 'lon': 74.8199, 'state': 'Karnataka'},
    {'code': 'tuti',  'name': 'Tuticorin',       'lat':  8.7642, 'lon': 78.1348, 'state': 'Tamil Nadu'},
    {'code': 'mumb',  'name': 'Mumbai',          'lat': 18.9067, 'lon': 72.8147, 'state': 'Maharashtra'},
]


def load_ioc_csv(station):
    """Load IOC CSV hourly sea level data."""
    code = station['code']
    name = station['name'].lower().replace(' ', '_')
    filepath = DATA_DIR / f"{code}_{name}.csv"

    if not filepath.exists():
        print(f"  Datei nicht gefunden: {filepath}")
        return None, None

    df = pd.read_csv(filepath, parse_dates=['datetime_utc'])
    df = df.dropna(subset=['level_m'])
    n_raw = len(df)

    # Remove spikes: per-month median ± 4*IQR
    df['month_key'] = df['datetime_utc'].dt.to_period('M')
    clean_idx = []
    for _, grp in df.groupby('month_key'):
        q25, q75 = grp['level_m'].quantile([0.25, 0.75])
        iqr = q75 - q25
        mask = (grp['level_m'] >= q25 - 4 * iqr) & (grp['level_m'] <= q75 + 4 * iqr)
        clean_idx.extend(grp[mask].index)
    df = df.loc[clean_idx].drop(columns=['month_key'])

    # Remove years with datum jumps (mean deviates >2σ from median of yearly means)
    df['year'] = df['datetime_utc'].dt.year
    yearly_stats = df.groupby('year')['level_m'].agg(['mean', 'std', 'count'])
    yearly_stats = yearly_stats[yearly_stats['count'] > 500]  # need enough data
    if len(yearly_stats) > 2:
        median_mean = yearly_stats['mean'].median()
        median_std = yearly_stats['std'].median()
        threshold = max(2.0 * median_std, 0.5)
        good_years = yearly_stats[abs(yearly_stats['mean'] - median_mean) <= threshold].index
        n_before = len(df)
        df = df[df['year'].isin(good_years)]
        if len(df) < n_before:
            print(f"  [{n_before - len(df)} Werte aus {len(yearly_stats) - len(good_years)} Jahren mit Datum-Offset entfernt]",
                  end='', flush=True)
    df = df.drop(columns=['year'])

    n_clean = len(df)
    if n_clean < n_raw:
        print(f"  [Bereinigt: {n_raw} → {n_clean}]", end='', flush=True)

    if n_clean < 2000:
        print(f"  Zu wenig Daten ({n_clean} Werte)")
        return None, None

    datetimes = df['datetime_utc'].values.astype('datetime64[ns]')
    datetimes_py = pd.to_datetime(datetimes).to_pydatetime()
    levels = df['level_m'].values.astype(np.float64)

    return np.array(datetimes_py), levels


def analyze_station(station):
    """Run UTide analysis for one IOC station."""
    code = station['code']
    checkpoint_file = CHECKPOINT_DIR / f"{code}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        yrs = result['n_obs'] / (24 * 365.25)
        print(f"  ✓ Checkpoint ({yrs:.1f}J, R²={result['r_squared']:.4f})")
        return result

    t0 = time.time()
    datetimes_utc, levels = load_ioc_csv(station)

    if datetimes_utc is None:
        return None

    lat = station['lat']
    years = len(datetimes_utc) / (24 * 365.25)
    print(f"  UTide solve ({len(datetimes_utc)} Beob., {years:.1f}J, lat={lat:.2f})...",
          end='', flush=True)

    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_93,
        )
    except Exception as e:
        print(f" FEHLER: {e}")
        return None

    print(" OK", flush=True)

    # Map to XTide 175 constituents
    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amplitude = coef['A'][i]
        greenwich_phase = coef['g'][i]

        if uname in utide_all_names:
            idx = utide_all_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue

        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue

        utide_results[xt_name] = {
            'amplitude': amplitude,
            'phase': greenwich_phase % 360,
            'speed': xt_speed,
        }

    constituents = []
    n_analyzed = 0
    for cname, speed in CONSTITUENTS_175:
        if cname in utide_results:
            r = utide_results[cname]
            constituents.append({
                'name': cname, 'amplitude': r['amplitude'],
                'phase': r['phase'], 'speed': speed,
            })
            n_analyzed += 1
        else:
            constituents.append({
                'name': cname, 'amplitude': 0.0, 'phase': 0.0,
                'speed': speed, 'not_analyzed': True,
            })

    # R²
    recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
    residuals = levels - recon['h']
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    rms_error = np.sqrt(np.mean(residuals**2))

    m2_amp = next((c['amplitude'] for c in constituents if c['name'] == 'M2'), 0)
    k1_amp = next((c['amplitude'] for c in constituents if c['name'] == 'K1'), 0)

    duration = time.time() - t0

    result = {
        'mean': coef['mean'],
        'constituents': constituents,
        'n_analyzed': n_analyzed,
        'r_squared': r_squared,
        'rms_error': rms_error,
        'm2_amp': m2_amp,
        'k1_amp': k1_amp,
        'n_obs': len(datetimes_utc),
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'station': station,
        'duration': duration,
        'coef': coef,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    print(f"  R²={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m ({duration:.0f}s)")

    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    station = result['station']
    name = station['name']
    lat = station['lat']
    lon = station['lon']
    state = station.get('state', 'India')

    lines = []
    lines.append(f"# Harmonic constants derived from IOC Sea Level Monitoring hourly data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: India")
    lines.append(f"# region: {state}")
    lines.append(f"# source: Derived from IOC Sea Level Monitoring data with UTide harmonic analysis")
    lines.append(f"# station_id_context: IOC-{station['code']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: unspecified")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, {state}, India")
    lines.append(f"+05:30 :Asia/Kolkata")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("UTide Harmonic Analysis — Indian Stations (IOC Sea Level Monitoring)")
    print("Hourly data, UTC")
    print("=" * 70)
    print(f"Stationen: {len(STATIONS)}")
    print()

    results = []

    for i, station in enumerate(STATIONS):
        print(f"\n[{i+1}/{len(STATIONS)}] {station['code']} | {station['name']} "
              f"({station['lat']:.4f}, {station['lon']:.4f})")

        result = analyze_station(station)
        if result is not None:
            results.append(result)

    # Write harmonics file
    if results:
        header = read_header_from_template(TEMPLATE_PATH)
        print(f"\n\n{'='*70}")
        print(f"Schreibe Harmonics-Datei: {OUTPUT_PATH.name}")
        with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
            f.write(header)
            f.write('\n')
            for result in results:
                block = format_station_block(result)
                f.write(block)
                f.write('\n')
        print(f"  {len(results)} Stationen, {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")

    # Summary
    if results:
        print(f"\n\n{'='*70}")
        print("ZUSAMMENFASSUNG")
        print(f"{'='*70}")
        print(f"{'Station':<25s} {'Region':<20s} {'Jahre':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s} {'K1':>7s}")
        print(f"{'─'*25} {'─'*20} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

        for r in results:
            years = r['n_obs'] / (24 * 365.25)
            print(f"{r['station']['name']:<25s} {r['station']['state']:<20s} {years:>5.1f}  "
                  f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  "
                  f"{r['m2_amp']:>6.4f}  {r['k1_amp']:>6.4f}")

        print(f"\nGesamt: {len(results)} Stationen erfolgreich")
        avg_r2 = np.mean([r['r_squared'] for r in results])
        print(f"Durchschnittliches R²: {avg_r2:.4f}")


if __name__ == '__main__':
    main()
