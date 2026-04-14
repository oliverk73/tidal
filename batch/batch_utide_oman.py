#!/usr/bin/env python3
"""
UTide harmonic analysis for Oman stations from UHSLC hourly data.
Creates harmonics_utide_oman.txt (ISO-8859-1).

Stations: Salalah (114), Masirah (113), Muscat (110)
Data: UHSLC Fast Delivery hourly sea level (mm, UTC)
Nodal cycle limit: ~19 years max.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import csv
import os
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import time as timer
import gc
import requests
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_mod.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_oman.txt")
DATA_DIR = Path("/home/oliver/water_levels/UHSLC_Oman")

ERDDAP_BASE = 'https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_fast.csv'

# 67 constituents
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

# ~19 years max (1 nodal cycle)
STATIONS = [
    {
        'uhslc_id': 114,
        'name': 'Salalah',
        'lat': 16.935,
        'lon': 54.007,
        # 36 years available, limit to 19
        'start': '2007-01-01',
        'end': '2025-12-31',
    },
    {
        'uhslc_id': 113,
        'name': 'Masirah',
        'lat': 20.687,
        'lon': 58.872,
        # 23 years available, limit to 19
        'start': '2001-01-01',
        'end': '2019-12-31',
    },
    {
        'uhslc_id': 110,
        'name': 'Muscat',
        'lat': 23.628,
        'lon': 58.565,
        # 11.5 years available, use all
        'start': '2009-12-01',
        'end': '2021-05-31',
    },
]


def download_uhslc(station):
    """Download UHSLC hourly fast delivery data via ERDDAP."""
    uhslc_id = station['uhslc_id']
    name = station['name']
    csv_path = DATA_DIR / f"{name.lower()}_{uhslc_id}.csv"

    if csv_path.exists() and csv_path.stat().st_size > 5000:
        lines = sum(1 for _ in open(csv_path)) - 2  # minus header + units
        print(f"  Bereits vorhanden ({lines} Werte)")
        return str(csv_path)

    start = station['start']
    end = station['end']

    url = (
        f"{ERDDAP_BASE}?time,sea_level"
        f"&uhslc_id={uhslc_id}"
        f"&time>={start}T00:00:00Z"
        f"&time<={end}T23:59:59Z"
        f"&orderBy(%22time%22)"
    )

    print(f"  Download UHSLC {uhslc_id} ({start} bis {end})...")
    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code == 200:
            csv_path.write_text(resp.text)
            lines = resp.text.count('\n') - 2
            print(f"  {lines} Werte heruntergeladen")
            return str(csv_path)
        else:
            print(f"  HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"  Fehler: {e}")
        return None


def load_uhslc_csv(csv_path):
    """Load UHSLC hourly CSV, return (datetimes_utc, levels_meters)."""
    times = []
    levels = []
    with open(csv_path) as f:
        reader = csv.reader(f)
        next(reader)  # header
        next(reader)  # units row
        for row in reader:
            if len(row) < 2:
                continue
            try:
                val = float(row[1])
            except ValueError:
                continue
            if val < -9000 or np.isnan(val):
                continue
            t = row[0].replace('Z', '')
            try:
                dt = datetime.fromisoformat(t)
            except ValueError:
                continue
            times.append(dt)
            levels.append(val / 1000.0)  # mm -> meters

    return np.array(times), np.array(levels)


def analyze_station(station, csv_path):
    t0 = timer.time()
    name = station['name']
    lat = station['lat']
    lon = station['lon']

    datetimes_utc, levels = load_uhslc_csv(csv_path)

    if len(datetimes_utc) < 1000:
        print(f"  Zu wenig Daten ({len(datetimes_utc)})")
        return None

    years_span = (datetimes_utc[-1] - datetimes_utc[0]).days / 365.25
    print(f"  {len(datetimes_utc)} Stundenwerte ({years_span:.1f} Jahre)")
    print(f"  Range: {levels.min():.3f} - {levels.max():.3f} m")

    print(f"  UTide (67 Konstituenten)...", end='', flush=True)
    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False,
            constit=CONSTIT_67,
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
            uid = utide_all_names.index(uname)
            utide_speed = const_table.freq[uid] * 360.0
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
    o1_amp = next((c['amplitude'] for c in constituents if c['name'] == 'O1'), 0)

    duration = timer.time() - t0

    result = {
        'mean': coef['mean'],
        'constituents': constituents,
        'n_analyzed': n_analyzed,
        'r_squared': r_squared,
        'rms_error': rms_error,
        'm2_amp': m2_amp,
        'k1_amp': k1_amp,
        'o1_amp': o1_amp,
        'n_obs': len(datetimes_utc),
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'name': name,
        'uhslc_id': station['uhslc_id'],
        'lat': lat,
        'lon': lon,
        'duration': duration,
    }

    print(f"  R²={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m, O1={o1_amp:.4f}m ({duration:.0f}s)")

    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()

    return result


def format_station_block(result):
    name = result['name']
    lat = result['lat']
    lon = result['lon']
    uhslc_id = result['uhslc_id']

    location = f"{name}, Oman"

    lines = []
    lines.append(f"# Harmonic constants derived from UHSLC hourly sea level data")
    lines.append(f"# using UTide (v{utide.__version__}) harmonic analysis")
    lines.append(f"# {result['n_obs']} hourly observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {location}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Oman")
    lines.append(f"# source: UHSLC hourly sea level data (station {uhslc_id}), UTide analysis")
    lines.append(f"# station_id_context: UHSLC {uhslc_id}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: station datum (UHSLC)")
    lines.append(f"# confidence: 9")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{location}")
    lines.append(f"+04:00 :Asia/Muscat")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    print("=" * 70)
    print("UTide Harmonic Analysis -- Oman (UHSLC)")
    print("=" * 70)
    print()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    header = read_header_from_template(TEMPLATE_PATH)

    results = []
    for i, station in enumerate(STATIONS):
        print(f"[{i+1}/{len(STATIONS)}] {station['name']} (UHSLC {station['uhslc_id']})")

        csv_path = download_uhslc(station)
        if csv_path is None:
            print()
            continue

        result = analyze_station(station, csv_path)
        if result:
            results.append(result)
        gc.collect()
        print()

    if not results:
        print("Keine Ergebnisse!")
        return

    results.sort(key=lambda r: r['name'])
    blocks = [format_station_block(r) for r in results]
    output = header + '\n' + '\n'.join(blocks) + '\n'
    OUTPUT_PATH.write_bytes(output.encode('iso-8859-1'))

    print(f"{'='*70}")
    print(f"Ergebnis: {len(results)} Stationen -> {OUTPUT_PATH}")
    print()
    for r in results:
        print(f"  {r['name']:20s}  R²={r['r_squared']:.4f}  M2={r['m2_amp']:.4f}m  "
              f"K1={r['k1_amp']:.4f}m  RMS={r['rms_error']:.4f}m")


if __name__ == '__main__':
    main()
