#!/usr/bin/env python3
"""
Batch UTide harmonic analysis for all German tide stations.
Reads pre-processed NPZ files, runs UTide, maps to 175 XTide constituents.

Features:
- Checkpoint/resume: saves each station result to disk immediately
- On restart, skips already-completed stations
- Uses imap_unordered for live progress output
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
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
    extract_stations_from_harmonics,
    build_station_lookup,
    fuzzy_match_station,
    read_header_from_template,
)

NPZ_DIR = Path("/home/oliver/water_levels/Germany/npz")
HARMONICS_REF = Path("/home/oliver/harmonics/utide/bak/harmonics_germany_2026-01-23.txt")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_germany_2026-03-15.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_93")

USE_LAST_N_YEARS = 19  # Full nodal cycle (18.61 years)
N_WORKERS = 3

# 93 constituents: 86 from DWF-2007 BSH analysis + 7 UTide-specific
# Based on BSH's expert constituent selection for German North Sea / estuaries
CONSTIT_93 = [
    # Astronomical diurnal
    'J1', 'K1', 'O1', 'OO1', 'P1', 'Q1', '2Q1', 'RHO1', 'ALP1', 'BET1',
    'CHI1', 'NO1', 'PHI1', 'PI1', 'PSI1', 'SIG1', 'SO1', 'THE1', '2PO1',
    'TAU1', 'UPS1',
    # Astronomical semi-diurnal
    'K2', 'L2', 'M2', 'N2', '2N2', 'R2', 'S2', 'T2', 'LDA2', 'MU2',
    'NU2', 'EPS2', 'ETA2', '2SM2', '2NS2', 'SKM2', 'OP2', 'MKS2', 'MSN2',
    'OQ2',
    # Long period
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    # Terdiurnal
    'M3', 'MK3', 'MO3', 'SK3', 'SO3', 'NO3',
    # Quarter-diurnal (shallow water)
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4', 'N4', 'SL4', '3MS4',
    # Quindiurnal
    '2MK5', '2SK5', '2MO5', 'MNO5', 'MSK5', '3KM5', '2MP5', '3MP5', 'MNK5',
    # Sixth-diurnal
    'M6', '2MN6', '2MS6', '2MK6', '2NM6', '2SM6', 'MSK6', 'MSN6', 'S6',
    # Seventh-diurnal
    'M7', '3MK7',
    # Eighth-diurnal
    'M8', '3MN8', '3MS8', '3MK8',
    # Higher
    '4MK9', 'M10', 'M12',
    # UTide-specific (not in DWF but auto-selected)
    'H1', 'H2', 'S1',
]


def load_npz(npz_path, use_last_n_years=19):
    """Load NPZ and return last N years as python datetime + meters arrays."""
    d = np.load(npz_path, allow_pickle=True)
    dt64 = d['datetimes_utc']
    levels_cm = d['levels_cm']

    timestamps = dt64.astype('datetime64[s]').astype(np.int64)
    datetimes = [datetime.utcfromtimestamp(ts) for ts in timestamps]

    if use_last_n_years is not None and len(datetimes) > 0:
        cutoff = datetimes[-1] - timedelta(days=use_last_n_years * 365.25)
        idx = 0
        for i, dt in enumerate(datetimes):
            if dt >= cutoff:
                idx = i
                break
        datetimes = datetimes[idx:]
        levels_cm = levels_cm[idx:]

    levels_m = levels_cm.astype(np.float64) / 100.0
    return np.array(datetimes), levels_m


def analyze_station(args):
    """Run UTide analysis for one station. Saves checkpoint on success."""
    npz_path, station_info, key = args
    checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
    t0 = time.time()

    try:
        datetimes_utc, levels = load_npz(npz_path, use_last_n_years=USE_LAST_N_YEARS)

        if len(datetimes_utc) < 2000:
            return (key, f"insufficient data ({len(datetimes_utc)} obs)")

        lat = station_info['latitude']

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
            snr = coef['SNR'][i] if 'SNR' in coef else 999

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
                'snr': snr,
            }

        constituents = []
        n_analyzed = 0
        for name, speed in CONSTITUENTS_175:
            if name in utide_results:
                r = utide_results[name]
                constituents.append({
                    'name': name, 'amplitude': r['amplitude'],
                    'phase': r['phase'], 'speed': speed, 'snr': r['snr'],
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
            'station_info': station_info,
            'duration': duration,
        }

        # Save checkpoint immediately
        with open(checkpoint_file, 'wb') as f:
            pickle.dump(result, f)

        return (key, result)

    except Exception as e:
        return (key, f"error: {e}")


def format_station_block(key, result):
    """Format a single station block in XTide harmonics format."""
    si = result['station_info']
    station_name = si['name']
    lat = si['latitude']
    lon = si['longitude']
    water = si.get('water', 'Unknown')

    lines = []
    lines.append(f"# Harmonic constants derived from Pegelonline water level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# Water body: {water}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Germany")
    lines.append(f"# source: Derived from Pegelonline data with UTide harmonic analysis")
    lines.append(f"# restriction: Non-commercial use only")
    lines.append(f"# station_id_context: WSV")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.4f}")
    lines.append(f"# !latitude: {lat:.4f}")

    lines.append(f"{station_name}, Germany")
    lines.append(f"+00:00 :Europe/Berlin")
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
    print("Batch UTide Harmonic Analysis — German Tide Stations")
    print("=" * 75)
    print(f"  NPZ dir:      {NPZ_DIR}")
    print(f"  Reference:    {HARMONICS_REF.name}")
    print(f"  Output:       {OUTPUT_PATH.name}")
    print(f"  Checkpoints:  {CHECKPOINT_DIR}")
    print(f"  Years:        last {USE_LAST_N_YEARS} (full nodal cycle)")
    print(f"  Workers:      {N_WORKERS}")
    print(f"  conf_int:     linear")
    print()

    # Load station metadata
    print("Loading station metadata...")
    all_stations = extract_stations_from_harmonics(HARMONICS_REF)
    station_lookup = build_station_lookup(all_stations)
    print(f"  {len(all_stations)} stations with coordinates")

    # Match NPZ files to stations
    npz_files = sorted(NPZ_DIR.glob("*.npz"))
    all_tasks = []
    unmatched = []

    for npz_path in npz_files:
        key = npz_path.stem
        station_info = fuzzy_match_station(key, station_lookup, all_stations)
        if station_info:
            all_tasks.append((npz_path, station_info, key))
        else:
            unmatched.append(key)

    print(f"  Matched: {len(all_tasks)}, Unmatched: {len(unmatched)}")
    if unmatched:
        print(f"  Unmatched: {unmatched}")

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

    # Read header
    header = read_header_from_template(TEMPLATE_PATH)

    # Process remaining stations with live progress
    print(f"\n{'#':>4s}  {'Station':<35s} {'Obs':>7s} {'Const':>6s} {'R²':>7s} {'M2':>7s} {'Time':>6s} {'Status'}")
    print(f"{'─'*4}  {'─'*35} {'─'*7} {'─'*6} {'─'*7} {'─'*7} {'─'*6} {'─'*8}")

    # Print already-done stations
    for task in tasks_done:
        key = task[2]
        station_info = task[1]
        checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
        try:
            with open(checkpoint_file, 'rb') as f:
                result = pickle.load(f)
            print(f"  ►  {result['station_info']['name']:<35s} "
                  f"{result['n_obs']:>7d} {result['n_analyzed']:>6d} "
                  f"{result['r_squared']:>7.4f} {result['m2_amp']:>7.4f} "
                  f"{'':>6s} ✓ cached")
        except:
            # Corrupt checkpoint, redo
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
                    print(f"{completed:>4d}  {key:<35s} {'':>7s} {'':>6s} {'':>7s} {'':>7s} {'':>6s} ✗ {result}",
                          flush=True)
                    failed += 1
                else:
                    print(f"{completed:>4d}  {result['station_info']['name']:<35s} "
                          f"{result['n_obs']:>7d} {result['n_analyzed']:>6d} "
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
    with open(OUTPUT_PATH, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for key, result in ok_results:
            block = format_station_block(key, result)
            f.write(block)
            f.write('\n')

    print(f"\n{'='*75}")
    print(f"New stations processed in {t_total:.0f}s ({t_total/60:.1f} min)")
    print(f"  Total OK: {len(ok_results)}, Failed: {failed}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")

    # Show constituent count summary
    if ok_results:
        constit_counts = [r['n_analyzed'] for _, r in ok_results]
        print(f"  Constituents: min={min(constit_counts)}, max={max(constit_counts)}, "
              f"median={sorted(constit_counts)[len(constit_counts)//2]}")


if __name__ == "__main__":
    main()
