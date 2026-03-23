#!/usr/bin/env python3
"""
UTide harmonic analysis for Belgian tide stations using waterinfo.be data.
10-min observations, TAW datum (Tweede Algemene Waterpassing).
Checkpoint/resume per station. Sorted by waterway.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import json
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

CSV_DIR = Path("/home/oliver/water_levels/Belgium_waterinfo")
CATALOG_PATH = CSV_DIR / "_station_catalog.json"
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_belgium.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_belgium")

USE_LAST_N_YEARS = 19

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


def get_waterway(name):
    """Extract waterway from station name (e.g. 'Antwerpen tij/Zeeschelde' -> 'Zeeschelde')."""
    if 'tij/' in name:
        return name.split('tij/')[-1].strip()
    return 'Unknown'


def load_csv(csv_path, use_last_n_years=None):
    """Load waterinfo CSV (time, waterlevel_m_TAW)."""
    df = pd.read_csv(csv_path, parse_dates=['time'], index_col='time')
    col = [c for c in df.columns if 'waterlevel' in c.lower()][0]
    df = df.rename(columns={col: 'level'})
    df = df.dropna(subset=['level'])

    if len(df) == 0:
        return None, None

    if use_last_n_years is not None:
        cutoff = df.index[-1] - pd.Timedelta(days=use_last_n_years * 365.25)
        df = df[df.index >= cutoff]

    if df.index.tz is not None:
        datetimes_utc = df.index.tz_convert('UTC').tz_localize(None).to_pydatetime()
    else:
        datetimes_utc = df.index.to_pydatetime()

    levels_m = df['level'].values.astype(np.float64)
    return np.array(datetimes_utc), levels_m


def analyze_station(station):
    """Run UTide analysis for one station."""
    code = station['code']
    name = station['name']
    safe_code = code.replace('/', '_').replace(' ', '_')
    checkpoint_file = CHECKPOINT_DIR / f"{safe_code}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        yrs = result['n_obs'] / (6 * 24 * 365.25)
        print(f"  ✓ Checkpoint ({yrs:.1f}J, R²={result['r_squared']:.4f})")
        return result

    csv_path = CSV_DIR / f"{safe_code}.csv"
    if not csv_path.exists():
        print(f"  ✗ Keine CSV-Datei")
        return None

    t0 = time.time()
    datetimes_utc, levels = load_csv(csv_path, use_last_n_years=USE_LAST_N_YEARS)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    lat = float(station.get('lat', 51.0)) if station.get('lat') else 51.0
    lon = float(station.get('lon', 4.0)) if station.get('lon') else 4.0
    years = len(datetimes_utc) / (6 * 24 * 365.25)
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

    recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
    residuals = levels - recon['h']
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    rms_error = np.sqrt(np.mean(residuals**2))

    m2_amp = next((c['amplitude'] for c in constituents if c['name'] == 'M2'), 0)
    k1_amp = next((c['amplitude'] for c in constituents if c['name'] == 'K1'), 0)

    duration = time.time() - t0
    waterway = get_waterway(name)

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
        'waterway': waterway,
        'duration': duration,
        'coef': coef,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    print(f"  R²={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m ({duration:.0f}s)")

    return result


def format_station_block(result):
    station = result['station']
    name = station['name']
    # Extract short name (before "tij/")
    short_name = name.split(' tij/')[0].strip() if ' tij/' in name else name
    lat = float(station.get('lat', 51.0)) if station.get('lat') else 51.0
    lon = float(station.get('lon', 4.0)) if station.get('lon') else 4.0
    waterway = result.get('waterway', '')

    lines = []
    lines.append(f"# Harmonic constants derived from waterinfo.be 10-min observed data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {short_name} ({waterway})")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Belgium")
    lines.append(f"# waterway: {waterway}")
    lines.append(f"# source: Derived from waterinfo.be observed data with UTide harmonic analysis")
    lines.append(f"# station_id_context: HIC-{station['code']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: TAW")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{short_name}, Belgium")
    lines.append(f"+01:00 :Europe/Brussels")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    with open(CATALOG_PATH) as f:
        all_stations = json.load(f)

    # Sort by waterway, then name
    all_stations.sort(key=lambda s: (get_waterway(s['name']), s['name']))

    print("=" * 70)
    print("UTide Harmonic Analysis — Belgium (waterinfo.be)")
    print(f"10-min Beobachtungen, TAW-Datum, letzte {USE_LAST_N_YEARS} Jahre")
    print("=" * 70)
    print(f"Stationen: {len(all_stations)}")
    print()

    results = []
    current_waterway = None

    for i, station in enumerate(all_stations):
        waterway = get_waterway(station['name'])
        if waterway != current_waterway:
            current_waterway = waterway
            print(f"\n{'━'*70}")
            print(f"  {waterway}")
            print(f"{'━'*70}")

        print(f"\n[{i+1}/{len(all_stations)}] {station['code']} | {station['name']}")

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
        print(f"{'Station':<35s} {'Gewässer':<20s} {'Jahre':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s}")
        print(f"{'─'*35} {'─'*20} {'─'*6} {'─'*7} {'─'*7} {'─'*7}")

        for r in results:
            short = r['station']['name'].split(' tij/')[0] if ' tij/' in r['station']['name'] else r['station']['name']
            years = r['n_obs'] / (6 * 24 * 365.25)
            print(f"{short:<35s} {r['waterway']:<20s} {years:>5.1f}  "
                  f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  {r['m2_amp']:>6.4f}")

        print(f"\nGesamt: {len(results)} Stationen")
        avg_r2 = np.mean([r['r_squared'] for r in results])
        print(f"Durchschnittliches R²: {avg_r2:.4f}")


if __name__ == '__main__':
    main()
