#!/usr/bin/env python3
"""
UTide harmonic analysis for Prince Edward Island tide stations.

Sources:
- WLO (observations) for Charlottetown, Souris, Wood Islands
- WLP (CHS predictions) for all other stations incl. Goodwood River + Covehead

WLP-derived harmonics are essentially reverse-engineered CHS constants.
WLO-derived harmonics are independent analyses from real observations.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
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

# --- Directories ---
PEI_DIR = Path("/home/oliver/water_levels/Canada_IWLS_PEI")
IWLS_DIR = Path("/home/oliver/water_levels/Canada_IWLS")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_pei.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_pei")

# PEI stations with their metadata
# code, name, lat, lon, data_type ('wlo' or 'wlp'), csv_file
PEI_STATIONS = [
    # Active stations with WLO observations
    ('01700', 'Charlottetown', 46.2301, -63.1222, 'wlo', None),  # from Canada_IWLS
    ('01650', 'Souris', 46.3496, -62.2518, 'wlo', '01650_Souris_wlo.csv'),
    ('01680', 'Wood Islands', 45.9529, -62.7494, 'wlo', '01680_Wood_Islands_wlo.csv'),
    # Stations with WLP predictions only — reverse-engineer CHS harmonics
    ('01660', 'Georgetown Harbour', 46.1795, -62.5316, 'wlp', '01660_Georgetown_wlp.csv'),
    ('01662', 'Montague', 46.1647, -62.6463, 'wlp', '01662_Montague_wlp.csv'),
    ('01665', 'Graham Pond', 46.0960, -62.4537, 'wlp', '01665_Graham_Pond_wlp.csv'),
    ('01670', 'Murray Harbour', 46.0055, -62.5235, 'wlp', '01670_Murray_Harbour_wlp.csv'),
    ('01690', 'Prim Point', 46.0562, -63.0302, 'wlp', '01690_Prim_Point_wlp.csv'),
    ('01710', 'Canoe Cove', 46.1492, -63.3037, 'wlp', '01710_Canoe_Cove_wlp.csv'),
    ('01715', 'Victoria', 46.2126, -63.4895, 'wlp', '01715_Victoria,_PEI_wlp.csv'),
    ('01725', 'Port Borden', 46.2461, -63.7007, 'wlp', '01725_Port_Borden_wlp.csv'),
    ('01735', 'Summerside', 46.3865, -63.7896, 'wlp', '01735_Summerside_wlp.csv'),
    ('01835', 'Cape Egmont', 46.4082, -64.1336, 'wlp', '01835_Cape_Egmont_wlp.csv'),
    ('01845', 'West Point', 46.6201, -64.3718, 'wlp', '01845_West_Point_wlp.csv'),
    ('01855', 'Miminegash', 46.8801, -64.2344, 'wlp', '01855_Miminegash_wlp.csv'),
    ('01860', "Skinner's Pond", 46.9642, -64.1229, 'wlp', '01860_Skinners_Pond_wlp.csv'),
    ('01865', 'North Point', 47.0582, -63.9960, 'wlp', '01865_North_Point_wlp.csv'),
    ('01875', 'Tignish', 46.9509, -63.9938, 'wlp', '01875_Tignish_wlp.csv'),
    ('01885', 'Alberton', 46.7951, -64.0583, 'wlp', '01885_Alberton_wlp.csv'),
    ('01896', 'Goodwood River', 46.6168, -63.9166, 'wlp', '01896_Goodwood_River_wlp.csv'),
    ('01905', 'Malpeque', 46.5240, -63.6966, 'wlp', '01905_Malpeque_wlp.csv'),
    ('01915', 'North Rustico', 46.4560, -63.2941, 'wlp', '01915_Rustico_wlp.csv'),
    ('01918', 'Covehead', 46.4290, -63.1461, 'wlp', '01918_Covehead_wlp.csv'),
    ('01925', 'Savage Harbour', 46.4269, -62.8400, 'wlp', '01925_Crowbush_Cove_wlp.csv'),
    ('01935', 'St. Peters Bay', 46.4386, -62.7331, 'wlp', '01935_St_Peters_Bay_wlp.csv'),
    ('01945', 'Naufrage', 46.4684, -62.4172, 'wlp', '01945_Naufrage_wlp.csv'),
    ('01955', 'North Lake Harbour', 46.4670, -62.0688, 'wlp', '01955_North_Lake_Harbour_wlp.csv'),
]

# 93 constituents for analysis (same as batch_utide_canada_all.py)
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


def load_csv(csv_path):
    """Load CSV (time, waterlevel_m) and return arrays."""
    df = pd.read_csv(csv_path, parse_dates=['time'], index_col='time')
    df = df.dropna(subset=['waterlevel_m'])

    if len(df) == 0:
        return None, None

    if df.index.tz is not None:
        datetimes_utc = df.index.tz_convert('UTC').tz_localize(None).to_pydatetime()
    else:
        datetimes_utc = df.index.to_pydatetime()

    levels_m = df['waterlevel_m'].values.astype(np.float64)
    return np.array(datetimes_utc), levels_m


def analyze_station(code, name, lat, lon, data_type, csv_file):
    """Run UTide analysis for one station."""
    checkpoint_file = CHECKPOINT_DIR / f"{code}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        yrs = result.get('n_obs', 0) / (4 * 24 * 365.25)
        print(f"  ✓ Checkpoint ({data_type}, {yrs:.1f}J, R²={result['r_squared']:.4f})")
        return result

    # Find CSV file
    if csv_file is None:
        # Charlottetown from main Canada_IWLS dir
        csv_path = IWLS_DIR / f"{code}_Charlottetown.csv"
    else:
        csv_path = PEI_DIR / csv_file

    if not csv_path.exists():
        print(f"  ✗ CSV nicht gefunden: {csv_path}")
        return None

    t0 = time.time()
    datetimes_utc, levels = load_csv(csv_path)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    years = len(datetimes_utc) / (4 * 24 * 365.25)
    print(f"  UTide [{data_type}] ({len(datetimes_utc)} Beob., {years:.1f}J, lat={lat:.2f})...",
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
        'code': code,
        'name': name,
        'lat': lat,
        'lon': lon,
        'data_type': data_type,
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
    data_type = result['data_type']

    source_desc = "IWLS sea level observations" if data_type == 'wlo' else "CHS tide predictions (reverse-engineered)"

    lines = []
    lines.append(f"# Harmonic constants derived from {source_desc}")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} data points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Canada")
    lines.append(f"# province: Prince Edward Island")
    lines.append(f"# source: Derived from {source_desc} with UTide harmonic analysis")
    lines.append(f"# station_id_context: CHS-{code}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: LLWLT")
    if data_type == 'wlo':
        lines.append(f"# confidence: 8")
    else:
        lines.append(f"# confidence: 9")  # CHS predictions are high quality
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, Prince Edward Island, Canada")
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

    print("=" * 70)
    print("UTide Harmonic Analysis — Prince Edward Island")
    print("=" * 70)
    print(f"Stationen: {len(PEI_STATIONS)}")
    print(f"Checkpoints: {CHECKPOINT_DIR}")
    print(f"Ausgabe: {OUTPUT_PATH}")
    print()

    results = []
    success = 0
    failed = 0

    for i, (code, name, lat, lon, data_type, csv_file) in enumerate(PEI_STATIONS):
        print(f"\n[{i+1}/{len(PEI_STATIONS)}] {code} | {name} [{data_type}]")

        result = analyze_station(code, name, lat, lon, data_type, csv_file)
        if result is not None:
            results.append(result)
            success += 1
        else:
            failed += 1

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

    # Summary table
    print(f"\n\n{'='*70}")
    print("ZUSAMMENFASSUNG")
    print(f"{'='*70}")
    print(f"{'Station':<30s} {'Typ':>4s} {'Jahre':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s} {'K1':>7s}")
    print(f"{'─'*30} {'─'*4} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

    for r in results:
        years = r['n_obs'] / (4 * 24 * 365.25)
        dtype = r['data_type']
        print(f"{r['name']:<30s} {dtype:>4s} {years:>5.1f}  "
              f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  "
              f"{r['m2_amp']:>6.4f}  {r['k1_amp']:>6.4f}")

    print(f"\nGesamt: {success} erfolgreich, {failed} fehlgeschlagen")


if __name__ == '__main__':
    main()
