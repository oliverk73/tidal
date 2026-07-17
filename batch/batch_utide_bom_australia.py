#!/usr/bin/env python3
"""
UTide harmonic analysis for Australian BOM tide stations.
Uses annual prediction PDFs (HW/NW times and heights) from BOM.
Cosine-interpolates HW/NW to 15-min time series, then runs UTide.

Resource-efficient: processes one station at a time, frees memory between stations.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
import json
import re
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import pickle
import gc
import fitz  # PyMuPDF

import utide
from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

PDF_DIR = Path("/home/oliver/weather/tide_tables/australia")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_australia.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_australia_bom.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_bom_au")
STATIONS_FILE = Path("/tmp/bom_new_stations.json")

MONTHS = {
    'JANUARY': 1, 'FEBRUARY': 2, 'MARCH': 3, 'APRIL': 4,
    'MAY': 5, 'JUNE': 6, 'JULY': 7, 'AUGUST': 8,
    'SEPTEMBER': 9, 'OCTOBER': 10, 'NOVEMBER': 11, 'DECEMBER': 12,
}

DAYS_OF_WEEK = {'MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'}

# State timezone info: (standard_offset_hours, dst_offset_hours_or_None)
# DST in Australia: first Sunday in October to first Sunday in April
STATE_TZ = {
    'NSW': (10.0, 11.0),
    'VIC': (10.0, 11.0),
    'TAS': (10.0, 11.0),
    'SA':  (9.5, 10.5),
    'QLD': (10.0, None),  # no DST
    'WA':  (8.0, None),   # no DST
    'NT':  (9.5, None),   # no DST
}

# State full names for output
STATE_NAMES = {
    'NSW': 'New South Wales',
    'VIC': 'Victoria',
    'TAS': 'Tasmania',
    'SA': 'South Australia',
    'QLD': 'Queensland',
    'WA': 'Western Australia',
    'NT': 'Northern Territory',
}

# 67 constituents — fewer than CHS (93) because interpolated HW/NW
# loses shallow-water detail, but more than standard 37
CONSTIT_67 = [
    # Major diurnal
    'K1', 'O1', 'P1', 'Q1', 'J1', 'OO1', '2Q1', 'RHO1',
    'NO1', 'CHI1', 'PI1', 'PHI1', 'PSI1', 'SIG1', 'THE1', 'SO1',
    # Major semidiurnal
    'M2', 'S2', 'N2', 'K2', 'L2', '2N2', 'R2', 'T2',
    'LDA2', 'MU2', 'NU2', 'EPS2', 'ETA2',
    # Long period
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    # Terdiurnal
    'M3', 'MK3', 'MO3', 'SK3', 'SO3',
    # Quarter-diurnal (limited by interpolation quality)
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4',
    # Sixth-diurnal
    'M6', '2MS6', '2MN6',
    # Shallow water
    'M8',
    # Extra
    'H1', 'H2', 'S1',
    # Additional useful ones
    'ALP1', 'BET1', 'TAU1', 'UPS1',
    '2SM2', 'OP2', 'MKS2', 'SKM2',
    'NO3',
    'N4', '3MS4',
    '2MK5', '2SK5',
    '2MK6', 'MSK6',
]


def get_dst_transitions(year):
    """Return (DST_start, DST_end) for Australian DST in a given year.
    DST starts first Sunday in October, ends first Sunday in April.
    Returns naive datetimes in local standard time."""
    # DST ends first Sunday in April of `year`
    apr1 = datetime(year, 4, 1)
    dst_end_day = apr1 + timedelta(days=(6 - apr1.weekday()) % 7)
    dst_end = datetime(year, dst_end_day.month, dst_end_day.day, 3, 0)  # 3:00 AM DST → 2:00 AM ST

    # DST starts first Sunday in October of `year`
    oct1 = datetime(year, 10, 1)
    dst_start_day = oct1 + timedelta(days=(6 - oct1.weekday()) % 7)
    dst_start = datetime(year, dst_start_day.month, dst_start_day.day, 2, 0)  # 2:00 AM ST → 3:00 AM DST

    return dst_start, dst_end


def local_to_utc(dt_local, state, year):
    """Convert local time (as printed in PDF) to UTC datetime.
    Handles DST for states that observe it."""
    std_offset, dst_offset = STATE_TZ[state]

    if dst_offset is None:
        # No DST
        return dt_local - timedelta(hours=std_offset)

    # Check if DST is in effect
    dst_start, dst_end = get_dst_transitions(year)

    # DST is in effect from dst_start (Oct) to end of year,
    # and from start of year to dst_end (Apr)
    # But we need to handle the year boundary:
    # For year Y, DST runs: Oct Y → Apr Y+1
    # So for a date in Jan-Mar, check against previous October
    if dt_local.month >= 10:
        # After October: check if after this year's DST start
        if dt_local >= dst_start:
            return dt_local - timedelta(hours=dst_offset)
    elif dt_local.month <= 4:
        # Jan-Apr: DST from previous year's October still in effect until April end
        dst_end_this = dst_end  # first Sunday April
        if dt_local < dst_end_this:
            return dt_local - timedelta(hours=dst_offset)
        elif dt_local.month == dst_end_this.month and dt_local.day == dst_end_this.day:
            # Transition day — times before 3AM DST (=2AM ST) are still DST
            if dt_local.hour < 3:
                return dt_local - timedelta(hours=dst_offset)

    return dt_local - timedelta(hours=std_offset)


def parse_pdf_hwlw(pdf_path, year):
    """Extract HW/NW times and heights from a BOM annual prediction PDF.
    Returns list of (datetime_local, height_m) tuples."""
    doc = fitz.open(pdf_path)
    entries = []

    for page_idx in range(doc.page_count):  # try all pages
        text = doc[page_idx].get_text()
        lines = text.split('\n')

        current_month = None
        current_day = None

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Check for month name
            if line in MONTHS:
                current_month = MONTHS[line]
                i += 1
                continue

            # Check for day number (1-31) followed by day-of-week on next line
            if line.isdigit() and 1 <= int(line) <= 31:
                candidate_day = int(line)
                # Look ahead for day-of-week
                if i + 1 < len(lines) and lines[i + 1].strip() in DAYS_OF_WEEK:
                    current_day = candidate_day
                    i += 2  # skip day number and day-of-week
                    # Check if month name follows
                    if i < len(lines) and lines[i].strip() in MONTHS:
                        current_month = MONTHS[lines[i].strip()]
                        i += 1
                    # Skip "Time     m" header if present
                    if i < len(lines) and 'Time' in lines[i] and 'm' in lines[i]:
                        i += 1
                    continue

            # Check for time/height entry
            m = re.match(r'^(\d{4})\s+(\d+\.\d+)$', line)
            if m and current_month and current_day:
                time_str = m.group(1)
                height = float(m.group(2))
                hour = int(time_str[:2])
                minute = int(time_str[2:])

                if hour < 24 and minute < 60:
                    try:
                        dt = datetime(year, current_month, current_day, hour, minute)
                        entries.append((dt, height))
                    except ValueError:
                        pass  # invalid date (e.g., Feb 30)

            i += 1

    doc.close()
    return entries


def cosine_interpolate(hw_lw_utc, target_interval_min=15):
    """Interpolate HW/NW points to regular time series using half-cosine.

    Between consecutive extremes, the tide follows approximately a half-cosine curve.
    This preserves the timing and height of all extremes while creating a smooth,
    physically reasonable interpolation.
    """
    if len(hw_lw_utc) < 4:
        return None, None

    # Sort by time
    hw_lw_utc.sort(key=lambda x: x[0])

    # Create regular time grid
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

    # For each target time, find surrounding HW/NW and interpolate
    hw_times = [e[0] for e in hw_lw_utc]
    hw_levels = [e[1] for e in hw_lw_utc]

    j = 0  # index into hw_lw_utc
    for i, t in enumerate(times):
        # Advance j so hw_times[j] <= t < hw_times[j+1]
        while j < len(hw_times) - 2 and hw_times[j + 1] <= t:
            j += 1

        if j >= len(hw_times) - 1:
            levels[i] = hw_levels[-1]
            continue

        # Cosine interpolation between hw_lw_utc[j] and hw_lw_utc[j+1]
        t0 = hw_times[j]
        t1 = hw_times[j + 1]
        h0 = hw_levels[j]
        h1 = hw_levels[j + 1]

        dt_total = (t1 - t0).total_seconds()
        if dt_total <= 0:
            levels[i] = h0
            continue

        dt = (t - t0).total_seconds()
        frac = dt / dt_total

        # Half-cosine: smooth transition from h0 to h1
        # cos goes from 1 to -1 as frac goes 0 to 1
        # so (1 - cos(pi*frac))/2 goes from 0 to 1
        w = (1 - np.cos(np.pi * frac)) / 2
        levels[i] = h0 * (1 - w) + h1 * w

    datetimes_py = np.array([t for t in times])
    return datetimes_py, levels


def analyze_station(code, name, state, lat, lon, years=[2025, 2026, 2027]):
    """Run UTide analysis for one BOM station."""
    checkpoint_file = CHECKPOINT_DIR / f"{state}_{code}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        print(f"  ✓ Checkpoint (R²={result['r_squared']:.4f})")
        return result

    t0 = time.time()

    # Extract HW/NW from all year PDFs
    all_entries = []
    for year in years:
        pdf_name = f"IDO59001_{year}_{state}_{code}.pdf"
        pdf_path = PDF_DIR / pdf_name
        if not pdf_path.exists():
            print(f"  ✗ PDF fehlt: {pdf_name}")
            return None

        entries = parse_pdf_hwlw(str(pdf_path), year)
        # Convert to UTC
        entries_utc = [(local_to_utc(dt, state, year), h) for dt, h in entries]
        all_entries.extend(entries_utc)
        print(f"    {year}: {len(entries)} HW/NW-Punkte", flush=True)

    if len(all_entries) < 100:
        print(f"  ✗ Zu wenig Daten ({len(all_entries)} HW/NW)")
        return None

    # Sort and remove duplicates
    all_entries.sort(key=lambda x: x[0])
    # Remove entries where time goes backwards (DST artifacts)
    cleaned = [all_entries[0]]
    for entry in all_entries[1:]:
        if entry[0] > cleaned[-1][0]:
            cleaned.append(entry)
    all_entries = cleaned

    total_hwlw = len(all_entries)
    print(f"  Gesamt: {total_hwlw} HW/NW-Punkte über {len(years)} Jahre")

    # Cosine interpolation to 15-min time series
    print(f"  Interpoliere...", end='', flush=True)
    datetimes_utc, levels = cosine_interpolate(all_entries)

    if datetimes_utc is None:
        print(" FEHLER: Interpolation gescheitert")
        return None

    n_points = len(datetimes_utc)
    years_span = n_points / (4 * 24 * 365.25)
    print(f" {n_points} Punkte ({years_span:.1f}J)")

    # Run UTide
    print(f"  UTide ({n_points} Beob., lat={lat:.2f})...", end='', flush=True)
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
        'n_obs': n_points,
        'n_hwlw': total_hwlw,
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'code': code,
        'name': name,
        'state': state,
        'lat': lat,
        'lon': lon,
        'duration': duration,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    # Free memory
    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()

    print(f"  R²={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m ({duration:.0f}s)")

    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    name = result['name']
    state = STATE_NAMES.get(result['state'], result['state'])
    lat = result['lat']
    lon = result['lon']
    code = result['code']

    lines = []
    lines.append(f"# Harmonic constants derived from BOM tide predictions (reverse-engineered)")
    lines.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/NW data")
    lines.append(f"# {result['n_hwlw']} HW/NW points -> {result['n_obs']} interpolated points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}, {state}, Australia")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Australia")
    lines.append(f"# state: {state}")
    lines.append(f"# source: Derived from BOM tide predictions (reverse-engineered) with UTide harmonic analysis")
    lines.append(f"# station_id_context: BOM-{result['state']}-{code}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: LAT")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, {state}, Australia")
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

    # Load new stations list
    with open(STATIONS_FILE) as f:
        stations_raw = json.load(f)

    # Parse station list: each entry is [code_key, display_name, {metadata}]
    stations = []
    for entry in stations_raw:
        code_key = entry[0]   # e.g., "NSW_TP013"
        display_name = entry[1]  # e.g., "Evans Head"
        meta = entry[2]
        state = meta['state']
        code = meta['code']  # e.g., "TP013"
        lat = meta['lat']
        lon = meta['lon']
        stations.append({
            'code': code,
            'name': display_name,
            'state': state,
            'lat': lat,
            'lon': lon,
        })

    print("=" * 70)
    print("UTide Harmonic Analysis — Australia (BOM Annual Predictions)")
    print("=" * 70)
    print(f"Stationen: {len(stations)}")
    print()

    results = []
    errors = []

    for i, s in enumerate(stations):
        print(f"\n[{i+1}/{len(stations)}] {s['state']}_{s['code']} | {s['name']} "
              f"({s['lat']:.4f}, {s['lon']:.4f})")

        # Check which years are available
        available_years = []
        for year in [2025, 2026, 2027]:
            pdf_name = f"IDO59001_{year}_{s['state']}_{s['code']}.pdf"
            if (PDF_DIR / pdf_name).exists():
                available_years.append(year)

        if len(available_years) < 2:
            print(f"  ✗ Nur {len(available_years)} Jahre verfügbar, überspringe")
            errors.append((s['name'], "zu wenig Jahre"))
            continue

        result = analyze_station(
            s['code'], s['name'], s['state'], s['lat'], s['lon'],
            years=available_years
        )
        if result is not None:
            results.append(result)
        else:
            errors.append((s['name'], "Analyse fehlgeschlagen"))

        # Free memory periodically
        if (i + 1) % 20 == 0:
            gc.collect()

    # Write harmonics file
    if results:
        # Check if template exists, if not use another UTide Australia file
        if TEMPLATE_PATH.exists():
            header = read_header_from_template(TEMPLATE_PATH)
        else:
            # Use any existing UTide template
            alt_template = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt")
            header = read_header_from_template(alt_template)

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
        print(f"{'Station':<45s} {'Code':>6s} {'HW/NW':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s} {'K1':>7s}")
        print(f"{'─'*45} {'─'*6} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

        for r in results:
            print(f"{r['name']:<45s} {r['code']:>6s} {r['n_hwlw']:>5d}  "
                  f"{r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  "
                  f"{r['m2_amp']:>6.4f}  {r['k1_amp']:>6.4f}")

        print(f"\nGesamt: {len(results)} Stationen erfolgreich")
        avg_r2 = np.mean([r['r_squared'] for r in results])
        print(f"Durchschnittliches R²: {avg_r2:.4f}")

    if errors:
        print(f"\n{len(errors)} Fehler:")
        for name, reason in errors:
            print(f"  ✗ {name}: {reason}")


if __name__ == '__main__':
    main()
