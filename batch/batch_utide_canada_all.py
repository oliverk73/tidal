#!/usr/bin/env python3
"""
UTide harmonic analysis for ALL Canadian tide stations.
Sources: CHS IWLS (15-min, ~6 years) + UHSLC (hourly, up to 50 years).
UHSLC data preferred where available (longer = better for nodal cycle).

Sorted by province, with checkpoint/resume per station.
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
import json
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

# --- Directories ---
IWLS_DIR = Path("/home/oliver/water_levels/Canada_IWLS")
UHSLC_DIR = Path("/home/oliver/water_levels/Canada_UHSLC")
CATALOG_PATH = Path("/home/oliver/water_levels/Canada/_stations_with_wlo.json")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_ca_all")

USE_LAST_N_YEARS = 19  # Full nodal cycle

# UHSLC stations (longer time series, preferred)
UHSLC_STATIONS = {
    '00490': 275,  # Halifax
    '09354': 540,  # Prince Rupert
    '08615': 542,  # Tofino
    '07120': 543,  # Victoria
    '00905': 276,  # St. John's
    '05010': 274,  # Churchill
    '01430': 833,  # Nain
    '00665': 273,  # Port-aux-Basques
    '08545': 541,  # Bamfield
    '03765': 836,  # Alert
}

# Province assignment by CHS code range + coordinates
def get_province(code, lat, lon, name):
    c = int(code)

    # Pacific / BC
    if 7000 <= c <= 9999:
        return 'British Columbia'

    # Hudson Bay / Arctic
    if 5000 <= c <= 6999:
        if lon < -125:
            return 'Northwest Territories'
        elif lat > 68:
            return 'Northwest Territories'
        elif lat > 63:
            return 'Nunavut'
        elif lon < -85:
            return 'Manitoba'
        else:
            return 'Ontario'

    # Great Lakes / Ontario (10xxx-14xxx)
    if 10000 <= c <= 14999:
        return 'Ontario'

    # St. Lawrence / Quebec (15xxx-16xxx)
    if 15000 <= c <= 15999:
        return 'Quebec'
    if 16000 <= c <= 16999:
        if lon < -75:
            return 'Ontario'
        return 'Quebec'

    # Nova Scotia / Bay of Fundy (00xxx)
    if 0 <= c <= 999:
        if lon < -65.5 and lat < 46:
            return 'New Brunswick'
        if lat > 46.5 and lon < -54:
            return 'Newfoundland and Labrador'
        return 'Nova Scotia'

    # Newfoundland / Labrador (01xxx)
    if 1000 <= c <= 1999:
        if lat > 52:
            return 'Newfoundland and Labrador'
        elif lon > -60:
            return 'Newfoundland and Labrador'
        elif lon > -64:
            return 'Prince Edward Island' if -64 < lon < -62 and 45.8 < lat < 47 else 'New Brunswick'
        else:
            return 'New Brunswick'

    # PEI / Gulf (02xxx)
    if 2000 <= c <= 2999:
        if -64.5 < lon < -62 and 45.8 < lat < 47.2:
            return 'Prince Edward Island'
        elif lon < -66:
            return 'Quebec'
        elif lat > 48:
            return 'Quebec'
        elif lon >= -62:
            return 'Nova Scotia'
        else:
            return 'New Brunswick'

    # Newfoundland south (03xxx)
    if 3000 <= c <= 3999:
        # St. Lawrence River stations
        if lon < -69 and lat < 49:
            return 'Quebec'
        if lat > 65:
            return 'Nunavut'
        return 'Quebec'  # Most 03xxx are actually Quebec St. Lawrence

    return 'Unknown'


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


def load_csv(csv_path, use_last_n_years=None):
    """Load CSV (time, waterlevel_m) and return arrays."""
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


def find_csv(station):
    """Find CSV file for a station. Prefer UHSLC over IWLS."""
    code = station['code']

    # Check UHSLC first (longer data)
    if code in UHSLC_STATIONS:
        uhslc_id = UHSLC_STATIONS[code]
        for f in UHSLC_DIR.glob(f"{uhslc_id}_*.csv"):
            if f.stat().st_size > 5000:
                return f, 'UHSLC', USE_LAST_N_YEARS

    # Then IWLS
    for f in IWLS_DIR.glob(f"{code}_*.csv"):
        if f.stat().st_size > 5000:
            return f, 'IWLS', None  # Use all available data (only ~6 years)

    return None, None, None


def analyze_station(station):
    """Run UTide analysis for one station."""
    code = station['code']
    name = station['name']
    checkpoint_file = CHECKPOINT_DIR / f"{code}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        src = result.get('source', '?')
        yrs = result.get('n_obs', 0) / (24 * 365.25) if result.get('source') == 'UHSLC' else result.get('n_obs', 0) / (4 * 24 * 365.25)
        print(f"  ✓ Checkpoint ({src}, {yrs:.1f}J, R²={result['r_squared']:.4f})")
        return result

    csv_path, source, use_years = find_csv(station)
    if csv_path is None:
        print(f"  ✗ Keine CSV-Datei")
        return None

    t0 = time.time()
    datetimes_utc, levels = load_csv(csv_path, use_last_n_years=use_years)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  ✗ Zu wenig Daten ({n} Werte)")
        return None

    lat = station['lat']
    years = len(datetimes_utc) / (24 * 365.25) if source == 'UHSLC' else len(datetimes_utc) / (4 * 24 * 365.25)
    print(f"  UTide [{source}] ({len(datetimes_utc)} Beob., {years:.1f}J, lat={lat:.2f})...",
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
        'station': station,
        'source': source,
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
    province = station.get('province', 'Canada')
    source = result['source']

    lines = []
    lines.append(f"# Harmonic constants derived from {source} sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Canada")
    lines.append(f"# province: {province}")
    lines.append(f"# source: Derived from {source} data with UTide harmonic analysis")
    lines.append(f"# station_id_context: CHS-{station['code']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: LLWLT")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, {province}, Canada")
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

    # Load station catalog
    with open(CATALOG_PATH) as f:
        all_stations = json.load(f)

    # Assign provinces
    for s in all_stations:
        s['province'] = get_province(s['code'], s['lat'], s['lon'], s['name'])

    # Sort by province, then by name
    all_stations.sort(key=lambda s: (s['province'], s['name']))

    # Exclude Great Lakes stations (no significant tidal range)
    GREAT_LAKES_CODES = {str(c) for c in range(10000, 15000)}
    # More precise: exclude codes 10xxx-14xxx (Great Lakes / Ontario inland)
    all_stations = [s for s in all_stations
                    if not (10000 <= int(s['code']) <= 14999)]

    # Count available CSVs
    n_available = sum(1 for s in all_stations if find_csv(s)[0] is not None)

    print("=" * 70)
    print("UTide Harmonic Analysis — ALL Canadian Tide Stations")
    print(f"Quellen: UHSLC ({USE_LAST_N_YEARS}J) + CHS IWLS (~6J)")
    print("=" * 70)
    print(f"Stationen gesamt:  {len(all_stations)}")
    print(f"Mit Daten:         {n_available}")
    print(f"Checkpoints:       {CHECKPOINT_DIR}")
    print()

    # Group by province for display
    from collections import OrderedDict
    by_prov = OrderedDict()
    for s in all_stations:
        by_prov.setdefault(s['province'], []).append(s)

    results = []
    total = 0
    success = 0
    failed = 0
    skipped = 0

    for province, stations in by_prov.items():
        n_with_data = sum(1 for s in stations if find_csv(s)[0] is not None)
        if n_with_data == 0:
            continue

        print(f"\n{'━'*70}")
        print(f"  {province} ({n_with_data} Stationen)")
        print(f"{'━'*70}")

        for s in stations:
            csv_path, source, _ = find_csv(s)
            if csv_path is None:
                continue

            total += 1
            print(f"\n[{total}/{n_available}] {s['code']} | {s['name']}")

            result = analyze_station(s)
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

    # Summary table by province
    print(f"\n\n{'='*70}")
    print("ZUSAMMENFASSUNG nach Provinz")
    print(f"{'='*70}")
    print(f"{'Provinz':<30s} {'N':>3s} {'Ø R²':>7s} {'Ø RMS':>8s} {'Ø M2':>7s}")
    print(f"{'─'*30} {'─'*3} {'─'*7} {'─'*8} {'─'*7}")

    prov_results = {}
    for r in results:
        prov = r['station'].get('province', '?')
        prov_results.setdefault(prov, []).append(r)

    for prov in sorted(prov_results.keys()):
        rs = prov_results[prov]
        avg_r2 = np.mean([r['r_squared'] for r in rs])
        avg_rms = np.mean([r['rms_error'] for r in rs])
        avg_m2 = np.mean([r['m2_amp'] for r in rs])
        print(f"{prov:<30s} {len(rs):>3d} {avg_r2:>6.4f}  {avg_rms:>7.4f}  {avg_m2:>6.4f}")

    print(f"\nGesamt: {success} erfolgreich, {failed} fehlgeschlagen")

    # Station detail table
    print(f"\n{'='*70}")
    print("DETAIL: Alle Stationen")
    print(f"{'='*70}")
    print(f"{'Station':<30s} {'Quelle':>6s} {'Jahre':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s} {'K1':>7s}")
    print(f"{'─'*30} {'─'*6} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

    current_prov = None
    for r in results:
        prov = r['station'].get('province', '?')
        if prov != current_prov:
            current_prov = prov
            print(f"\n  ── {prov} ──")

        src = r['source']
        if src == 'UHSLC':
            years = r['n_obs'] / (24 * 365.25)
        else:
            years = r['n_obs'] / (4 * 24 * 365.25)

        print(f"{r['station']['name']:<30s} {src:>6s} {years:>5.1f}  "
              f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  "
              f"{r['m2_amp']:>6.4f}  {r['k1_amp']:>6.4f}")


if __name__ == '__main__':
    main()
