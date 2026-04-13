#!/usr/bin/env python3
"""
UTide harmonic analysis for Nova Scotia tide stations.
Uses WLP (CHS predictions) data — reverse-engineering CHS harmonics.
Identical method to PEI, NB, and QC batch scripts.
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
import glob
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

NS_DIR = Path("/home/oliver/water_levels/Canada_IWLS_NS")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_ns.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_ns")

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


def load_wlp_csv(csv_path):
    """Load WLP CSV and return (datetimes, levels) arrays."""
    df = pd.read_csv(csv_path)

    if 'time' in df.columns:
        time_col = 'time'
    elif 'datetime_utc' in df.columns:
        time_col = 'datetime_utc'
    else:
        time_col = df.columns[0]

    level_col = 'waterlevel_m' if 'waterlevel_m' in df.columns else df.columns[1]

    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    df = df.dropna(subset=[level_col])

    if len(df) == 0:
        return None, None

    datetimes_utc = df[time_col].dt.tz_localize(None).values.astype('datetime64[ns]')
    datetimes_py = pd.to_datetime(datetimes_utc).to_pydatetime()
    levels_m = df[level_col].values.astype(np.float64)
    return np.array(datetimes_py), levels_m


def analyze_station(code, name, lat, lon, csv_path):
    """Run UTide analysis for one station."""
    checkpoint_file = CHECKPOINT_DIR / f"{code}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        yrs = result.get('n_obs', 0) / (4 * 24 * 365.25)
        print(f"  ✓ Checkpoint ({yrs:.1f}J, R²={result['r_squared']:.4f})")
        return result

    t0 = time.time()
    datetimes_utc, levels = load_wlp_csv(csv_path)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    years = len(datetimes_utc) / (4 * 24 * 365.25)
    print(f"  UTide [wlp] ({len(datetimes_utc)} Beob., {years:.1f}J, lat={lat:.2f})...",
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
        'code': code,
        'name': name,
        'lat': lat,
        'lon': lon,
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
    name = result['name']
    lat = result['lat']
    lon = result['lon']
    code = result['code']

    lines = []
    lines.append(f"# Harmonic constants derived from CHS tide predictions (reverse-engineered)")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} data points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Canada")
    lines.append(f"# province: Nova Scotia")
    lines.append(f"# source: Derived from CHS tide predictions (reverse-engineered) with UTide harmonic analysis")
    lines.append(f"# station_id_context: CHS-{code}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: LLWLT")
    lines.append(f"# confidence: 9")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, Nova Scotia, Canada")
    lines.append(f"+00:00 :UTC")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    with open(NS_DIR / '_ns_stations.json') as f:
        catalog = json.load(f)
    catalog_by_code = {s['code']: s for s in catalog}

    wlp_files = sorted(glob.glob(str(NS_DIR / '*_wlp.csv')))

    print("=" * 70)
    print("UTide Harmonic Analysis — Nova Scotia (CHS WLP)")
    print("=" * 70)
    print(f"WLP-Dateien gefunden: {len(wlp_files)}")
    print()

    results = []

    for i, csv_path in enumerate(wlp_files):
        basename = os.path.basename(csv_path)
        code = basename.split('_')[0]

        if code in catalog_by_code:
            s = catalog_by_code[code]
            name = s['name']
            lat = s['lat']
            lon = s['lon']
        else:
            print(f"\n[{i+1}/{len(wlp_files)}] {basename} — nicht im Katalog, überspringe")
            continue

        print(f"\n[{i+1}/{len(wlp_files)}] {code} | {name} ({lat:.4f}, {lon:.4f})")

        result = analyze_station(code, name, lat, lon, csv_path)
        if result is not None:
            results.append(result)

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

    if results:
        print(f"\n\n{'='*70}")
        print("ZUSAMMENFASSUNG")
        print(f"{'='*70}")
        print(f"{'Station':<40s} {'Code':>6s} {'Jahre':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s} {'K1':>7s}")
        print(f"{'─'*40} {'─'*6} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

        for r in results:
            years = r['n_obs'] / (4 * 24 * 365.25)
            print(f"{r['name']:<40s} {r['code']:>6s} {years:>5.1f}  "
                  f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  "
                  f"{r['m2_amp']:>6.4f}  {r['k1_amp']:>6.4f}")

        print(f"\nGesamt: {len(results)} Stationen erfolgreich")
        avg_r2 = np.mean([r['r_squared'] for r in results])
        print(f"Durchschnittliches R²: {avg_r2:.4f}")


if __name__ == '__main__':
    main()
