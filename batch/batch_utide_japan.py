#!/usr/bin/env python3
"""
UTide harmonic analysis for Japan stations from JMA hourly tide data.
Creates harmonics_utide_japan.txt (ISO-8859-1).

Stations: 239 JMA tide gauge stations
Data: JMA hourly observed sea level (cm, JST=UTC+9), years 2011-2025
Format: fixed-width, 24 values x 3 chars per line, 1 line per day
Nodal cycle limit: 15 years (within 19-year max).
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import csv
import os
import numpy as np
from datetime import datetime, timedelta, timezone
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
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_japan.txt")
DATA_DIR = Path("/home/oliver/water_levels/JMA_Japan")
STATION_CSV = Path("/tmp/jma_stations_romanized_final.csv")

JMA_BASE = 'https://www.data.jma.go.jp/gmd/kaiyou/data/db/tide/suisan/txt'
YEARS = list(range(2011, 2026))  # 15 years

JST = timezone(timedelta(hours=9))
UTC = timezone.utc

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


def load_station_list():
    """Load JMA station list from CSV (romanized names)."""
    stations = []
    with open(STATION_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            stations.append({
                'code': row['code'],
                'name': row['romanized'].strip('"'),
                'lat': float(row['lat']),
                'lon': float(row['lon']),
            })
    return stations


def download_jma(station):
    """Download JMA hourly tide data for all years, return path to merged file."""
    code = station['code']
    name = station['name']
    merged_path = DATA_DIR / f"{code}.txt"

    if merged_path.exists() and merged_path.stat().st_size > 50000:
        lines = sum(1 for _ in open(merged_path))
        print(f"  Bereits vorhanden ({lines} Tage)")
        return str(merged_path)

    all_lines = []
    for year in YEARS:
        url = f"{JMA_BASE}/{year}/{code}.txt"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200 and len(resp.text) > 100:
                all_lines.extend(resp.text.strip().split('\n'))
            else:
                pass  # year not available
        except Exception:
            pass
        timer.sleep(0.2)  # rate limit

    if not all_lines:
        print(f"  Keine Daten verfuegbar")
        return None

    merged_path.write_text('\n'.join(all_lines) + '\n')
    n_days = len(all_lines)
    n_years = n_days / 365.25
    print(f"  {n_days} Tage heruntergeladen ({n_years:.1f} Jahre)")
    return str(merged_path)


def parse_jma_file(filepath):
    """Parse JMA fixed-width hourly tide file.

    Format per line:
      pos 0-71:  24 hourly values, 3 chars each (cm, right-justified)
      pos 72-73: 2-digit year
      pos 74-75: month (right-justified)
      pos 76-77: day (right-justified)
      pos 78-79: station code

    Missing values: 999 or negative-hundreds that look like 999.
    Times are JST (UTC+9), converted to UTC.
    """
    times = []
    levels = []

    with open(filepath) as f:
        for line in f:
            if len(line.rstrip()) < 80:
                continue

            # Parse date
            try:
                yy = int(line[72:74])
                mm = int(line[74:76])
                dd = int(line[76:78])
                year = 2000 + yy if yy < 50 else 1900 + yy
            except (ValueError, IndexError):
                continue

            # Parse 24 hourly values
            for hour in range(24):
                start = hour * 3
                val_str = line[start:start + 3].strip()
                if not val_str:
                    continue
                try:
                    val = int(val_str)
                except ValueError:
                    continue
                if val >= 900 or val <= -900:
                    continue

                # JST -> UTC
                dt_jst = datetime(year, mm, dd, hour, tzinfo=JST)
                dt_utc = dt_jst.astimezone(UTC).replace(tzinfo=None)
                times.append(dt_utc)
                levels.append(val / 100.0)  # cm -> meters

    return np.array(times), np.array(levels)



def analyze_station(station, data_path):
    """Run UTide analysis on a JMA station."""
    t0 = timer.time()
    name = station['name']
    code = station['code']
    lat = station['lat']
    lon = station['lon']

    datetimes_utc, levels = parse_jma_file(data_path)

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
        'code': code,
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
    """Format a single station as XTide harmonics block."""
    name = result['name']
    code = result['code']
    lat = result['lat']
    lon = result['lon']

    location = f"{name}, Japan"

    lines = []
    lines.append(f"# Harmonic constants derived from JMA hourly tide gauge data")
    lines.append(f"# using UTide (v{utide.__version__}) harmonic analysis")
    lines.append(f"# {result['n_obs']} hourly observations")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {location}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Japan")
    lines.append(f"# source: JMA hourly tide gauge data (station {code}), UTide analysis")
    lines.append(f"# station_id_context: JMA {code}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: station datum (JMA)")
    lines.append(f"# confidence: 9")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{location}")
    lines.append(f"+09:00 :Asia/Tokyo")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    print("=" * 70)
    print("UTide Harmonic Analysis -- Japan (JMA)")
    print("=" * 70)
    print()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    header = read_header_from_template(TEMPLATE_PATH)
    stations = load_station_list()
    print(f"{len(stations)} Stationen geladen")
    print()

    results = []
    failed = []
    for i, station in enumerate(stations):
        print(f"[{i+1}/{len(stations)}] {station['name']} ({station['code']})")

        data_path = download_jma(station)
        if data_path is None:
            failed.append(station['code'])
            print()
            continue

        result = analyze_station(station, data_path)
        if result:
            results.append(result)
        else:
            failed.append(station['code'])
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
    if failed:
        print(f"Fehlgeschlagen: {len(failed)} ({', '.join(failed)})")
    print()
    for r in results:
        print(f"  {r['code']:4s} {r['name']:20s}  R²={r['r_squared']:.4f}  M2={r['m2_amp']:.4f}m  "
              f"K1={r['k1_amp']:.4f}m  RMS={r['rms_error']:.4f}m")


if __name__ == '__main__':
    main()
