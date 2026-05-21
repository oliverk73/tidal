#!/usr/bin/env python3
"""
UTide harmonic analysis for French tide stations using SHOM REFMAR data.
10-min validated observations (source 3), datum: hydrographic zero (≈ LAT).
Checkpoint/resume per station. Sorted by coast.
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

NPZ_DIR = Path("/home/oliver/water_levels/France_SHOM/npz")
CSV_DIR = Path("/home/oliver/water_levels/France_SHOM")  # fallback for old CSVs
CATALOG_PATH = CSV_DIR / "_station_catalog.json"
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_mod.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_france.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_france")

USE_LAST_N_YEARS = 19
MIN_R_SQUARED = 0.60

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


def get_coast(lat, lon):
    """Assign coast region based on coordinates."""
    if lon < -1.0 and lat > 47.5:
        return 'Bretagne'
    elif lon < -1.0 and lat > 45.5:
        return 'Atlantique Sud'
    elif lon < -1.0 and lat <= 45.5:
        return 'Aquitaine'
    elif lon >= -1.0 and lat > 49.0:
        return 'Manche / Mer du Nord'
    elif lon >= -1.0 and lat > 47.5:
        return 'Normandie'
    elif lon >= -1.0 and lat > 45.5:
        return 'Centre-Ouest'
    elif lon >= 3.0 and lat < 44.0:
        return 'Méditerranée'
    elif lon >= 3.0 and lat >= 44.0:
        return 'Méditerranée'
    elif lon >= 8.0:
        return 'Corse'
    else:
        return 'Atlantique'


def load_npz(npz_path, use_last_n_years=None, max_obs=1500000):
    """Load SHOM NPZ (datetimes_utc, levels_m). Downsample if too many obs."""
    d = np.load(npz_path, allow_pickle=True)
    datetimes = d['datetimes_utc'].astype('datetime64[s]')
    levels = d['levels_m'].astype(np.float64)

    # Filter by time BEFORE converting to Python datetime (saves memory)
    if use_last_n_years is not None:
        cutoff = datetimes[-1] - np.timedelta64(int(use_last_n_years * 365.25), 'D')
        mask = datetimes >= cutoff
        datetimes = datetimes[mask]
        levels = levels[mask]

    # Downsample to ~10-min intervals if too many observations
    if len(datetimes) > max_obs:
        step = len(datetimes) // max_obs + 1
        datetimes = datetimes[::step]
        levels = levels[::step]
        print(f" [downsampled ×{step}]", end='', flush=True)

    if len(datetimes) == 0:
        return None, None

    # Convert to Python datetime
    datetimes_py = datetimes.astype(datetime)
    return np.array(datetimes_py), levels


def analyze_station(station):
    """Run UTide analysis for one station."""
    sid = station['shom_id']
    name = station['name']
    checkpoint_file = CHECKPOINT_DIR / f"{sid}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        yrs = result['n_obs'] / (6 * 24 * 365.25)
        print(f"  ✓ Checkpoint ({yrs:.1f}J, R²={result['r_squared']:.4f})")
        return result

    npz_path = NPZ_DIR / f"{sid}.npz"
    if not npz_path.exists():
        print(f"  ✗ Keine NPZ-Datei")
        return None

    t0 = time.time()
    datetimes_utc, levels = load_npz(npz_path, use_last_n_years=USE_LAST_N_YEARS)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    lat = float(station['latitude'])
    lon = float(station['longitude'])
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
    coast = get_coast(lat, lon)

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
        'coast': coast,
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
    name = station['name'].replace('_', ' ').replace('  ', ' ')
    lat = float(station['latitude'])
    lon = float(station['longitude'])
    coast = result.get('coast', '')

    lines = []
    lines.append(f"# Harmonic constants derived from SHOM REFMAR 10-min validated data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: France")
    lines.append(f"# coast: {coast}")
    lines.append(f"# source: Derived from SHOM REFMAR observed data with UTide harmonic analysis")
    lines.append(f"# station_id_context: SHOM-{station['shom_id']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: ZH")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, France")
    # UTide gets UTC timestamps -> coef['g'] are Greenwich phases, so the
    # meridian must be +00:00 (not +01:00). Europe/Paris is only the display
    # zone. Mislabelling as +01:00 shifts XTide predictions ~1.5 h too early.
    lines.append(f"+00:00 :Europe/Paris")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="Comma-separated SHOM IDs to process (default: all NPZ)")
    args = ap.parse_args()
    id_filter = set(args.ids.split(",")) if args.ids else None

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    # Discover stations from NPZ files
    available = []
    for npz_path in sorted(NPZ_DIR.glob("*.npz")):
        if id_filter and npz_path.stem not in id_filter:
            continue
        d = np.load(npz_path, allow_pickle=True)
        sid = str(d['station_id'])
        name = str(d['name'])
        lat = float(d['latitude'])
        lon = float(d['longitude'])
        s = {
            'shom_id': sid,
            'name': name,
            'latitude': lat,
            'longitude': lon,
        }
        s['_coast'] = get_coast(lat, lon)
        available.append(s)

    # Sort by coast, then name
    available.sort(key=lambda s: (s['_coast'], s['name']))

    print("=" * 70)
    print("UTide Harmonic Analysis — France (SHOM REFMAR)")
    print(f"10-min validierte Beobachtungen, ZH-Datum, letzte {USE_LAST_N_YEARS} Jahre")
    print("=" * 70)
    print(f"Stationen mit Daten: {len(available)}")
    print()

    results = []
    current_coast = None

    for i, station in enumerate(available):
        coast = station['_coast']
        if coast != current_coast:
            current_coast = coast
            print(f"\n{'━'*70}")
            print(f"  {coast}")
            print(f"{'━'*70}")

        print(f"\n[{i+1}/{len(available)}] {station['shom_id']} | {station['name']}")

        result = analyze_station(station)
        if result is not None:
            results.append(result)

    # Write harmonics file (only R² >= MIN_R_SQUARED and >= 0.95 year of data)
    MIN_YEARS = 0.95
    good_results = [r for r in results
                    if r['r_squared'] >= MIN_R_SQUARED
                    and r['n_obs'] / (6 * 24 * 365.25) >= MIN_YEARS
                    and r['m2_amp'] < 20.0]  # filter unrealistic amplitudes
    skipped = [r for r in results if r not in good_results]

    if skipped:
        print(f"\n\nHerausgefiltert (R² < {MIN_R_SQUARED}):")
        for r in skipped:
            name = r['station']['name']
            print(f"  {name}: R²={r['r_squared']:.4f}")

    if good_results:
        header = read_header_from_template(TEMPLATE_PATH)
        print(f"\n\n{'='*70}")
        print(f"Schreibe Harmonics-Datei: {OUTPUT_PATH.name}")
        with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
            f.write(header)
            f.write('\n')
            for result in good_results:
                block = format_station_block(result)
                f.write(block)
                f.write('\n')
        print(f"  {len(good_results)} Stationen, {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")

    # Summary
    if results:
        print(f"\n\n{'='*70}")
        print("ZUSAMMENFASSUNG")
        print(f"{'='*70}")
        print(f"{'Station':<35s} {'Küste':<22s} {'Jahre':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s}")
        print(f"{'─'*35} {'─'*22} {'─'*6} {'─'*7} {'─'*7} {'─'*7}")

        for r in results:
            name = r['station']['name'].replace('_', ' ')
            if len(name) > 34:
                name = name[:31] + '...'
            years = r['n_obs'] / (6 * 24 * 365.25)
            marker = ' ✗' if r['r_squared'] < MIN_R_SQUARED else ''
            print(f"{name:<35s} {r['coast']:<22s} {years:>5.1f}  "
                  f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  {r['m2_amp']:>6.4f}{marker}")

        print(f"\nGesamt: {len(results)} analysiert, {len(good_results)} in Datei (R² ≥ {MIN_R_SQUARED})")
        avg_r2 = np.mean([r['r_squared'] for r in good_results])
        print(f"Durchschnittliches R²: {avg_r2:.4f}")


if __name__ == '__main__':
    main()
