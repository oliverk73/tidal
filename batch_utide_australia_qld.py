#!/usr/bin/env python3
"""
UTide harmonic analysis for Australian tide stations using BOM ABSLMP data.
Hourly observations, AHD datum. Checkpoint/resume per station.
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

NPZ_DIR = Path("/home/oliver/water_levels/Australia_QLD/npz")
TEMPLATE_PATH = Path("/home/oliver/harmonics_working/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics_working/harmonics_utide_australia_qld.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics_working/checkpoints_au_qld")

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


def load_npz(npz_path, use_last_n_years=None, max_obs=1500000):
    """Load NPZ (datetimes_utc, levels_m). Downsample if too many obs."""
    d = np.load(npz_path, allow_pickle=True)
    datetimes = d['datetimes_utc'].astype('datetime64[s]')
    levels = d['levels_m'].astype(np.float64)

    if use_last_n_years is not None:
        cutoff = datetimes[-1] - np.timedelta64(int(use_last_n_years * 365.25), 'D')
        mask = datetimes >= cutoff
        datetimes = datetimes[mask]
        levels = levels[mask]

    if len(datetimes) > max_obs:
        step = len(datetimes) // max_obs + 1
        datetimes = datetimes[::step]
        levels = levels[::step]
        print(f" [downsampled ×{step}]", end='', flush=True)

    if len(datetimes) == 0:
        return None, None

    datetimes_py = datetimes.astype(datetime)
    return np.array(datetimes_py), levels


def analyze_station(station):
    """Run UTide analysis for one station."""
    sid = station['station_id']
    name = station['name']
    checkpoint_file = CHECKPOINT_DIR / f"{sid}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        yrs = result['n_obs'] / (6 * 24 * 365.25)
        print(f"  ✓ Checkpoint ({yrs:.1f}J, R²={result['r_squared']:.4f})")
        return result

    # NPZ files are named by station name, not ID
    npz_path = station.get('_npz_path')
    if npz_path is None or not npz_path.exists():
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
    station = result['station']
    name = station['name']
    lat = float(station['latitude'])
    lon = float(station['longitude'])

    lines = []
    lines.append(f"# Harmonic constants derived from QLD MSQ 10-min observation data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Australia")
    lines.append(f"# source: Derived from QLD MSQ observed data with UTide harmonic analysis")
    lines.append(f"# station_id_context: QLD-{station['station_id']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: LAT")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, Australia")
    lines.append(f"+10:00 :Australia/Brisbane")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    available = []
    for npz_path in sorted(NPZ_DIR.glob("*.npz")):
        d = np.load(npz_path, allow_pickle=True)
        sid = str(d['station_id'])
        name = str(d['name'])
        lat = float(d['latitude'])
        lon = float(d['longitude'])
        available.append({
            'station_id': sid,
            'name': name,
            'latitude': lat,
            'longitude': lon,
            '_npz_path': npz_path,
        })

    available.sort(key=lambda s: s['name'])

    print("=" * 70)
    print("UTide Harmonic Analysis — Australia (QLD MSQ)")
    print(f"10-min Beobachtungen, LAT-Datum, letzte {USE_LAST_N_YEARS} Jahre")
    print("=" * 70)
    print(f"Stationen mit Daten: {len(available)}\n")

    results = []
    for i, station in enumerate(available):
        print(f"\n[{i+1}/{len(available)}] {station['station_id']} | {station['name']}")
        result = analyze_station(station)
        if result is not None:
            results.append(result)

    MIN_YEARS = 1.0
    good_results = [r for r in results
                    if r['r_squared'] >= MIN_R_SQUARED
                    and r['n_obs'] / (6 * 24 * 365.25) >= MIN_YEARS
                    and r['m2_amp'] < 20.0]
    skipped = [r for r in results if r not in good_results]

    if skipped:
        print(f"\n\nHerausgefiltert:")
        for r in skipped:
            print(f"  {r['station']['name']}: R²={r['r_squared']:.4f}")

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

    if results:
        print(f"\n\n{'='*70}")
        print("ZUSAMMENFASSUNG")
        print(f"{'='*70}")
        print(f"{'Station':<35s} {'Jahre':>5s}  {'R²':>6s}  {'RMS':>6s}  {'M2':>6s}")
        print(f"{'─'*35} {'─'*5}  {'─'*6}  {'─'*6}  {'─'*6}")
        for r in results:
            name = r['station']['name'][:35]
            yrs = r['n_obs'] / (6 * 24 * 365.25)
            marker = '' if r in good_results else ' ✗'
            print(f"{name:<35s} {yrs:>5.1f}  {r['r_squared']:>5.4f}  "
                  f"{r['rms_error']:>5.4f}  {r['m2_amp']:>5.4f}{marker}")

        good_r2 = [r['r_squared'] for r in good_results] if good_results else [0]
        print(f"\nGesamt: {len(results)} analysiert, {len(good_results)} in Datei (R² ≥ {MIN_R_SQUARED})")
        print(f"Durchschnittliches R²: {np.mean(good_r2):.4f}")


if __name__ == '__main__':
    main()
