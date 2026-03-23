#!/usr/bin/env python3
"""
UTide harmonic analysis for UK tide stations using BODC 15-min data.
Data is in ACD (Admiralty Chart Datum) = LAT.
Checkpoint/resume per station.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import re
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

DATA_DIR = Path("/home/oliver/water_levels/UK/bodc_sea_level_2007-2026_values_and_residuals_acd")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_uk_bodc.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_uk_bodc")

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

# UK regions by approximate location
def get_region(name, lat, lon):
    if lat > 56.5:
        return 'Scotland'
    elif lon < -4.5 and lat < 53.5:
        return 'Wales'
    elif lon < -5.5 and lat > 54:
        return 'Northern Ireland'
    elif name in ['Port Erin']:
        return 'Isle of Man'
    elif name in ['St. Helier (Jersey)']:
        return 'Channel Islands'
    elif name in ["St. Mary's"]:
        return 'Isles of Scilly'
    else:
        return 'England'


def discover_stations():
    """Scan data directory and group files by station."""
    stations = {}
    for f in sorted(os.listdir(DATA_DIR)):
        if f.endswith('.txt') and ':' not in f:
            m = re.match(r'(\d{4})([A-Z]+)\.txt', f)
            if m:
                year, code = m.groups()
                if code not in stations:
                    with open(DATA_DIR / f) as fh:
                        header_lines = [fh.readline() for _ in range(9)]
                    name = header_lines[1].split(':', 1)[1].strip()
                    lat = float(header_lines[2].split(':', 1)[1].strip())
                    lon = float(header_lines[3].split(':', 1)[1].strip())
                    stations[code] = {
                        'name': name, 'lat': lat, 'lon': lon,
                        'code': code, 'files': [],
                        'region': get_region(name, lat, lon),
                    }
                stations[code]['files'].append(f)
    return stations


def load_bodc_files(file_list):
    """Load and concatenate BODC text files into arrays.

    Detects and removes years with datum offset jumps by comparing
    per-file means against the overall median.
    """
    # First pass: load each file separately to detect datum jumps
    file_data = []
    for fname in sorted(file_list):
        filepath = DATA_DIR / fname
        times = []
        levels = []
        with open(filepath) as f:
            for line in f:
                m = re.match(r'\s*\d+\)\s+(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+([\d.]+)', line)
                if m:
                    try:
                        times.append(pd.Timestamp(m.group(1)))
                        levels.append(float(m.group(2)))
                    except (ValueError, IndexError):
                        pass
        if levels:
            file_data.append({
                'fname': fname,
                'times': times,
                'levels': levels,
                'mean': np.mean(levels),
                'std': np.std(levels),
            })

    if not file_data:
        return None, None

    # Detect datum jumps: use median of per-file means as reference
    all_means = [fd['mean'] for fd in file_data]
    median_mean = np.median(all_means)
    # Also get the typical std (median of stds)
    median_std = np.median([fd['std'] for fd in file_data])

    # Filter out files where mean deviates more than 2x the typical std
    threshold = max(2.0 * median_std, 0.5)  # at least 0.5m tolerance
    good_files = []
    skipped = []
    for fd in file_data:
        offset = abs(fd['mean'] - median_mean)
        if offset > threshold:
            skipped.append(fd['fname'])
        else:
            good_files.append(fd)

    if skipped:
        print(f" [{len(skipped)} Dateien übersprungen: Datum-Offset]", end='', flush=True)

    if not good_files:
        return None, None

    # Combine good files
    all_times = []
    all_levels = []
    for fd in good_files:
        all_times.extend(fd['times'])
        all_levels.extend(fd['levels'])

    df = pd.DataFrame({'time': all_times, 'level': all_levels})
    df = df.drop_duplicates(subset='time').sort_values('time')

    datetimes = df['time'].values.astype('datetime64[ns]')
    datetimes_py = pd.to_datetime(datetimes).to_pydatetime()
    levels = df['level'].values.astype(np.float64)

    return np.array(datetimes_py), levels


def analyze_station(station):
    """Run UTide analysis for one BODC station."""
    code = station['code']
    checkpoint_file = CHECKPOINT_DIR / f"{code}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        yrs = result['n_obs'] / (4 * 24 * 365.25)
        print(f"  ✓ Checkpoint ({yrs:.1f}J, R²={result['r_squared']:.4f})")
        return result

    t0 = time.time()
    datetimes_utc, levels = load_bodc_files(station['files'])

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    lat = station['lat']
    years = len(datetimes_utc) / (4 * 24 * 365.25)
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
    region = station.get('region', 'England')

    lines = []
    lines.append(f"# Harmonic constants derived from BODC 15-min sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: United Kingdom")
    lines.append(f"# region: {region}")
    lines.append(f"# source: Derived from BODC NTGN data with UTide harmonic analysis")
    lines.append(f"# station_id_context: BODC-{station['code']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: ACD")
    lines.append(f"# confidence: 9")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, {region}, United Kingdom")
    lines.append(f"+00:00 :Europe/London")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    stations = discover_stations()

    # Sort by region, then name
    sorted_codes = sorted(stations.keys(),
                         key=lambda c: (stations[c]['region'], stations[c]['name']))

    print("=" * 70)
    print("UTide Harmonic Analysis — BODC UK Tide Gauge Network")
    print("15-min data, ACD datum, 2007–2024")
    print("=" * 70)
    print(f"Stationen: {len(stations)}")
    print()

    results = []
    current_region = None

    for i, code in enumerate(sorted_codes):
        station = stations[code]
        region = station['region']

        if region != current_region:
            current_region = region
            print(f"\n{'━'*70}")
            print(f"  {region}")
            print(f"{'━'*70}")

        n_files = len(station['files'])
        years_range = sorted([int(f[:4]) for f in station['files']])
        print(f"\n[{i+1}/{len(stations)}] {code} | {station['name']} "
              f"({n_files} Dateien, {years_range[0]}-{years_range[-1]})")

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
        print(f"{'Station':<30s} {'Region':<18s} {'Jahre':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s} {'K1':>7s}")
        print(f"{'─'*30} {'─'*18} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

        for r in results:
            years = r['n_obs'] / (4 * 24 * 365.25)
            print(f"{r['station']['name']:<30s} {r['station']['region']:<18s} {years:>5.1f}  "
                  f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  "
                  f"{r['m2_amp']:>6.4f}  {r['k1_amp']:>6.4f}")

        print(f"\nGesamt: {len(results)} Stationen erfolgreich")
        avg_r2 = np.mean([r['r_squared'] for r in results])
        print(f"Durchschnittliches R²: {avg_r2:.4f}")


if __name__ == '__main__':
    main()
