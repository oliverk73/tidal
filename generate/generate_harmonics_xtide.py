#!/usr/bin/env python3
"""
Generate Harmonic Constants from long-term water level measurements.
Outputs in XTide-compatible text format.

For 26 years of data, this provides high-resolution harmonic constants
suitable for accurate tide predictions.
"""
import json
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
import sys

# Standard tidal constituent frequencies (degrees per solar hour)
# These must match the order in the xTide harmonics file header
CONSTITUENTS = {
    # Major constituents (same order as in harmonics-dwf files)
    'J1':    15.5854433,
    'K1':    15.0410686,
    'K2':    30.0821373,
    'L2':    29.5284789,
    'M1':    14.4966939,
    'M2':    28.9841042,
    'M3':    43.4761563,
    'M4':    57.9682084,
    'M6':    86.9523126,
    'M8':   115.9364169,
    'N2':    28.4397295,
    '2N2':   27.8953548,
    'O1':    13.9430356,
    'OO1':   16.1391017,
    'P1':    14.9589314,
    'Q1':    13.3986609,
    '2Q1':   12.8542862,
    'R2':    30.0410667,
    'S1':    15.0000000,
    'S2':    30.0000000,
    'S4':    60.0000000,
    'S6':    90.0000000,
    'T2':    29.9589333,
    'LDA2':  29.4556253,
    'MU2':   27.9682084,
    'NU2':   28.5125831,
    'RHO1':  13.4715145,
    'MK3':   44.0251729,
    '2MK3':  42.9271398,
    'MN4':   57.4238337,
    'MS4':   58.9841042,
    '2SM2':  31.0158958,
    'MF':     1.0980331,
    'MSF':    1.0158958,
    'MM':     0.5443747,
    'SA':     0.0410686,
    'SSA':    0.0821373,
    # Additional shallow water constituents
    '2MS6':  87.9682084,
    '2MN6':  86.4079379,
    'MSK6':  89.0662415,
    'M10':  144.9205211,
    'M12':  173.9046253,
}

# Constituents to analyze (subset for practical analysis)
ANALYSIS_CONSTITUENTS = [
    # Long period (need multi-year data)
    'SA', 'SSA', 'MM', 'MSF', 'MF',
    # Diurnal
    '2Q1', 'Q1', 'RHO1', 'O1', 'M1', 'P1', 'S1', 'K1', 'J1', 'OO1',
    # Semidiurnal
    '2N2', 'MU2', 'N2', 'NU2', 'M2', 'LDA2', 'L2', 'T2', 'S2', 'R2', 'K2',
    # Terdiurnal
    'M3', 'MK3', '2MK3',
    # Quarter-diurnal
    'MN4', 'M4', 'MS4', 'S4',
    # Sixth-diurnal
    '2MN6', 'M6', '2MS6', 'MSK6', 'S6',
    # Higher
    'M8', '2SM2',
]


def parse_pegelonline_json(filepath, downsample_minutes=15, progress_interval=1000000):
    """
    Parse Pegelonline JSON export file.

    Args:
        filepath: Path to JSON file
        downsample_minutes: Resample to this interval (reduces memory/computation)
        progress_interval: Print progress every N records

    Returns:
        Dictionary with times (hours since epoch) and levels (meters)
    """
    print(f"Loading JSON file: {filepath}")
    print("This may take a moment for large files...")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"Loaded {len(data):,} records")

    # Reference epoch: J2000.0 (2000-01-01 12:00:00 UTC)
    # This is a common astronomical epoch
    epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    times_hours = []
    levels_m = []

    # Parse timestamps and convert to hours since epoch
    for i, record in enumerate(data):
        if i % progress_interval == 0 and i > 0:
            print(f"  Processed {i:,} records...")

        ts_str = record['timestamp']
        value = record.get('value')

        if value is None:
            continue

        # Parse ISO 8601 timestamp with timezone
        # Format: 2000-01-01T01:00:00+01:00
        try:
            dt = datetime.fromisoformat(ts_str)
            # Convert to UTC
            dt_utc = dt.astimezone(timezone.utc)

            # Hours since epoch
            delta = dt_utc - epoch
            hours = delta.total_seconds() / 3600.0

            times_hours.append(hours)
            levels_m.append(value / 100.0)  # cm to meters
        except Exception as e:
            continue

    times = np.array(times_hours)
    levels = np.array(levels_m)

    print(f"Parsed {len(times):,} valid measurements")

    # Downsample to reduce computation
    if downsample_minutes > 1:
        step = downsample_minutes
        times = times[::step]
        levels = levels[::step]
        print(f"Downsampled to {len(times):,} points ({downsample_minutes}-minute intervals)")

    # Get time range info
    start_dt = epoch + np.timedelta64(int(times[0] * 3600), 's')
    end_dt = epoch + np.timedelta64(int(times[-1] * 3600), 's')

    return {
        'times': times,
        'levels': levels,
        'epoch': epoch,
        'start_hours': times[0],
        'end_hours': times[-1],
        'n_points': len(times),
    }


