#!/usr/bin/env python3
"""
UTide harmonic analysis for Philippine NAMRIA tide stations.
Uses hourly predictions downloaded from NAMRIA PH TIDES API.

Data is in Philippine Standard Time (PHT = UTC+8), converted to UTC for UTide.
Since these are predictions (not observations), the R² should be very high.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import json
import re
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time
import pickle
import gc
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

DATA_DIR = Path("/home/oliver/water_levels/Philippines_NAMRIA")
STATIONS_FILE = Path("/home/oliver/harmonics/help/namria_stations.json")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_mod.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_philippines_namria.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_namria_ph")

PHT_OFFSET_HOURS = 8  # Philippine Standard Time = UTC+8

# 67 constituents (same as BOM analysis — predictions don't need 93)
CONSTIT_67 = [
    'K1', 'O1', 'P1', 'Q1', 'J1', 'OO1', '2Q1', 'RHO1',
    'NO1', 'CHI1', 'PI1', 'PHI1', 'PSI1', 'SIG1', 'THE1', 'SO1',
    'M2', 'S2', 'N2', 'K2', 'L2', '2N2', 'R2', 'T2',
    'LDA2', 'MU2', 'NU2', 'EPS2', 'ETA2',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4',
    'M6', '2MS6', '2MN6',
    'M8',
    'H1', 'H2', 'S1',
    'ALP1', 'BET1', 'TAU1', 'UPS1',
    '2SM2', 'OP2', 'MKS2', 'SKM2',
    'NO3',
    'N4', '3MS4',
    '2MK5', '2SK5',
    '2MK6', 'MSK6',
]

# Stations already covered by UHSLC UTide (skip these)
UHSLC_STATIONS = {
    'Manila South Harbor', 'Legazpi City, Albay', 'Davao City',
    'Jolo, Sulu', 'Cebu City, Cebu', 'Puerto Princesa, Palawan',
    'Subic Bay, Zambales', 'Currimao, Ilocos Norte', 'Lubang, Occidental Mindoro',
}


def parse_dms(dms_str):
    """Parse DMS coordinate string to decimal degrees."""
    m = re.match(r"(\d+)°\s*(\d+)'\s*([\d.]+)\"\s*([NSEW])", dms_str)
    if not m:
        return None
    deg = float(m.group(1))
    mins = float(m.group(2))
    secs = float(m.group(3))
    direction = m.group(4)
    dd = deg + mins / 60 + secs / 3600
    if direction in ('S', 'W'):
        dd = -dd
    return dd


def load_hourly_json(json_path):
    """Load NAMRIA hourly JSON and convert to UTC datetime + levels arrays."""
    with open(json_path) as f:
        data = json.load(f)

    rows = []
    for entry in data:
        date_str = entry['date']
        hour_str = entry['hour']
        tide_str = entry['tide']

        try:
            # Parse "01/01/2023" + "0:00"
            dt_local = datetime.strptime(f"{date_str} {hour_str}", "%m/%d/%Y %H:%M")
            dt_utc = dt_local - timedelta(hours=PHT_OFFSET_HOURS)
            level = float(tide_str)
            rows.append((dt_utc, level))
        except (ValueError, TypeError):
            continue

    if not rows:
        return None, None

    rows.sort(key=lambda x: x[0])
    datetimes = np.array([r[0] for r in rows])
    levels = np.array([r[1] for r in rows], dtype=np.float64)
    return datetimes, levels


def analyze_station(json_path, meta):
    """Run UTide analysis for one NAMRIA station."""
    sid = meta['id']
    checkpoint_file = CHECKPOINT_DIR / f"{sid}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        print(f"  Checkpoint (R²={result['r_squared']:.4f})")
        return result

    t0 = time.time()
    datetimes_utc, levels = load_hourly_json(json_path)

    if datetimes_utc is None or len(datetimes_utc) < 2000:
        n = 0 if datetimes_utc is None else len(datetimes_utc)
        print(f"  Zu wenig Daten ({n} Werte)")
        return None

    lat = parse_dms(meta.get('coordinates_lat', '')) or 0
    lon = parse_dms(meta.get('coordinates_long', '')) or 0

    years = len(datetimes_utc) / (24 * 365.25)
    print(f"  UTide solve ({len(datetimes_utc)} Beob., {years:.1f} Jahre, lat={lat:.2f})...",
          end='', flush=True)

    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_67,
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
        'meta': meta,
        'lat': lat,
        'lon': lon,
        'duration': duration,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()

    print(f"  R²={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m ({duration:.0f}s)")

    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    meta = result['meta']
    name = meta['name']
    lat = result['lat']
    lon = result['lon']

    lines = []
    lines.append(f"# Harmonic constants derived from NAMRIA hourly tide predictions")
    lines.append(f"# using UTide (v{utide.__version__}) with {result['n_obs']} hourly values")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Philippines")
    lines.append(f"# source: Derived from NAMRIA PH TIDES predictions with UTide harmonic analysis")
    lines.append(f"# station_id_context: NAMRIA-{meta['code']}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: MLLW")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, Philippines")
    lines.append(f"+00:00 :Asia/Manila")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    header = read_header_from_template(TEMPLATE_PATH)

    with open(STATIONS_FILE) as f:
        all_stations = json.load(f)

    # Filter out UHSLC-covered stations
    stations = [s for s in all_stations if s['name'] not in UHSLC_STATIONS]
    skipped = len(all_stations) - len(stations)

    print("=" * 70)
    print("UTide Harmonic Analysis -- Philippines (NAMRIA PH TIDES)")
    print("=" * 70)
    print(f"Stationen gesamt: {len(all_stations)}")
    print(f"Uebersprungen (UHSLC vorhanden): {skipped}")
    print(f"Zu analysieren: {len(stations)}")
    print()

    results = []
    errors = []

    for i, meta in enumerate(stations):
        sid = meta['id']
        name = meta['name']
        safe = name.replace(' ', '_').replace("'", '').replace(',', '').replace('/', '_')

        # Find JSON file
        json_files = list(DATA_DIR.glob(f"{sid:02d}_*_hourly.json"))
        if not json_files:
            print(f"[{i+1:2d}/{len(stations)}] {name:45s} KEINE DATEN")
            errors.append(name)
            continue

        json_path = json_files[0]
        print(f"[{i+1:2d}/{len(stations)}] {name}")
        result = analyze_station(json_path, meta)
        if result:
            results.append(result)
        else:
            errors.append(name)

        gc.collect()
        print()

    if not results:
        print("Keine Ergebnisse!")
        return

    blocks = [format_station_block(r) for r in results]
    output = header + '\n' + '\n'.join(blocks) + '\n'
    OUTPUT_PATH.write_text(output, encoding='iso-8859-1')

    print(f"{'='*70}")
    print(f"Ergebnis: {len(results)} Stationen -> {OUTPUT_PATH}")
    if errors:
        print(f"Fehler: {len(errors)} Stationen: {', '.join(errors)}")
    print()
    for r in results:
        m = r['meta']
        print(f"  {m['name']:45s}  R²={r['r_squared']:.4f}  "
              f"M2={r['m2_amp']:.4f}m  K1={r['k1_amp']:.4f}m  "
              f"RMS={r['rms_error']:.4f}m")


if __name__ == '__main__':
    main()
