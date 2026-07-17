#!/usr/bin/env python3
"""
UTide harmonic analysis for Australian BOM tidal stream stations + missed tide stations.
Processes IDO59002 (tidal streams) and IDO59001 (tide) PDFs from australia2/.

Tidal streams: Slack/Maximum format with rates in knots.
Cosine-interpolates slack(0)/max(rate) to 15-min time series, then runs UTide.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import os
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

PDF_DIR = Path("/home/oliver/weather/tide_tables/australia2")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_australia_bom.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_bom_streams")

MONTHS = {
    'JANUARY': 1, 'FEBRUARY': 2, 'MARCH': 3, 'APRIL': 4,
    'MAY': 5, 'JUNE': 6, 'JULY': 7, 'AUGUST': 8,
    'SEPTEMBER': 9, 'OCTOBER': 10, 'NOVEMBER': 11, 'DECEMBER': 12,
}

DAYS_OF_WEEK = {'MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'}

STATE_TZ = {
    'NSW': (10.0, 11.0),
    'VIC': (10.0, 11.0),
    'TAS': (10.0, 11.0),
    'SA':  (9.5, 10.5),
    'QLD': (10.0, None),
    'WA':  (8.0, None),
    'NT':  (9.5, None),
}

STATE_NAMES = {
    'NSW': 'New South Wales', 'VIC': 'Victoria', 'TAS': 'Tasmania',
    'SA': 'South Australia', 'QLD': 'Queensland',
    'WA': 'Western Australia', 'NT': 'Northern Territory',
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

# Station definitions
STATIONS = [
    # Tidal stream stations (IDO59002 format)
    {
        'code': 'TS001', 'state': 'QLD', 'name': 'Hammond Rock',
        'lat': -10.5000, 'lon': 142.2167, 'type': 'stream',
        'pdf_prefix': 'IDO59002',
    },
    {
        'code': 'TS006', 'state': 'QLD', 'name': 'Oom Shoal - Mackay',
        'lat': -21.0500, 'lon': 149.2833, 'type': 'stream',
        'pdf_prefix': 'IDO59002',
    },
    {
        'code': 'TS001', 'state': 'VIC', 'name': 'The Rip',
        'lat': -38.2984, 'lon': 144.6307, 'type': 'stream',
        'pdf_prefix': 'IDO59002',
    },
    # Missed tide station (IDO59001 format)
    {
        'code': 'TP104', 'state': 'QLD', 'name': 'Serpentine Creek',
        'lat': -27.3500, 'lon': 153.1000, 'type': 'tide',
        'pdf_prefix': 'IDO59001',
    },
]


def get_dst_transitions(year):
    """Return (DST_start, DST_end) for Australian DST."""
    apr1 = datetime(year, 4, 1)
    dst_end_day = apr1 + timedelta(days=(6 - apr1.weekday()) % 7)
    dst_end = datetime(year, dst_end_day.month, dst_end_day.day, 3, 0)
    oct1 = datetime(year, 10, 1)
    dst_start_day = oct1 + timedelta(days=(6 - oct1.weekday()) % 7)
    dst_start = datetime(year, dst_start_day.month, dst_start_day.day, 2, 0)
    return dst_start, dst_end


def local_to_utc(dt_local, state, year):
    """Convert local time (as printed in PDF) to UTC."""
    std_offset, dst_offset = STATE_TZ[state]
    if dst_offset is None:
        return dt_local - timedelta(hours=std_offset)
    dst_start, dst_end = get_dst_transitions(year)
    if dt_local.month >= 10:
        if dt_local >= dst_start:
            return dt_local - timedelta(hours=dst_offset)
    elif dt_local.month <= 4:
        if dt_local < dst_end:
            return dt_local - timedelta(hours=dst_offset)
        elif dt_local.month == dst_end.month and dt_local.day == dst_end.day:
            if dt_local.hour < 3:
                return dt_local - timedelta(hours=dst_offset)
    return dt_local - timedelta(hours=std_offset)


def parse_pdf_stream(pdf_path, year):
    """Extract Slack/Maximum events from a BOM tidal stream PDF.
    Returns list of (datetime_local, rate_knots) tuples.
    Slack events have rate=0, max events have the signed rate."""
    doc = fitz.open(pdf_path)
    entries = []

    for page_idx in range(doc.page_count):
        text = doc[page_idx].get_text()
        lines = text.split('\n')

        current_month = None
        current_day = None

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Check for month
            if line in MONTHS:
                current_month = MONTHS[line]
                i += 1
                continue

            # Check for day number + day-of-week
            if line.isdigit() and 1 <= int(line) <= 31:
                candidate_day = int(line)
                if i + 1 < len(lines) and lines[i + 1].strip() in DAYS_OF_WEEK:
                    current_day = candidate_day
                    i += 2
                    if i < len(lines) and lines[i].strip() in MONTHS:
                        current_month = MONTHS[lines[i].strip()]
                        i += 1
                    # Skip headers
                    while i < len(lines) and ('Slack' in lines[i] or 'Time' in lines[i] or 'Rate' in lines[i]):
                        i += 1
                    continue

            if not current_month or not current_day:
                i += 1
                continue

            # Parse tidal stream entries:
            # Pattern 1: "HHMM HHMM  N.NN" or "HHMM HHMM -N.NN" (slack + max + rate)
            # Pattern 2: "HHMM  N.NN" or "HHMM -N.NN" (max only, no slack)
            # Pattern 3: "HHMM" alone (slack only)

            # Try pattern 1: slack_time max_time rate
            m1 = re.match(r'^(\d{4})\s+(\d{4})\s+(-?\d+\.\d+)$', line)
            if m1:
                slack_str, max_str, rate = m1.group(1), m1.group(2), float(m1.group(3))
                sh, sm = int(slack_str[:2]), int(slack_str[2:])
                mh, mm = int(max_str[:2]), int(max_str[2:])
                if sh < 24 and sm < 60 and mh < 24 and mm < 60:
                    try:
                        dt_slack = datetime(year, current_month, current_day, sh, sm)
                        dt_max = datetime(year, current_month, current_day, mh, mm)
                        entries.append((dt_slack, 0.0))
                        entries.append((dt_max, rate))
                    except ValueError:
                        pass
                i += 1
                continue

            # Try pattern 2: max_time rate (no slack)
            m2 = re.match(r'^(\d{4})\s+(-?\d+\.\d+)$', line)
            if m2:
                max_str, rate = m2.group(1), float(m2.group(2))
                mh, mm = int(max_str[:2]), int(max_str[2:])
                if mh < 24 and mm < 60:
                    try:
                        dt_max = datetime(year, current_month, current_day, mh, mm)
                        entries.append((dt_max, rate))
                    except ValueError:
                        pass
                i += 1
                continue

            # Try pattern 3: slack_time only (4 digits, no rate)
            m3 = re.match(r'^(\d{4})$', line)
            if m3:
                slack_str = m3.group(1)
                sh, sm = int(slack_str[:2]), int(slack_str[2:])
                if sh < 24 and sm < 60:
                    try:
                        dt_slack = datetime(year, current_month, current_day, sh, sm)
                        entries.append((dt_slack, 0.0))
                    except ValueError:
                        pass
                i += 1
                continue

            i += 1

    doc.close()
    return entries


def parse_pdf_hwlw(pdf_path, year):
    """Extract HW/NW times and heights from a standard BOM tide PDF."""
    doc = fitz.open(pdf_path)
    entries = []

    for page_idx in range(doc.page_count):
        text = doc[page_idx].get_text()
        lines = text.split('\n')

        current_month = None
        current_day = None

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if line in MONTHS:
                current_month = MONTHS[line]
                i += 1
                continue

            if line.isdigit() and 1 <= int(line) <= 31:
                candidate_day = int(line)
                if i + 1 < len(lines) and lines[i + 1].strip() in DAYS_OF_WEEK:
                    current_day = candidate_day
                    i += 2
                    if i < len(lines) and lines[i].strip() in MONTHS:
                        current_month = MONTHS[lines[i].strip()]
                        i += 1
                    if i < len(lines) and 'Time' in lines[i] and 'm' in lines[i]:
                        i += 1
                    continue

            m = re.match(r'^(\d{4})\s+(\d+\.\d+)$', line)
            if m and current_month and current_day:
                time_str = m.group(1)
                height = float(m.group(2))
                hour, minute = int(time_str[:2]), int(time_str[2:])
                if hour < 24 and minute < 60:
                    try:
                        dt = datetime(year, current_month, current_day, hour, minute)
                        entries.append((dt, height))
                    except ValueError:
                        pass
            i += 1

    doc.close()
    return entries


def cosine_interpolate(events_utc, target_interval_min=15):
    """Interpolate slack/max or HW/NW events to regular time series using half-cosine."""
    if len(events_utc) < 4:
        return None, None

    events_utc.sort(key=lambda x: x[0])

    t_start = events_utc[0][0]
    t_end = events_utc[-1][0]
    interval = timedelta(minutes=target_interval_min)

    times = []
    t = t_start
    while t <= t_end:
        times.append(t)
        t += interval

    if len(times) < 100:
        return None, None

    levels = np.zeros(len(times))
    ev_times = [e[0] for e in events_utc]
    ev_vals = [e[1] for e in events_utc]

    j = 0
    for i, t in enumerate(times):
        while j < len(ev_times) - 2 and ev_times[j + 1] <= t:
            j += 1
        if j >= len(ev_times) - 1:
            levels[i] = ev_vals[-1]
            continue

        t0, t1 = ev_times[j], ev_times[j + 1]
        h0, h1 = ev_vals[j], ev_vals[j + 1]
        dt_total = (t1 - t0).total_seconds()
        if dt_total <= 0:
            levels[i] = h0
            continue

        dt = (t - t0).total_seconds()
        frac = dt / dt_total
        w = (1 - np.cos(np.pi * frac)) / 2
        levels[i] = h0 * (1 - w) + h1 * w

    return np.array(times), levels


def analyze_station(station, years=[2025, 2026, 2027]):
    """Run UTide analysis for one station."""
    code = station['code']
    state = station['state']
    name = station['name']
    lat = station['lat']
    lon = station['lon']
    stype = station['type']
    prefix = station['pdf_prefix']

    checkpoint_file = CHECKPOINT_DIR / f"{state}_{code}.pkl"
    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        print(f"  Checkpoint (R²={result['r_squared']:.4f})")
        return result

    t0 = time.time()
    all_entries = []

    for year in years:
        pdf_name = f"{prefix}_{year}_{state}_{code}.pdf"
        pdf_path = PDF_DIR / pdf_name
        if not pdf_path.exists():
            print(f"  PDF fehlt: {pdf_name}")
            continue

        if stype == 'stream':
            entries = parse_pdf_stream(str(pdf_path), year)
        else:
            entries = parse_pdf_hwlw(str(pdf_path), year)

        entries_utc = [(local_to_utc(dt, state, year), v) for dt, v in entries]
        all_entries.extend(entries_utc)
        print(f"    {year}: {len(entries)} Ereignisse", flush=True)

    if len(all_entries) < 100:
        print(f"  Zu wenig Daten ({len(all_entries)})")
        return None

    # Sort and deduplicate
    all_entries.sort(key=lambda x: x[0])
    cleaned = [all_entries[0]]
    for entry in all_entries[1:]:
        if entry[0] > cleaned[-1][0]:
            cleaned.append(entry)
    all_entries = cleaned

    total_events = len(all_entries)
    unit = "knots" if stype == 'stream' else "m"
    print(f"  Gesamt: {total_events} Ereignisse ({unit})")

    # Cosine interpolation
    print(f"  Interpoliere...", end='', flush=True)
    datetimes_utc, values = cosine_interpolate(all_entries)

    if datetimes_utc is None:
        print(" FEHLER")
        return None

    n_points = len(datetimes_utc)
    years_span = n_points / (4 * 24 * 365.25)
    print(f" {n_points} Punkte ({years_span:.1f}J)")

    # UTide
    print(f"  UTide ({n_points} Beob., lat={lat:.2f})...", end='', flush=True)
    try:
        coef = utide.solve(
            datetimes_utc, values, lat=lat,
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

    # R²
    recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
    residuals = values - recon['h']
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((values - np.mean(values))**2)
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
        'n_events': total_events,
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'code': code,
        'name': name,
        'state': state,
        'lat': lat,
        'lon': lon,
        'type': stype,
        'duration': duration,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    del coef, recon, datetimes_utc, values, residuals
    gc.collect()

    print(f"  R²={r_squared:.4f}, RMS={rms_error:.4f}{unit}, M2={m2_amp:.4f}{unit}, "
          f"K1={k1_amp:.4f}{unit} ({duration:.0f}s)")
    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    name = result['name']
    state_name = STATE_NAMES.get(result['state'], result['state'])
    lat = result['lat']
    lon = result['lon']
    code = result['code']
    stype = result.get('type', 'tide')
    unit = "knots" if stype == 'stream' else "meters"
    source_type = "tidal stream" if stype == 'stream' else "tide"
    current_suffix = " Current" if stype == 'stream' else ""

    lines = []
    lines.append(f"# Harmonic constants derived from BOM {source_type} predictions (reverse-engineered)")
    lines.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated data")
    lines.append(f"# {result['n_events']} events -> {result['n_obs']} interpolated points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} {unit}")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {name}, {state_name}, Australia{current_suffix}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Australia")
    lines.append(f"# state: {state_name}")
    lines.append(f"# source: BOM {source_type} predictions, UTide analysis")
    lines.append(f"# station_id_context: BOM-{result['state']}-{code}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    if stype == 'stream':
        lines.append(f"# datum: n/a")
        lines.append(f"# station_type: current")
    else:
        lines.append(f"# datum: LAT")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: {unit}")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{name}, {state_name}, Australia{current_suffix}")
    lines.append(f"+00:00 :UTC")
    lines.append(f"{result['mean']:.4f} {unit}")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("UTide Harmonic Analysis - BOM Tidal Streams + Serpentine Creek")
    print("=" * 70)
    print(f"Stationen: {len(STATIONS)}")

    results = []
    errors = []

    for i, s in enumerate(STATIONS):
        print(f"\n[{i+1}/{len(STATIONS)}] {s['state']}_{s['code']} | {s['name']} "
              f"({s['lat']:.4f}, {s['lon']:.4f}) [{s['type']}]")

        available_years = []
        for year in [2025, 2026, 2027]:
            pdf_name = f"{s['pdf_prefix']}_{year}_{s['state']}_{s['code']}.pdf"
            if (PDF_DIR / pdf_name).exists():
                available_years.append(year)

        if len(available_years) < 2:
            print(f"  Nur {len(available_years)} Jahre, ueberspringe")
            errors.append((s['name'], "zu wenig Jahre"))
            continue

        result = analyze_station(s, years=available_years)
        if result is not None:
            results.append(result)
        else:
            errors.append((s['name'], "Analyse fehlgeschlagen"))

    # Append to existing harmonics file
    if results:
        print(f"\n{'='*70}")
        print(f"Haenge {len(results)} Stationen an {OUTPUT_PATH.name} an...")
        with open(OUTPUT_PATH, 'a', encoding='iso-8859-1') as f:
            for result in results:
                block = format_station_block(result)
                f.write(block)
                f.write('\n')
        print(f"  Fertig.")

    # Summary
    if results:
        print(f"\n{'='*70}")
        print("ZUSAMMENFASSUNG")
        print(f"{'='*70}")
        unit_map = {'stream': 'kn', 'tide': 'm'}
        for r in results:
            u = unit_map.get(r.get('type', 'tide'), 'm')
            print(f"  {r['name']:<30s} {r['state']}_{r['code']:>5s} "
                  f"R2={r['r_squared']:.4f} RMS={r['rms_error']:.4f}{u} "
                  f"M2={r['m2_amp']:.4f}{u} events={r['n_events']}")
        print(f"\nGesamt: {len(results)} Stationen")

    if errors:
        print(f"\n{len(errors)} Fehler:")
        for name, reason in errors:
            print(f"  {name}: {reason}")


if __name__ == '__main__':
    main()
