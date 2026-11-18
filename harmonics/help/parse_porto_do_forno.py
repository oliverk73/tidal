#!/usr/bin/env python3
"""
Parse Porto do Forno (Marinha CHM) tide table PDFs and create UTide harmonics.

Strategy:
1. Extract all HW/LW times+heights from PDFs (2024-2026, 3 years)
2. Interpolate to hourly time series using half-cosine segments
3. Run UTide harmonic analysis
4. Output in XTide harmonics format
"""

import re
import numpy as np
from datetime import datetime, timedelta
from scipy.interpolate import CubicHermiteSpline
import utide

# Month name mapping (Portuguese)
MONTHS_PT = {
    'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4,
    'Maio': 5, 'Junho': 6, 'Julho': 7, 'Agosto': 8,
    'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
}

def parse_pdf_text(filename):
    """Parse the raw text extracted from the Marinha PDF."""
    with open(filename, 'r') as f:
        text = f.read()

    # Split into pages/sections by the header pattern
    # Each month section starts with the month name
    entries = []  # list of (datetime, height_m)

    current_month = None
    # Extract year from header line "... - YYYY"
    year_match = re.search(r'-\s*(\d{4})', text)
    current_year = int(year_match.group(1)) if year_match else 2026

    lines = text.split('\n')
    i = 0

    # Track current day being parsed
    current_day = None

    while i < len(lines):
        line = lines[i].strip()

        # Check for month header
        for month_name, month_num in MONTHS_PT.items():
            if line == month_name:
                current_month = month_num
                break

        # Check for day number (1-31, standalone on a line or followed by day name)
        if current_month and re.match(r'^(\d{1,2})$', line):
            day_num = int(line)
            if 1 <= day_num <= 31:
                # Next line should be day-of-week abbreviation
                if i + 1 < len(lines) and re.match(r'^(SEG|TER|QUA|QUI|SEX|S[AÁ]B|DOM)$', lines[i+1].strip()):
                    current_day = day_num
                    i += 2  # skip day number and day name
                    continue

        # Check for time+height data: HHMM    height
        if current_month and current_day:
            m = re.match(r'^(\d{4})\s+(-?\d+\.\d+)$', line)
            if m:
                time_str = m.group(1)
                height = float(m.group(2))
                hour = int(time_str[:2])
                minute = int(time_str[2:])

                try:
                    dt = datetime(current_year, current_month, current_day, hour, minute)
                    entries.append((dt, height))
                except ValueError:
                    # Handle edge cases like hour=24
                    pass

        i += 1

    return entries


def check_monotonic_and_fix(entries):
    """Sort by datetime and remove duplicates."""
    # The PDF has two-column layout (days 1-16 left, 17-31 right)
    # so entries come interleaved. Just sort them.
    entries.sort(key=lambda e: e[0])
    fixed = []
    for dt, h in entries:
        if fixed and dt == fixed[-1][0]:
            continue  # skip duplicate
        fixed.append((dt, h))
    return fixed


def interpolate_to_hourly(entries):
    """Interpolate HW/LW points to hourly using half-cosine segments.

    Between each consecutive pair of extrema (HW->NW or NW->HW),
    the tide follows approximately a half cosine:
    h(t) = (h1+h2)/2 + (h1-h2)/2 * cos(pi * (t-t1) / (t2-t1))
    """
    # Use Jan 1 of earliest year as base for clean hourly grid
    first_year = entries[0][0].year
    base = datetime(first_year, 1, 1, 0, 0)
    print(f"  Base time: {base}")
    times = np.array([(e[0] - base).total_seconds() / 3600.0 for e in entries])
    heights = np.array([e[1] for e in entries])

    # Generate hourly points on clean grid
    t_start = int(np.ceil(times[0]))
    t_end = int(np.floor(times[-1]))
    t_hourly = np.arange(t_start, t_end + 1, 1.0)
    h_hourly = np.zeros_like(t_hourly)

    # For each hourly point, find which segment it belongs to
    seg_idx = 0
    for i, t in enumerate(t_hourly):
        # Advance segment if needed
        while seg_idx < len(times) - 2 and t > times[seg_idx + 1]:
            seg_idx += 1

        t1 = times[seg_idx]
        t2 = times[seg_idx + 1]
        h1 = heights[seg_idx]
        h2 = heights[seg_idx + 1]

        # Half-cosine interpolation
        phase = np.pi * (t - t1) / (t2 - t1)
        h_hourly[i] = (h1 + h2) / 2.0 + (h1 - h2) / 2.0 * np.cos(phase)

    dt_hourly = [base + timedelta(hours=int(t)) for t in t_hourly]
    return dt_hourly, h_hourly


