#!/usr/bin/env python3
"""
Batch UTide harmonic analysis for Hamburg tide stations.
Reads 10-minute NPZ files, runs UTide with 93 constituents, maps to 175 XTide constituents.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import time
import pickle
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    UTIDE_TO_XTIDE_NAME,
    find_xtide_match,
    read_header_from_template,
)

NPZ_DIR = Path("/home/oliver/water_levels/Germany/HH/npz")
TEMPLATE_PATH = Path("/home/oliver/harmonics_working/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics_working/harmonics_utide_hamburg_2026-03-15.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics_working/checkpoints_hh")

USE_LAST_N_YEARS = 19
N_WORKERS = 3

# Station metadata from tide_stations_hamburg.ods
STATIONS = {
    'STP': {'name': 'Hamburg (St. Pauli)', 'latitude': 53.5456, 'longitude': 9.9700, 'water': 'Norderelbe'},
    'HAR': {'name': 'Hamburg-Harburg (Elbe, Schleuse)', 'latitude': 53.473, 'longitude': 9.992, 'water': 'Süderelbe'},
    'UBN': {'name': 'Hamburg-Blankenese (Elbe, Unterfeuer)', 'latitude': 53.558, 'longitude': 9.796, 'water': 'Elbe'},
    'SMH': {'name': 'Hamburg Seemannshöft (Elbe)', 'latitude': 53.540, 'longitude': 9.881, 'water': 'Norderelbe'},
    'SPS': {'name': 'Hamburg Dove-Elbe (Einfahrt)', 'latitude': 53.508, 'longitude': 10.062, 'water': 'Dove-Elbe'},
    'BHS': {'name': 'Hamburg-Bunthaus (Elbe)', 'latitude': 53.461, 'longitude': 10.064, 'water': 'Norderelbe'},
}

# Same 93 constituents as for BSH/Pegelonline stations
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


def load_npz(npz_path):
    """Load NPZ and return datetime64 array + meters array."""
    d = np.load(npz_path, allow_pickle=True)
    dt64 = d['datetimes_utc']
    levels_cm = d['levels_cm']

    # Convert datetime64 to python datetime for UTide
    timestamps = dt64.astype('datetime64[s]').astype(np.int64)
    datetimes = [datetime.utcfromtimestamp(ts) for ts in timestamps]

    levels_m = levels_cm.astype(np.float64) / 100.0
    return np.array(datetimes), levels_m


def analyze_station(key):
    """Run UTide analysis for one station."""
    npz_path = NPZ_DIR / f"{key}.npz"
    checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
    station_info = STATIONS[key]
    t0 = time.time()

    try:
        datetimes_utc, levels = load_npz(npz_path)

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
            'station_info': station_info,
            'duration': duration,
        }

        with open(checkpoint_file, 'wb') as f:
            pickle.dump(result, f)

        return (key, result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return (key, f"error: {e}")


def format_station_block(key, result):
    """Format a single station block in XTide harmonics format."""
    si = result['station_info']
    station_name = si['name']
    lat = si['latitude']
    lon = si['longitude']
    water = si.get('water', 'Unknown')

    lines = []
    lines.append(f"# Harmonic constants derived from HPA water level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# Water body: {water}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Germany")
    lines.append(f"# source: Derived from HPA Hamburg data with UTide harmonic analysis")
    lines.append(f"# restriction: Non-commercial use only")
    lines.append(f"# station_id_context: HPA")
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
    print("Batch UTide Harmonic Analysis — Hamburg Tide Stations")
    print("=" * 75)
    print(f"  NPZ dir:      {NPZ_DIR}")
    print(f"  Output:       {OUTPUT_PATH.name}")
    print(f"  Checkpoints:  {CHECKPOINT_DIR}")
    print(f"  Years:        last {USE_LAST_N_YEARS} (full nodal cycle)")
    print(f"  Constituents: {len(CONSTIT_93)}")
    print()

    # Process each station sequentially (only 6 stations)
    print(f"{'#':>3s}  {'Station':<45s} {'Obs':>8s} {'Const':>6s} {'R²':>7s} {'M2':>7s} {'Time':>6s}")
    print(f"{'─'*3}  {'─'*45} {'─'*8} {'─'*6} {'─'*7} {'─'*7} {'─'*6}")

    results = []
    for i, key in enumerate(STATIONS):
        checkpoint_file = CHECKPOINT_DIR / f"{key}.pkl"
        if checkpoint_file.exists():
            with open(checkpoint_file, 'rb') as f:
                result = pickle.load(f)
            print(f"{i+1:>3d}  {result['station_info']['name']:<45s} "
                  f"{result['n_obs']:>8d} {result['n_analyzed']:>6d} "
                  f"{result['r_squared']:>7.4f} {result['m2_amp']:>7.4f} "
                  f"{'':>6s} ✓ cached")
            results.append((key, result))
            continue

        key_result, result = analyze_station(key)
        if isinstance(result, str):
            print(f"{i+1:>3d}  {key:<45s} {'':>8s} {'':>6s} {'':>7s} {'':>7s} {'':>6s} ✗ {result}")
        else:
            print(f"{i+1:>3d}  {result['station_info']['name']:<45s} "
                  f"{result['n_obs']:>8d} {result['n_analyzed']:>6d} "
                  f"{result['r_squared']:>7.4f} {result['m2_amp']:>7.4f} "
                  f"{result['duration']:>5.1f}s ✓")
            results.append((key, result))

    # Read header and write output
    header = read_header_from_template(TEMPLATE_PATH)

    print(f"\nWriting {len(results)} stations to {OUTPUT_PATH.name}...")
    with open(OUTPUT_PATH, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for key, result in results:
            block = format_station_block(key, result)
            f.write(block)
            f.write('\n')
        f.write('# END OF FILE\n')

    print(f"\n{'='*75}")
    print(f"  Stations: {len(results)}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size / 1024:.0f} KB")

    if results:
        r2_vals = [r['r_squared'] for _, r in results]
        m2_vals = [r['m2_amp'] for _, r in results]
        print(f"  R² range: {min(r2_vals):.4f} - {max(r2_vals):.4f}")
        print(f"  M2 range: {min(m2_vals):.4f} - {max(m2_vals):.4f} m")


if __name__ == '__main__':
    main()