def harmonic_analysis(times, levels, constituents=None):
    """
    Perform harmonic analysis using least squares.

    The tidal height is modeled as:
        h(t) = Z0 + Σ [A_n * cos(ω_n * t - φ_n)]
             = Z0 + Σ [a_n * cos(ω_n * t) + b_n * sin(ω_n * t)]

    where:
        A_n = √(a_n² + b_n²)  is the amplitude
        φ_n = atan2(b_n, a_n) is the phase (epoch)

    Args:
        times: Time array in hours since J2000.0 epoch
        levels: Water level array in meters
        constituents: List of constituent names to analyze

    Returns:
        Dictionary with analysis results
    """
    if constituents is None:
        constituents = ANALYSIS_CONSTITUENTS

    # Filter to constituents we have speeds for
    constituents = [c for c in constituents if c in CONSTITUENTS]

    n_obs = len(times)
    n_constit = len(constituents)

    print(f"Building design matrix: {n_obs:,} observations × {2*n_constit + 1} parameters")

    # Build design matrix
    # Column 0: constant (mean level Z0)
    # Columns 1,2: cos/sin for first constituent
    # Columns 3,4: cos/sin for second constituent, etc.
    A = np.ones((n_obs, 1 + 2 * n_constit), dtype=np.float64)

    for i, name in enumerate(constituents):
        omega = np.radians(CONSTITUENTS[name])  # Convert degrees/hour to radians/hour
        A[:, 1 + 2*i] = np.cos(omega * times)
        A[:, 2 + 2*i] = np.sin(omega * times)

    print("Solving least squares system...")

    # Solve least squares: minimize ||A*x - levels||²
    x, residuals, rank, s = np.linalg.lstsq(A, levels, rcond=None)

    print(f"Solution rank: {rank}")

    # Extract results
    results = {
        'Z0': x[0],  # Mean level (datum offset)
        'constituents': [],
    }

    for i, name in enumerate(constituents):
        a_cos = x[1 + 2*i]
        a_sin = x[2 + 2*i]

        # Amplitude
        amplitude = np.sqrt(a_cos**2 + a_sin**2)

        # Phase (epoch) in degrees
        # atan2(sin, cos) gives the phase φ where h = A*cos(ωt - φ)
        phase = np.degrees(np.arctan2(a_sin, a_cos))
        if phase < 0:
            phase += 360.0

        results['constituents'].append({
            'name': name,
            'amplitude': amplitude,
            'phase': phase,  # Local epoch in degrees
            'speed': CONSTITUENTS[name],
        })

    # Calculate fit statistics
    h_predicted = A @ x
    residual_values = levels - h_predicted
    ss_res = np.sum(residual_values**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)

    results['r_squared'] = 1 - ss_res / ss_tot
    results['rms_error'] = np.sqrt(np.mean(residual_values**2))
    results['max_error'] = np.max(np.abs(residual_values))

    return results