def run_utide_analysis(times, heights, lat):
    """Run UTide harmonic analysis."""
    # Convert to matplotlib datenum
    from matplotlib.dates import date2num
    t_num = date2num(times)

    from matplotlib.dates import date2num as d2n
    # Use middle of time series as epoch for best phase accuracy
    mid_time = times[len(times) // 2]
    epoch_num = d2n(datetime(mid_time.year, 1, 1))

    coef = utide.solve(
        t_num, heights, lat=lat,
        method='ols',
        conf_int='MC',
        verbose=True,
        epoch=epoch_num
    )
    # Store epoch for reconstruct
    coef['_epoch_num'] = epoch_num
    return coef


def format_xtide_harmonics(coef, station_name, lat, lon, utc_offset_hours=0):
    """Format UTide results as XTide harmonics file entry.

    CRITICAL: XTide reads constituents by POSITION, not by name.
    All 175 constituents must be output in the exact order defined in the header.
    Missing constituents get 'x 0 0'.

    If UTide was given local-time data (not UTC), phases must be converted
    to Greenwich: phase_greenwich = phase_local + speed * utc_offset_hours
    """
    # Import the 175-constituent list from generate_brazil_harmonics
    import sys
    sys.path.insert(0, '/home/oliver/py')
    from generate_brazil_harmonics import CONSTITUENTS_175, find_xtide_match

    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_names = [n.strip() for n in const_table.name]

    # Build lookup: XTide constituent name -> (amplitude, greenwich_phase)
    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amp = coef['A'][i]
        phase_local = coef['g'][i]

        # Get constituent speed from UTide's own table
        if uname in utide_names:
            idx = utide_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0  # deg/hour
        else:
            continue

        # Convert local phase to Greenwich phase
        phase_greenwich = (phase_local + utide_speed * utc_offset_hours) % 360

        # Find matching XTide constituent name
        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue

        utide_results[xt_name] = {
            'amplitude': amp,
            'phase': phase_greenwich,
        }

    lines = []
    lines.append(f"# {station_name}")
    lines.append(f"# Derived from Marinha do Brasil (CHM/DHN) official tide tables 2025-2026")
    lines.append(f"# Porto do Forno station 50156, IEAPM")
    lines.append(f"# Harmonic analysis via UTide from interpolated HW/LW predictions (2 years)")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Brazil")
    lines.append(f"# state: Rio de Janeiro")
    lines.append(f"# source: Derived from Marinha do Brasil (CHM/DHN) tide tables with UTide")
    lines.append(f"# station_id_context: Marinha-50156")
    lines.append(f"# date_imported: 20260405")
    lines.append(f"# datum: Chart Datum (Marinha)")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")
    lines.append(station_name)
    lines.append(f"+00:00 :UTC")

    # Z0 (mean level)
    z0 = coef['mean']
    lines.append(f"{z0:.4f} meters")

    # Output ALL 175 constituents in order (positional!)
    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            if r['amplitude'] >= 0.00005:
                lines.append(f"{name:15s} {r['amplitude']:.4f}  {r['phase']:.2f}")
            else:
                lines.append(f"x 0 0")
        else:
            lines.append(f"x 0 0")

    return '\n'.join(lines)


if __name__ == '__main__':
    # Parse available years
    import sys
    sys.path.insert(0, '/home/oliver/harmonics/help')
    from parse_2024_pdf import parse_2024_pdf

    all_entries = []
    USE_2024 = False  # 2024 has only 1 decimal precision, hurts analysis

    if USE_2024:
        print("=== Parsing 2024 ===")
        e2024 = parse_2024_pdf('/home/oliver/weather/tide_tables/brazil/40_-_porto_do_forno_2024_ok.pdf', year=2024)
        print(f"  2024: {len(e2024)} entries")
        all_entries.extend(e2024)

    # 2025
    print("=== Parsing 2025 ===")
    e2025 = parse_pdf_text('/home/oliver/harmonics/help/porto_do_forno_raw_2025.txt')
    print(f"  2025: {len(e2025)} entries")
    all_entries.extend(e2025)

    # 2026
    print("=== Parsing 2026 ===")
    e2026 = parse_pdf_text('/home/oliver/harmonics/help/porto_do_forno_raw.txt')
    print(f"  2026: {len(e2026)} entries")
    all_entries.extend(e2026)

    entries = all_entries
    print(f"\nTotal: {len(entries)} HW/LW entries")

    if entries:
        print(f"First: {entries[0]}")
        print(f"Last:  {entries[-1]}")

    # Fix monotonicity (sorts and deduplicates)
    entries = check_monotonic_and_fix(entries)
    print(f"After fixing: {len(entries)} entries")

    # Check for gaps
    for i in range(1, len(entries)):
        dt_diff = (entries[i][0] - entries[i-1][0]).total_seconds() / 3600
        if dt_diff > 12:
            print(f"  Gap: {entries[i-1][0]} -> {entries[i][0]} ({dt_diff:.1f}h)")

    print("\n=== Interpolating to hourly ===")
    dt_hourly, h_hourly = interpolate_to_hourly(entries)
    print(f"Generated {len(dt_hourly)} hourly values")
    print(f"Time range: {dt_hourly[0]} to {dt_hourly[-1]}")

    print("\n=== Running UTide analysis ===")
    lat = -22.9725
    lon = -42.0136

    coef = run_utide_analysis(dt_hourly, h_hourly, lat)

    print(f"\nMean level (Z0): {coef['mean']:.4f} m")
    print(f"Number of constituents: {len(coef['name'])}")

    # Show top constituents
    idx = np.argsort(coef['A'])[::-1]
    print("\nTop 20 constituents:")
    for i in idx[:20]:
        print(f"  {coef['name'][i].strip():8s}  A={coef['A'][i]:.4f}m  g={coef['g'][i]:8.2f}°")

    # Format output
    station_name = "Porto do Forno, Rio de Janeiro, Brazil"
    # Marinha data is in BRT (UTC-3), convert phases to Greenwich: +3h offset
    output = format_xtide_harmonics(coef, station_name, lat, lon, utc_offset_hours=3)

    outfile = '/home/oliver/harmonics/help/porto_do_forno_utide.txt'
    with open(outfile, 'w') as f:
        f.write(output + '\n')
    print(f"\nHarmonics written to {outfile}")

    # Compare UTide prediction at original HW/LW times against Marinha data
    from matplotlib.dates import date2num
    epoch_num = coef['_epoch_num']
    print("\n=== Comparing UTide prediction vs Marinha HW/LW ===")

    # Reconstruct at 6-minute resolution for April
    base = datetime(2026, 1, 1, 0, 0)
    april_start = datetime(2026, 4, 1, 0, 0)
    april_end = datetime(2026, 4, 30, 23, 54)
    t_fine = []
    dt = april_start
    while dt <= april_end:
        t_fine.append(dt)
        dt += timedelta(minutes=6)

    t_fine_num = date2num(t_fine)
    recon = utide.reconstruct(t_fine_num, coef, epoch=epoch_num)
    h_fine = recon['h']

    # Find HW/LW in reconstruction
    predicted_extrema = []
    for i in range(1, len(h_fine) - 1):
        if h_fine[i] > h_fine[i-1] and h_fine[i] > h_fine[i+1]:
            predicted_extrema.append((t_fine[i], h_fine[i], 'HW'))
        elif h_fine[i] < h_fine[i-1] and h_fine[i] < h_fine[i+1]:
            predicted_extrema.append((t_fine[i], h_fine[i], 'NW'))

    # Get April entries from Marinha
    marinha_april = [(dt, h) for dt, h in entries if dt.month == 4 and dt.year == 2026]

    # Match and compare
    print(f"Marinha April entries: {len(marinha_april)}")
    print(f"UTide predicted extrema in April: {len(predicted_extrema)}")

    print(f"\n{'Datum':>12s}  {'Marinha':>14s}  {'UTide':>14s}  {'ΔZeit':>7s}  {'ΔHöhe':>7s}")
    print("-" * 62)

    time_diffs = []
    height_diffs = []
    for m_dt, m_h in marinha_april[:24]:  # first 6 days
        # Find closest predicted extremum
        best_diff = 999
        best_p = None
        for p_dt, p_h, p_type in predicted_extrema:
            diff_h = abs((p_dt - m_dt).total_seconds()) / 3600
            if diff_h < best_diff:
                best_diff = diff_h
                best_p = (p_dt, p_h, p_type)

        if best_p and best_diff < 3:
            dt_diff_min = (best_p[0] - m_dt).total_seconds() / 60
            dh = best_p[1] - m_h
            time_diffs.append(dt_diff_min)
            height_diffs.append(dh)
            print(f"{m_dt.strftime('%d.%m %H:%M')}  {m_h:6.2f}m       "
                  f"{best_p[1]:6.2f}m       {dt_diff_min:+5.0f}min  {dh:+5.2f}m")

    if time_diffs:
        print(f"\nApril (erste 6 Tage):")
        print(f"  Mittlere Zeitabweichung: {np.mean(time_diffs):+.1f} min")
        print(f"  RMS Zeitabweichung:      {np.sqrt(np.mean(np.array(time_diffs)**2)):.1f} min")
        print(f"  Mittlere Höhenabweichung: {np.mean(height_diffs):+.3f} m")
        print(f"  RMS Höhenabweichung:      {np.sqrt(np.mean(np.array(height_diffs)**2)):.3f} m")

    # Also compare the OLD XTide Cabo Frio prediction against Marinha
    print("\n=== Zum Vergleich: alter XTide 'Cabo Frio' vs Marinha (April 5) ===")
    print("XTide:  03:30/1.06  10:06/0.19  16:10/1.10  22:33/0.43")
    print("Marinha: 04:21/0.95  10:51/0.19  17:01/0.96  23:12/0.39")
