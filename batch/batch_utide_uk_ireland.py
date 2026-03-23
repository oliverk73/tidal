#!/usr/bin/env python3
"""
UTide harmonic analysis for UK and Ireland tide stations using UHSLC hourly data.
Uses last 19 years (full nodal cycle) where available.
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

CSV_DIR = Path("/home/oliver/water_levels/UK_UHSLC")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_uk_ireland.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_uk_ie")

USE_LAST_N_YEARS = 19

STATIONS = {
    293: {'name': 'Lerwick', 'lat': 60.154, 'lon': -1.140, 'tz': 'Europe/London', 'country': 'UK'},
    294: {'name': 'Newlyn', 'lat': 50.103, 'lon': -5.543, 'tz': 'Europe/London', 'country': 'UK'},
    295: {'name': 'Stornoway', 'lat': 58.207, 'lon': -5.177, 'tz': 'Europe/London', 'country': 'UK'},
    835: {'name': 'Castletownbere', 'lat': 51.650, 'lon': -9.900, 'tz': 'Europe/Dublin', 'country': 'Ireland'},
    834: {'name': 'Malin Head', 'lat': 55.367, 'lon': -7.333, 'tz': 'Europe/Dublin', 'country': 'Ireland'},
}

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


def load_csv(csv_path, use_last_n_years=19):
    """Load UHSLC CSV (time, waterlevel_m) and return arrays."""
    df = pd.read_csv(csv_path, parse_dates=['time'], index_col='time')
    df = df.dropna(subset=['waterlevel_m'])

    if len(df) == 0:
        return None, None

    if use_last_n_years is not None and len(df) > 0:
        cutoff = df.index[-1] - pd.Timedelta(days=use_last_n_years * 365.25)
        df = df[df.index >= cutoff]

    if df.index.tz is not None:
        datetimes_utc = df.index.tz_convert('UTC').tz_localize(None).to_pydatetime()
    else:
        datetimes_utc = df.index.to_pydatetime()

    levels_m = df['waterlevel_m'].values.astype(np.float64)
    return np.array(datetimes_utc), levels_m


def analyze_station(csv_path, meta, uhslc_id):
    """Run UTide analysis for one station."""
    key = str(uhslc_id)
    checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"

    if checkpoint_file.exists():
        print(f"  ✓ Checkpoint vorhanden, lade...")
        with open(checkpoint_file, 'rb') as f:
            return pickle.load(f)

    t0 = time.time()
    datetimes_utc, levels = load_csv(csv_path, use_last_n_years=USE_LAST_N_YEARS)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    lat = meta['lat']
    years = len(datetimes_utc) / (24 * 365.25)
    print(f"  UTide solve ({len(datetimes_utc)} Beob., {years:.1f} Jahre, lat={lat:.2f})...",
          end='', flush=True)

    coef = utide.solve(
        datetimes_utc, levels, lat=lat,
        nodal=True, trend=False, method='ols',
        conf_int='none', verbose=False, constit=CONSTIT_93,
    )
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
    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            constituents.append({
                'name': name, 'amplitude': r['amplitude'],
                'phase': r['phase'], 'speed': speed,
            })
            n_analyzed += 1
        else:
            constituents.append({
                'name': name, 'amplitude': 0.0, 'phase': 0.0,
                'speed': speed, 'not_analyzed': True,
            })

    # R² via reconstruction
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
        'station_meta': meta,
        'uhslc_id': uhslc_id,
        'duration': duration,
        'coef': coef,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    meta = result['station_meta']
    name = meta['name']
    lat = meta['lat']
    lon = meta['lon']
    country = meta.get('country', 'UK')

    lines = []
    lines.append(f"# Harmonic constants derived from UHSLC hourly sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: {country}")
    lines.append(f"# source: Derived from UHSLC hourly data with UTide harmonic analysis")
    lines.append(f"# station_id_context: UHSLC-{result['uhslc_id']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: LAT")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    if country == 'Ireland':
        lines.append(f"{name}, {country}")
    else:
        lines.append(f"{name}, Scotland" if lat > 56 else f"{name}, England")

    lines.append(f"+00:00 :{meta.get('tz', 'Europe/London')}")
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
    print("UTide Harmonic Analysis — UHSLC Hourly Data (UK + Ireland)")
    print(f"Letzte {USE_LAST_N_YEARS} Jahre (voller Nodalzyklus)")
    print("=" * 70)

    csv_files = sorted(CSV_DIR.glob("*.csv"))
    print(f"CSV-Dateien: {len(csv_files)}")
    for f in csv_files:
        print(f"  {f.name}: {f.stat().st_size / (1024*1024):.1f} MB")
    print()

    results = []

    for uhslc_id, meta in STATIONS.items():
        csv_match = [f for f in csv_files if f.name.startswith(str(uhslc_id))]
        if not csv_match:
            print(f"  ✗ {meta['name']}: Keine CSV-Datei")
            continue

        csv_path = csv_match[0]
        print(f"\n{'─'*70}")
        print(f"  {meta['name']} (UHSLC {uhslc_id}) — {meta.get('country', '')}")

        result = analyze_station(csv_path, meta, uhslc_id)
        if result is None:
            continue

        results.append(result)
        print(f"  R² = {result['r_squared']:.4f}, RMS = {result['rms_error']:.4f} m")
        print(f"  M2 = {result['m2_amp']:.4f} m, K1 = {result['k1_amp']:.4f} m")
        print(f"  Konstituenten: {result['n_analyzed']}, Dauer: {result['duration']:.1f}s")

    # Write harmonics file
    if results:
        header = read_header_from_template(TEMPLATE_PATH)
        print(f"\n\nSchreibe Harmonics-Datei: {OUTPUT_PATH.name}")
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
        print(f"{'Station':<20s} {'Land':>8s} {'Jahre':>6s} {'R²':>7s} {'RMS(m)':>7s} {'M2(m)':>7s} {'K1(m)':>7s}")
        print(f"{'─'*20} {'─'*8} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
        for r in results:
            years = r['n_obs'] / (24 * 365.25)
            print(f"{r['station_meta']['name']:<20s} {r['station_meta'].get('country',''):>8s} "
                  f"{years:>5.1f}  {r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  "
                  f"{r['m2_amp']:>6.4f}  {r['k1_amp']:>6.4f}")


if __name__ == '__main__':
    main()
