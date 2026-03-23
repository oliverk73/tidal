#!/usr/bin/env python3
"""
Batch UTide harmonic analysis for Dutch tide stations (Rijkswaterstaat).
Reads CSV files from water_levels/Netherlands/, runs UTide with 93 constituents,
maps to 175 XTide constituents, outputs XTide-compatible harmonics file.

Features:
- Checkpoint/resume: saves each station result to disk immediately
- On restart, skips already-completed stations
- Multiprocessing for speed
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time
import pickle
import utide
from multiprocessing import Pool

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    UTIDE_TO_XTIDE_NAME,
    find_xtide_match,
    read_header_from_template,
)

CSV_DIR = Path("/home/oliver/water_levels/Netherlands")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_netherlands.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_nl")

USE_LAST_N_YEARS = 19  # Full nodal cycle (18.61 years)
N_WORKERS = 3

# 93 constituents (same as German stations analysis)
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
    """Load RWS CSV and return datetime + meters arrays."""
    df = pd.read_csv(csv_path, parse_dates=['time'], index_col='time')

    # Drop NaN values
    df = df.dropna(subset=['waterlevel_cm_NAP'])

    if len(df) == 0:
        return None, None

    # Use last N years
    if use_last_n_years is not None:
        cutoff = df.index[-1] - pd.Timedelta(days=use_last_n_years * 365.25)
        df = df[df.index >= cutoff]

    # Convert to UTC (timestamps have timezone info)
    if df.index.tz is not None:
        datetimes_utc = df.index.tz_convert('UTC').tz_localize(None).to_pydatetime()
    else:
        # Assume CET (+01:00), subtract 1 hour
        datetimes_utc = (df.index - pd.Timedelta(hours=1)).to_pydatetime()

    levels_m = df['waterlevel_cm_NAP'].values / 100.0  # cm -> meters

    return np.array(datetimes_utc), levels_m.astype(np.float64)


def analyze_station(args):
    """Run UTide analysis for one station. Saves checkpoint on success."""
    csv_path, station_meta, key = args
    checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
    t0 = time.time()

    try:
        datetimes_utc, levels = load_csv(csv_path, use_last_n_years=USE_LAST_N_YEARS)

        if datetimes_utc is None or len(datetimes_utc) < 2000:
            n = 0 if datetimes_utc is None else len(datetimes_utc)
            return (key, f"insufficient data ({n} obs)")

        lat = station_meta['lat']

        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_93,
        )

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
        try:
            recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
            residuals = levels - recon['h']
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((levels - np.mean(levels))**2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            rms_error = np.sqrt(np.mean(residuals**2))
        except:
            r_squared = 0
            rms_error = 0

        m2_amp = 0
        for c in constituents:
            if c['name'] == 'M2':
                m2_amp = c['amplitude']
                break

        duration = time.time() - t0

        result = {
            'mean': coef['mean'],
            'constituents': constituents,
            'n_analyzed': n_analyzed,
            'r_squared': r_squared,
            'rms_error': rms_error,
            'm2_amp': m2_amp,
            'n_obs': len(datetimes_utc),
            'start_time': datetimes_utc[0],
            'end_time': datetimes_utc[-1],
            'station_meta': station_meta,
            'duration': duration,
        }

        with open(checkpoint_file, 'wb') as f:
            pickle.dump(result, f)

        return (key, result)

    except Exception as e:
        import traceback
        return (key, f"error: {e}\n{traceback.format_exc()}")


def format_station_block(key, result):
    """Format a single station block in XTide harmonics format."""
    meta = result['station_meta']
    station_name = meta['name']
    lat = meta['lat']
    lon = meta['lon']

    lines = []
    lines.append(f"# Harmonic constants derived from RWS astronomical water level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Netherlands")
    lines.append(f"# source: Derived from Rijkswaterstaat astronomical tide data with UTide")
    lines.append(f"# station_id_context: RWS")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: NAP")
    lines.append(f"# confidence: 9")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{station_name}, Netherlands")
    lines.append(f"+00:00 :Europe/Amsterdam")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print("Batch UTide Harmonic Analysis — Dutch Tide Stations (RWS)")
    print("=" * 75)

    # Load station metadata from ddlpy
    print("Loading station metadata from RWS...")
    import ddlpy
    locations = ddlpy.locations()
    sel = locations[
        (locations['Grootheid.Code'] == 'WATHTE') &
        (locations['Hoedanigheid.Code'] == 'NAP') &
        (locations['ProcesType'] == 'astronomisch') &
        (locations['Groepering.Code'] == '')
    ]

    # Build metadata lookup: csv filename stem -> {name, lat, lon}
    meta_lookup = {}
    for idx, row in sel.iterrows():
        code = idx.replace('/', '_').replace('\\', '_').replace(' ', '_')
        meta_lookup[code] = {
            'name': row['Naam'],
            'lat': float(row['Lat']),
            'lon': float(row['Lon']),
            'code': idx,
        }

    # Match CSV files to metadata
    csv_files = sorted(CSV_DIR.glob("*.csv"))
    all_tasks = []
    unmatched = []

    for csv_path in csv_files:
        key = csv_path.stem
        if key in meta_lookup:
            all_tasks.append((csv_path, meta_lookup[key], key))
        else:
            unmatched.append(key)

    print(f"  CSV files: {len(csv_files)}")
    print(f"  Matched: {len(all_tasks)}, Unmatched: {len(unmatched)}")
    if unmatched:
        print(f"  Unmatched: {unmatched[:10]}...")

    # Check for existing checkpoints (resume support)
    tasks_todo = []
    tasks_done = []
    for task in all_tasks:
        key = task[2]
        checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
        if checkpoint_file.exists():
            tasks_done.append(task)
        else:
            tasks_todo.append(task)

    if tasks_done:
        print(f"\n  Resuming: {len(tasks_done)} already completed, {len(tasks_todo)} remaining")
    else:
        print(f"\n  Starting fresh: {len(tasks_todo)} stations to process")

    print(f"  Years: last {USE_LAST_N_YEARS}, Workers: {N_WORKERS}")

    # Read header from template
    header = read_header_from_template(TEMPLATE_PATH)

    # Progress table
    print(f"\n{'#':>4s}  {'Station':<45s} {'Obs':>8s} {'Const':>6s} {'R²':>7s} {'M2':>7s} {'Time':>6s} {'Status'}")
    print(f"{'─'*4}  {'─'*45} {'─'*8} {'─'*6} {'─'*7} {'─'*7} {'─'*6} {'─'*8}")

    # Print cached stations
    for task in tasks_done:
        key = task[2]
        checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
        try:
            with open(checkpoint_file, 'rb') as f:
                result = pickle.load(f)
            name = result['station_meta']['name']
            print(f"  ►  {name:<45s} "
                  f"{result['n_obs']:>8d} {result['n_analyzed']:>6d} "
                  f"{result['r_squared']:>7.4f} {result['m2_amp']:>7.4f} "
                  f"{'':>6s} ✓ cached")
        except:
            tasks_todo.append(task)
            checkpoint_file.unlink(missing_ok=True)

    t_start = time.time()
    completed = len(tasks_done)
    failed = 0

    if tasks_todo:
        with Pool(N_WORKERS) as pool:
            for key, result in pool.imap_unordered(analyze_station, tasks_todo):
                completed += 1
                if isinstance(result, str):
                    print(f"{completed:>4d}  {key:<45s} {'':>8s} {'':>6s} {'':>7s} {'':>7s} {'':>6s} ✗ {result[:40]}",
                          flush=True)
                    failed += 1
                else:
                    name = result['station_meta']['name']
                    print(f"{completed:>4d}  {name:<45s} "
                          f"{result['n_obs']:>8d} {result['n_analyzed']:>6d} "
                          f"{result['r_squared']:>7.4f} {result['m2_amp']:>7.4f} "
                          f"{result['duration']:>5.1f}s ✓",
                          flush=True)

    t_total = time.time() - t_start

    # Assemble final output from all checkpoints
    print(f"\nAssembling output from checkpoints...")
    ok_results = []
    for task in all_tasks:
        key = task[2]
        checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, 'rb') as f:
                    result = pickle.load(f)
                ok_results.append((key, result))
            except:
                pass

    print(f"Writing {len(ok_results)} stations to {OUTPUT_PATH.name}...")
    with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
        f.write(header)
        f.write('\n')
        for key, result in ok_results:
            block = format_station_block(key, result)
            f.write(block)
            f.write('\n')

    print(f"\n{'='*75}")
    print(f"Done in {t_total:.0f}s ({t_total/60:.1f} min)")
    print(f"  Total OK: {len(ok_results)}, Failed: {failed}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")

    if ok_results:
        r2_vals = [r['r_squared'] for _, r in ok_results]
        m2_vals = [r['m2_amp'] for _, r in ok_results]
        constit_counts = [r['n_analyzed'] for _, r in ok_results]
        print(f"  R²: min={min(r2_vals):.4f}, median={sorted(r2_vals)[len(r2_vals)//2]:.4f}, max={max(r2_vals):.4f}")
        print(f"  M2: min={min(m2_vals):.4f}m, max={max(m2_vals):.4f}m")
        print(f"  Constituents: min={min(constit_counts)}, max={max(constit_counts)}")


if __name__ == "__main__":
    main()