def format_xtide_station(station_name, lat, lon, timezone_str, datum,
                         results, source_info=None):
    """
    Format harmonic constants in xTide text format.

    This produces the station data block that can be appended to an
    existing harmonics file (after the *END* marker of the congen output).

    Args:
        station_name: Full station name (e.g., "Cuxhaven, Germany")
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        timezone_str: Timezone file (e.g., "Europe/Berlin")
        datum: Datum offset in meters (MLLW or similar)
        results: Results from harmonic_analysis()
        source_info: Optional dict with metadata

    Returns:
        String in xTide format
    """
    lines = []

    # HOT COMMENTS (metadata)
    lines.append("# Harmonic constants derived from PEGELONLINE data")
    if source_info:
        if 'start_date' in source_info:
            lines.append(f"# Analysis period: {source_info['start_date']} to {source_info['end_date']}")
        if 'n_observations' in source_info:
            lines.append(f"# Number of observations: {source_info['n_observations']:,}")
        if 'r_squared' in source_info:
            lines.append(f"# R² = {source_info['r_squared']:.6f}")
        if 'rms_error' in source_info:
            lines.append(f"# RMS error = {source_info['rms_error']:.4f} m")
    lines.append("# ")
    lines.append("# BEGIN HOT COMMENTS")
    lines.append("# country: Germany")
    lines.append("# source: Derived from PEGELONLINE WSV data")
    lines.append("# restriction: Public domain")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append("# datum: Mean Sea Level")
    lines.append(f"# confidence: 10")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.4f}")
    lines.append(f"# !latitude: {lat:.4f}")

    # Station name
    lines.append(station_name)

    # Time meridian and timezone
    # For UTC-referenced data, use +00:00
    # The timezone file handles DST
    lines.append(f"+00:00 :{timezone_str}")

    # Datum and units
    lines.append(f"{datum:.4f} meters")

    # Constituent data: name amplitude epoch
    # Sort by constituent order in the standard list
    constituent_order = list(CONSTITUENTS.keys())

    sorted_constits = sorted(
        results['constituents'],
        key=lambda c: constituent_order.index(c['name']) if c['name'] in constituent_order else 999
    )

    for c in sorted_constits:
        if c['amplitude'] >= 0.0001:  # Skip negligible constituents (< 0.1mm)
            lines.append(f"{c['name']:16s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    # Input file
    input_file = Path("/home/oliver/water_levels/pegelonline-cuxhavensteubenhft-W-20000101-20260123/pegelonline-cuxhavensteubenhft-W-20000101-20260123.json")

    # Output file
    output_dir = Path("/home/oliver/water_levels")

    # Station information
    station_name = "Cuxhaven Steubenhöft, Germany"
    lat = 53.8697  # Latitude
    lon = 8.7172   # Longitude
    timezone_str = "Europe/Berlin"

    # Parse data
    print("=" * 70)
    print("HARMONIC ANALYSIS OF LONG-TERM TIDAL DATA")
    print("=" * 70)
    print()

    data = parse_pegelonline_json(input_file, downsample_minutes=15)

    duration_years = (data['end_hours'] - data['start_hours']) / (24 * 365.25)
    print(f"\nData span: {duration_years:.2f} years")
    print(f"Level range: {data['levels'].min():.2f} m to {data['levels'].max():.2f} m")
    print(f"Mean level: {np.mean(data['levels']):.4f} m")
    print()

    # Perform harmonic analysis
    print("-" * 70)
    print("HARMONIC ANALYSIS")
    print("-" * 70)

    results = harmonic_analysis(data['times'], data['levels'], ANALYSIS_CONSTITUENTS)

    print(f"\nMean level (Z0): {results['Z0']:.4f} m")
    print(f"R² = {results['r_squared']:.6f} ({results['r_squared']*100:.2f}% variance explained)")
    print(f"RMS error = {results['rms_error']:.4f} m ({results['rms_error']*100:.1f} cm)")
    print(f"Max error = {results['max_error']:.4f} m ({results['max_error']*100:.1f} cm)")
    print()

    # Print top constituents
    print("-" * 70)
    print("TIDAL CONSTITUENTS (sorted by amplitude)")
    print("-" * 70)
    print(f"{'Name':10s} {'Amplitude':>12s} {'Phase':>12s} {'Period':>14s}")
    print(f"{'':10s} {'(m)':>12s} {'(deg)':>12s} {'(hours)':>14s}")
    print("-" * 70)

    sorted_by_amp = sorted(results['constituents'],
                           key=lambda x: x['amplitude'],
                           reverse=True)

    for c in sorted_by_amp:
        if c['amplitude'] >= 0.001:  # >= 1mm
            period = 360.0 / c['speed'] if c['speed'] > 0 else float('inf')
            print(f"{c['name']:10s} {c['amplitude']:12.4f} {c['phase']:12.2f} {period:14.2f}")

    print()

    # Calculate datum
    # The datum should be the level below which tide predictions should not go
    # For North Sea, we use approximately Mean Sea Level
    datum = results['Z0']

    # Source info for metadata
    source_info = {
        'start_date': '2000-01-01',
        'end_date': '2026-01-23',
        'n_observations': data['n_points'],
        'r_squared': results['r_squared'],
        'rms_error': results['rms_error'],
    }

    # Format xTide output
    xtide_text = format_xtide_station(
        station_name, lat, lon, timezone_str, datum,
        results, source_info
    )

    # Save xTide format
    output_file = output_dir / "cuxhaven_harmonics_xtide.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(xtide_text)
    print(f"Saved xTide format to: {output_file}")

    # Also save a detailed report
    report_file = output_dir / "cuxhaven_harmonics_report.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("HARMONIC ANALYSIS REPORT\n")
        f.write(f"Station: {station_name}\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Data period: 2000-01-01 to 2026-01-23 ({duration_years:.2f} years)\n")
        f.write(f"Observations: {data['n_points']:,}\n")
        f.write(f"Coordinates: {lat:.4f}°N, {lon:.4f}°E\n\n")

        f.write(f"Mean level (Z0): {results['Z0']:.4f} m\n")
        f.write(f"R² = {results['r_squared']:.6f}\n")
        f.write(f"RMS error = {results['rms_error']:.4f} m\n")
        f.write(f"Max error = {results['max_error']:.4f} m\n\n")

        f.write("-" * 70 + "\n")
        f.write(f"{'Constituent':12s} {'Speed':>14s} {'Amplitude':>12s} {'Phase':>12s}\n")
        f.write(f"{'':12s} {'(deg/hour)':>14s} {'(m)':>12s} {'(deg)':>12s}\n")
        f.write("-" * 70 + "\n")

        for c in sorted_by_amp:
            f.write(f"{c['name']:12s} {c['speed']:14.7f} {c['amplitude']:12.4f} {c['phase']:12.2f}\n")

    print(f"Saved detailed report to: {report_file}")
    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
