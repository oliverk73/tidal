#!/usr/bin/env python3
"""
UTide harmonic analysis for Hong Kong Observatory (HKO) tide stations.
Downloads HW/NW predictions from HKO open data API (2024-2028),
cosine-interpolates to 15-min time series, then runs UTide.

14 stations, free API, no login required.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import csv
import io
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import time
import pickle
import gc
import urllib.request

import utide
from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_hongkong_hko.txt")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_australia_bom.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_hongkong_hko")
CACHE_DIR = Path("/tmp/hko_tides")

API_BASE = "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php"
YEARS = [2024, 2025, 2026, 2027, 2028]

# Station definitions: code, name, lat, lon
STATIONS = [
    ('CLK', 'Chek Lap Kok',    22.3200, 113.9453),
    ('CCH', 'Cheung Chau',     22.2144, 114.0231),
    ('CMW', 'Chi Ma Wan',      22.2394, 114.0000),
    ('KLW', 'Ko Lau Wan',      22.4586, 114.3608),
    ('KCT', 'Kwai Chung',      22.3236, 114.1222),
    ('LOP', 'Lok On Pai',      22.3614, 114.0017),
    ('MWC', 'Ma Wan',          22.3639, 114.0714),
    ('QUB', 'Quarry Bay',      22.2911, 114.2133),
    ('SPW', 'Shek Pik',        22.2203, 113.8944),
    ('TAO', 'Tai O',           22.2535, 113.8638),
    ('TMW', 'Tai Miu Wan',     22.2697, 114.2886),
    ('TPK', 'Tai Po Kau',      22.4425, 114.1839),
    ('TBT', 'Tsim Bei Tsui',   22.4872, 114.0131),
    ('WAG', 'Waglan Island',   22.1833, 114.3028),
]

# UTide constituents to analyze (67 standard + shallow water)
CONSTIT_67 = [
    'M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1',
    'MU2', 'NU2', 'L2', 'T2', '2N2', 'LDA2', 'R2',
    'J1', 'OO1', '2Q1', 'RHO1', 'SIG1', 'CHI1', 'PHI1', 'THE1', 'PSI1',
    'PI1', 'S1',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4',
    'M6', '2MS6', '2MN6',
    'M8',
    'H1', 'H2',
    'ALP1', 'BET1', 'TAU1', 'UPS1',
    '2SM2', 'OP2', 'MKS2', 'SKM2',
    'NO3',
    'N4', '3MS4',
    '2MK5', '2SK5',
    '2MK6', 'MSK6',
]


def download_station_csv(code, year):
    """Download HW/NW CSV for one station and year from HKO API."""
    cache_file = CACHE_DIR / f"{code}_{year}.csv"
    if cache_file.exists():
        return cache_file.read_text(encoding='utf-8-sig')

    url = f"{API_BASE}?dataType=HLT&station={code}&year={year}&rformat=csv"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode('utf-8-sig')
        cache_file.write_text(text, encoding='utf-8')
        return text
    except Exception as e:
        print(f"    Download-Fehler {code}/{year}: {e}")
        return None


def parse_hko_csv(csv_text, year):
    """Parse HKO CSV into list of (datetime_utc, height_m) tuples.
    CSV format: Month,Date,Time,Height(m),Time,Height(m),Time,Height(m),Time,Height(m)
    Times in HK Time (UTC+8), heights in meters above Chart Datum.
    Up to 4 HW/NW events per day, empty fields when fewer."""
    entries = []
    reader = csv.reader(io.StringIO(csv_text))
    next(reader)  # skip header

    for row in reader:
        if len(row) < 4:
            continue
        month = int(row[0])
        day = int(row[1])

        # Up to 4 time/height pairs starting at index 2
        for i in range(2, len(row), 2):
            time_str = row[i].strip() if i < len(row) else ''
            height_str = row[i + 1].strip() if i + 1 < len(row) else ''

            if not time_str or not height_str:
                continue

            try:
                hh = int(time_str[:2])
                mm = int(time_str[2:4])
                height_m = float(height_str)
            except (ValueError, IndexError):
                continue

            # Handle midnight (2400 → next day 0000)
            if hh == 24:
                dt_local = datetime(year, month, day, 0, mm) + timedelta(days=1)
            else:
                dt_local = datetime(year, month, day, hh, mm)

            # Convert HK Time (UTC+8) to UTC
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


def analyze_station(code, name, lat, lon, entries_utc):
    """Run UTide analysis for one HKO station."""
    checkpoint_file = CHECKPOINT_DIR / f"{code}.pkl"
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
        'station_code': code,
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
    code = result['station_code']

    lines = []
    lines.append(f"# Harmonic constants derived from HKO tide predictions")
    lines.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/NW data")
    lines.append(f"# {result['n_hwlw']} HW/NW points -> {result['n_obs']} interpolated points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}, Hong Kong, China")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: China")
    lines.append(f"# source: HKO tide predictions, UTide analysis")
    lines.append(f"# station_id_context: HKO-{code}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Chart Datum")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, Hong Kong, China")
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
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("UTide Harmonic Analysis - Hong Kong Observatory (HKO)")
    print("=" * 70)
    print(f"Stationen: {len(STATIONS)}, Jahre: {YEARS[0]}-{YEARS[-1]}")
    print()

    results = []
    errors = []

    for i, (code, name, lat, lon) in enumerate(STATIONS):
        print(f"\n[{i+1}/{len(STATIONS)}] {code} | {name} ({lat:.4f}, {lon:.4f})")

        # Download all years
        all_entries = []
        for year in YEARS:
            csv_text = download_station_csv(code, year)
            if csv_text is None:
                continue
            entries = parse_hko_csv(csv_text, year)
            all_entries.extend(entries)
            print(f"  {year}: {len(entries)} HW/NW")

        print(f"  Gesamt: {len(all_entries)} HW/NW aus {len(YEARS)} Jahren")

        if len(all_entries) < 100:
            print(f"  Zu wenig Daten, ueberspringe")
            errors.append((name, "zu wenig Daten"))
            continue

        result = analyze_station(code, name, lat, lon, all_entries)
        if result is not None:
            results.append(result)
        else:
            errors.append((name, "Analyse fehlgeschlagen"))

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
    print(f"\n{'='*70}")
    print("ZUSAMMENFASSUNG")
    print(f"{'='*70}")
    print(f"{'Station':<25s} {'Code':>5s} {'HW/NW':>6s} {'R2':>7s} {'RMS':>7s} "
          f"{'M2':>7s} {'K1':>7s}")
    print(f"{'_'*25} {'_'*5} {'_'*6} {'_'*7} {'_'*7} {'_'*7} {'_'*7}")

    for r in results:
        print(f"{r['name']:<25s} {r['station_code']:>5s} {r['n_hwlw']:>6d} "
              f"{r['r_squared']:>7.4f} {r['rms_error']:>7.4f} "
              f"{r['m2_amp']:>7.4f} {r['k1_amp']:>7.4f}")

    if errors:
        print(f"\nFehler ({len(errors)}):")
        for name, err in errors:
            print(f"  {name}: {err}")

    print(f"\nGesamt: {len(results)} Stationen")
    if results:
        avg_r2 = np.mean([r['r_squared'] for r in results])
        print(f"Durchschnittliches R2: {avg_r2:.4f}")


if __name__ == '__main__':
    main()
