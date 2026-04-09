#!/usr/bin/env python3
"""
UTide harmonic analysis for Taiwan CWA tide stations.
Uses CWA opendata API (F-A0023-001) annual HW/NW predictions.
Cosine-interpolates HW/NW to 15-min time series, then runs UTide.

Includes 3 mainland China stations from the same dataset.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import json
import re
import numpy as np
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

API_URL = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/F-A0023-001?Authorization=rdec-key-123-45678-011121314&format=JSON"
CACHE_FILE = Path("/tmp/cwa_tides.json")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_taiwan_cwa.txt")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_australia_bom.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_taiwan_cwa")

# English names for stations (manually transliterated)
STATION_NAMES = {
    '11006': 'Danhai',
    '1102':  'Tamsui',
    '1116':  'Zhuwei',
    '112':   'Hsinchu',
    '113':   'Waipu',
    '1156':  'Boziliao',
    '1166':  'Dongshih',
    '1176':  'Jiangjun',
    '1186':  'Donggang',
    '1196':  'Houbihu',
    '1206':  'Linshanbi',
    '1226':  'Longdong',
    '1236':  'Wushih',
    '1246':  'Su-ao',
    '12540': 'Heping',
    '1256':  'Hualien',
    '1276':  'Chenggong',
    '1315':  'Pengjiayu',
    '13406': 'Jibei',
    '1356':  'Magong',
    '13606': 'Qimei',
    '1366':  'Wungang',
    '1386':  'Xiao Liuqiu',
    '1396':  'Lanyu',
    '1436':  'Taichung',
    '1456':  'Mailiao',
    '1486':  'Kaohsiung',
    '1496':  'Xunguangzui',
    '1516':  'Keelung',
    '1566':  'Shiti',
    '1586':  'Fugang',
    '1596':  'Dawu',
    '1676':  'Ludao',
    '1786':  'Yongan',
    '1826':  'Fulong',
    '1926':  'Matsu',
    '1956':  'Liaoluowan',
    '1966':  'Shuitou',
    '198':   'Pratas Island',
    '294':   'Minjiangkou',
    '295':   'Xiamen',
    '296':   'Shantou',
    '4A':    'Anping',
    'H0100': 'Taipei Port',
}

# Country for each station
STATION_COUNTRY = {
    '294': 'China',
    '295': 'China',
    '296': 'China',
}

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


def load_cwa_data():
    """Load CWA tide prediction data from cache or API."""
    if CACHE_FILE.exists():
        print(f"Lade aus Cache: {CACHE_FILE}")
        with open(CACHE_FILE) as f:
            return json.load(f)

    import urllib.request
    print(f"Lade von CWA API...")
    req = urllib.request.Request(API_URL)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    with open(CACHE_FILE, 'w') as f:
        json.dump(data, f)
    return data


def parse_hwlw_from_cwa(location):
    """Extract HW/NW times and heights from CWA JSON location entry.
    Heights are in cm (AboveChartDatum), converted to meters.
    Times are in UTC+8 (Taiwan Standard Time), converted to UTC."""
    entries = []
    daily = location.get('TimePeriods', {}).get('Daily', [])

    for day in daily:
        times = day.get('Time', [])
        # XML→JSON: single element becomes dict instead of list
        if isinstance(times, dict):
            times = [times]
        for event in times:
            dt_str = event['DateTime']  # e.g. "2026-01-01T02:14:00+08:00"
            height_cm = event['TideHeights']['AboveChartDatum']
            if height_cm is None or height_cm == '':
                continue
            height_m = float(height_cm) / 100.0

            # Parse datetime (UTC+8)
            # Format: 2026-01-01T02:14:00+08:00
            dt_local = datetime.strptime(dt_str[:19], '%Y-%m-%dT%H:%M:%S')
            # Convert to UTC (Taiwan is always UTC+8, no DST)
            dt_utc = dt_local - timedelta(hours=8)
            entries.append((dt_utc, height_m))

    return entries


def cosine_interpolate(hw_lw_utc, target_interval_min=15):
    """Interpolate HW/NW points to regular time series using half-cosine."""
    if len(hw_lw_utc) < 4:
        return None, None

    hw_lw_utc.sort(key=lambda x: x[0])

    t_start = hw_lw_utc[0][0]
    t_end = hw_lw_utc[-1][0]
    interval = timedelta(minutes=target_interval_min)

    times = []
    t = t_start
    while t <= t_end:
        times.append(t)
        t += interval

    if len(times) < 100:
        return None, None

    levels = np.zeros(len(times))
    hw_times = [e[0] for e in hw_lw_utc]
    hw_levels = [e[1] for e in hw_lw_utc]

    j = 0
    for i, t in enumerate(times):
        while j < len(hw_times) - 2 and hw_times[j + 1] <= t:
            j += 1
        if j >= len(hw_times) - 1:
            levels[i] = hw_levels[-1]
            continue

        t0, t1 = hw_times[j], hw_times[j + 1]
        h0, h1 = hw_levels[j], hw_levels[j + 1]
        dt_total = (t1 - t0).total_seconds()
        if dt_total <= 0:
            levels[i] = h0
            continue

        dt = (t - t0).total_seconds()
        frac = dt / dt_total
        w = (1 - np.cos(np.pi * frac)) / 2
        levels[i] = h0 * (1 - w) + h1 * w

    return np.array(times), levels


def analyze_station(sid, name, lat, lon, entries_utc):
    """Run UTide analysis for one CWA station."""
    checkpoint_file = CHECKPOINT_DIR / f"{sid}.pkl"
    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        print(f"  Checkpoint (R2={result['r_squared']:.4f})")
        return result

    t0 = time.time()

    if len(entries_utc) < 100:
        print(f"  Zu wenig Daten ({len(entries_utc)} HW/NW)")
        return None

    # Sort and deduplicate
    entries_utc.sort(key=lambda x: x[0])
    cleaned = [entries_utc[0]]
    for entry in entries_utc[1:]:
        if entry[0] > cleaned[-1][0]:
            cleaned.append(entry)
    entries_utc = cleaned
    total_hwlw = len(entries_utc)

    # Cosine interpolation
    print(f"  {total_hwlw} HW/NW, interpoliere...", end='', flush=True)
    datetimes_utc, levels = cosine_interpolate(entries_utc)

    if datetimes_utc is None:
        print(" FEHLER")
        return None

    n_points = len(datetimes_utc)
    years_span = n_points / (4 * 24 * 365.25)
    print(f" {n_points} Punkte ({years_span:.1f}J)")

    # UTide
    print(f"  UTide (lat={lat:.2f})...", end='', flush=True)
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

    # R2
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
        'n_obs': n_points,
        'n_hwlw': total_hwlw,
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'station_id': sid,
        'name': name,
        'lat': lat,
        'lon': lon,
        'duration': duration,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()

    print(f"  R2={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m ({duration:.0f}s)")
    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    name = result['name']
    lat = result['lat']
    lon = result['lon']
    sid = result['station_id']
    country = STATION_COUNTRY.get(sid, 'Taiwan')

    lines = []
    lines.append(f"# Harmonic constants derived from CWA tide predictions (reverse-engineered)")
    lines.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/NW data")
    lines.append(f"# {result['n_hwlw']} HW/NW points -> {result['n_obs']} interpolated points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}, {country}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: {country}")
    lines.append(f"# source: CWA tide predictions, UTide analysis")
    lines.append(f"# station_id_context: CWA-{sid}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Chart Datum")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, {country}")
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

    data = load_cwa_data()
    locations = data['cwaopendata']['Resources']['Resource']['Data']['TideForecasts']['Location']

    print("=" * 70)
    print("UTide Harmonic Analysis - Taiwan CWA Tide Predictions")
    print("=" * 70)
    print(f"Stationen: {len(locations)}")
    print()

    results = []
    errors = []

    for i, loc in enumerate(locations):
        sid = loc['StationID']
        name_cn = loc['StationName']
        name_en = STATION_NAMES.get(sid, name_cn)
        lat = float(loc['Latitude'])
        lon = float(loc['Longitude'])
        country = STATION_COUNTRY.get(sid, 'Taiwan')

        print(f"\n[{i+1}/{len(locations)}] {sid} | {name_en} ({name_cn}) "
              f"({lat:.4f}, {lon:.4f}) [{country}]")

        entries = parse_hwlw_from_cwa(loc)
        print(f"  {len(entries)} HW/NW aus API")

        if len(entries) < 100:
            print(f"  Zu wenig Daten, ueberspringe")
            errors.append((name_en, "zu wenig Daten"))
            continue

        result = analyze_station(sid, name_en, lat, lon, entries)
        if result is not None:
            results.append(result)
        else:
            errors.append((name_en, "Analyse fehlgeschlagen"))

        if (i + 1) % 10 == 0:
            gc.collect()

    # Write harmonics file
    if results:
        header = read_header_from_template(TEMPLATE_PATH)

        print(f"\n{'='*70}")
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
        print(f"\n{'='*70}")
        print("ZUSAMMENFASSUNG")
        print(f"{'='*70}")
        print(f"{'Station':<30s} {'ID':>6s} {'HW/NW':>6s} {'R2':>7s} {'RMS':>7s} {'M2':>7s} {'K1':>7s}")
        print(f"{'_'*30} {'_'*6} {'_'*6} {'_'*7} {'_'*7} {'_'*7} {'_'*7}")

        for r in results:
            print(f"{r['name']:<30s} {r['station_id']:>6s} {r['n_hwlw']:>5d}  "
                  f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  "
                  f"{r['m2_amp']:>6.4f}  {r['k1_amp']:>6.4f}")

        print(f"\nGesamt: {len(results)} Stationen")
        avg_r2 = np.mean([r['r_squared'] for r in results])
        print(f"Durchschnittliches R2: {avg_r2:.4f}")

    if errors:
        print(f"\n{len(errors)} Fehler:")
        for name, reason in errors:
            print(f"  {name}: {reason}")


if __name__ == '__main__':
    main()
