#!/usr/bin/env python3
"""
Generate Harmonic Constants from PEGELONLINE water level data.
Outputs in XTide-compatible text format with ISO-8859-1 encoding.

This script processes all ZIP files in water_levels/Germany and generates
harmonic constants using least-squares harmonic analysis.
"""

import json
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
import zipfile
import urllib.request
import sys
import re

# Constituent order from XTide harmonics file header
# This MUST match the order in the header file
CONSTITUENT_ORDER = [
    'J1', 'K1', 'K2', 'L2', 'M1', 'M2', 'M3', 'M4', 'M6', 'M8',
    'N2', '2N2', 'O1', 'OO1', 'P1', 'Q1', '2Q1', 'R2', 'S1', 'S2',
    'S4', 'S6', 'T2', 'LDA2', 'MU2', 'NU2', 'RHO1', 'MK3', '2MK3',
    'MN4', 'MS4', '2SM2', 'MF', 'MSF', 'MM', 'SA', 'SSA',
    # Additional shallow water constituents
    '2MS6', '2MN6', 'MSK6',
]

# Constituent speeds in degrees per solar hour
CONSTITUENT_SPEEDS = {
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
    '2MS6':  87.9682084,
    '2MN6':  86.4079379,
    'MSK6':  89.0662415,
}

# Station name corrections for proper display
STATION_NAME_CORRECTIONS = {
    'STEUBENHOFT': 'Steubenhoeft',
    'CUXHAVENSTEUBENHFT': 'Cuxhaven (Steubenhoeft)',
    'BHVALTERLEUCHTTURM': 'Bremerhaven (Alter Leuchtturm)',
    'BORKUMFISCHERBALJE': 'Borkum (Fischerbalje)',
    'BORKUMSDSTRAND': 'Borkum (Suedstrand)',
    'BREMERVRDEUW': 'Bremervoerde (UW)',
    'BRUNSBTTELMPM': 'Brunsbuettel (MPM)',
    'BARDOWICKOP': 'Bardowick (OP)',
    'BARDOWICKUP': 'Bardowick (UP)',
}


def fetch_station_coordinates():
    """Fetch station coordinates from PEGELONLINE API."""
    url = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json"
    try:
        print("Fetching station coordinates from PEGELONLINE API...")
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))

        # Create lookup by shortname (normalized)
        coords = {}
        for station in data:
            shortname = station.get('shortname', '').upper().replace(' ', '').replace('-', '')
            if 'latitude' in station and 'longitude' in station:
                coords[shortname] = {
                    'lat': station['latitude'],
                    'lon': station['longitude'],
                    'water': station.get('water', {}).get('shortname', ''),
                    'longname': station.get('longname', station.get('shortname', '')),
                }
        print(f"  Loaded coordinates for {len(coords)} stations")
        return coords
    except Exception as e:
        print(f"  Warning: Could not fetch coordinates: {e}")
        return {}


def extract_station_name_from_filename(filename):
    """Extract station name from filename like 'pegelonline-borkumfischerbalje-W-...'"""
    match = re.match(r'pegelonline-([a-z0-9]+)-W-', filename, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def format_station_name(raw_name, longname=None):
    """Format station name for display, handling German special characters."""
    if raw_name.upper() in STATION_NAME_CORRECTIONS:
        return STATION_NAME_CORRECTIONS[raw_name.upper()]

    if longname and len(longname) > 2:
        # Use longname but capitalize properly
        return longname.title()

    # Basic formatting
    name = raw_name.replace('-', ' ').replace('_', ' ')
    # Handle common German place name parts
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)  # CamelCase to spaces
    return name.title()


def parse_json_waterlevels(json_path, downsample_minutes=15):
    """
    Parse water level JSON file.

    Args:
        json_path: Path to JSON file
        downsample_minutes: Resample interval (reduces memory)

    Returns:
        Dictionary with times (hours since J2000.0) and levels (meters)
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data:
        return None

    # Reference epoch: J2000.0 (2000-01-01 12:00:00 UTC)
    epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    times_hours = []
    levels_m = []

    for record in data:
        ts_str = record.get('timestamp')
        value = record.get('value')

        if value is None or ts_str is None:
            continue

        try:
            dt = datetime.fromisoformat(ts_str)
            dt_utc = dt.astimezone(timezone.utc)
            delta = dt_utc - epoch
            hours = delta.total_seconds() / 3600.0

            times_hours.append(hours)
            levels_m.append(value / 100.0)  # cm to meters
        except:
            continue

    if len(times_hours) < 1000:  # Need enough data for analysis
        return None

    times = np.array(times_hours)
    levels = np.array(levels_m)

    # Downsample
    if downsample_minutes > 1:
        step = downsample_minutes
        times = times[::step]
        levels = levels[::step]

    return {
        'times': times,
        'levels': levels,
        'n_points': len(times),
    }


def harmonic_analysis(times, levels, constituents):
    """
    Perform harmonic analysis using least squares.

    Args:
        times: Time array in hours since J2000.0 epoch
        levels: Water level array in meters
        constituents: List of constituent names to analyze

    Returns:
        Dictionary with analysis results
    """
    constituents = [c for c in constituents if c in CONSTITUENT_SPEEDS]

    n_obs = len(times)
    n_constit = len(constituents)

    # Build design matrix
    A = np.ones((n_obs, 1 + 2 * n_constit), dtype=np.float64)

    for i, name in enumerate(constituents):
        omega = np.radians(CONSTITUENT_SPEEDS[name])
        A[:, 1 + 2*i] = np.cos(omega * times)
        A[:, 2 + 2*i] = np.sin(omega * times)

    # Solve least squares
    x, residuals, rank, s = np.linalg.lstsq(A, levels, rcond=None)

    results = {
        'Z0': x[0],
        'constituents': {},
    }

    for i, name in enumerate(constituents):
        a_cos = x[1 + 2*i]
        a_sin = x[2 + 2*i]

        amplitude = np.sqrt(a_cos**2 + a_sin**2)
        phase = np.degrees(np.arctan2(a_sin, a_cos))
        if phase < 0:
            phase += 360.0

        results['constituents'][name] = {
            'amplitude': amplitude,
            'phase': phase,
        }

    # Calculate fit statistics
    h_predicted = A @ x
    residual_values = levels - h_predicted
    ss_res = np.sum(residual_values**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)

    results['r_squared'] = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    results['rms_error'] = np.sqrt(np.mean(residual_values**2))

    return results


def format_station_block(station_name, lat, lon, datum, results, source_info=None):
    """
    Format a single station block in XTide format.

    Args:
        station_name: Display name of station
        lat, lon: Coordinates
        datum: Datum offset in meters
        results: Results from harmonic_analysis()
        source_info: Optional metadata dict

    Returns:
        List of lines (strings)
    """
    lines = []

    # Hot comments (metadata)
    lines.append("# Harmonic constants derived from PEGELONLINE data")
    if source_info:
        if 'start_date' in source_info:
            lines.append(f"# Analysis period: {source_info['start_date']} to {source_info['end_date']}")
        if 'n_observations' in source_info:
            lines.append(f"# Number of observations: {source_info['n_observations']:,}")
        if 'r_squared' in source_info:
            lines.append(f"# R^2 = {source_info['r_squared']:.6f}")
        if 'rms_error' in source_info:
            lines.append(f"# RMS error = {source_info['rms_error']:.4f} m")
    lines.append("# ")
    lines.append("# BEGIN HOT COMMENTS")
    lines.append("# country: Germany")
    lines.append("# source: Derived from PEGELONLINE WSV data")
    lines.append("# restriction: Public domain")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append("# datum: Mean Sea Level")
    lines.append("# confidence: 10")
    lines.append("# !units: meters")
    lines.append(f"# !longitude: {lon:.4f}")
    lines.append(f"# !latitude: {lat:.4f}")

    # Station name
    lines.append(f"{station_name}, Germany")

    # Time meridian and timezone
    lines.append("+00:00 :Europe/Berlin")

    # Datum and units
    lines.append(f"{datum:.4f} meters")

    # Constituents in the required order
    for const_name in CONSTITUENT_ORDER:
        if const_name in results['constituents']:
            c = results['constituents'][const_name]
            if c['amplitude'] >= 0.0001:  # >= 0.1mm threshold
                lines.append(f"{const_name:16s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return lines


def convert_to_iso8859(text):
    """Convert text to ISO-8859-1, replacing problematic characters."""
    replacements = {
        '\u00f6': 'oe',  # o-umlaut -> oe
        '\u00e4': 'ae',  # a-umlaut -> ae
        '\u00fc': 'ue',  # u-umlaut -> ue
        '\u00d6': 'Oe',  # O-umlaut -> Oe
        '\u00c4': 'Ae',  # A-umlaut -> Ae
        '\u00dc': 'Ue',  # U-umlaut -> Ue
        '\u00df': 'ss',  # sharp s -> ss
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # Encode to ISO-8859-1, replacing any remaining problematic chars
    try:
        return text.encode('iso-8859-1').decode('iso-8859-1')
    except UnicodeEncodeError:
        return text.encode('iso-8859-1', errors='replace').decode('iso-8859-1')


def process_all_stations(input_dir, header_file, output_file):
    """
    Process all water level ZIP files and generate harmonics file.

    Args:
        input_dir: Directory with ZIP files
        header_file: Existing harmonics file to copy header from
        output_file: Output harmonics file path
    """
    input_path = Path(input_dir)
    header_path = Path(header_file)
    output_path = Path(output_file)

    # Get station coordinates
    station_coords = fetch_station_coordinates()

    # Read header from existing file (up to and including *END*)
    print(f"\nReading header from {header_path}...")
    header_lines = []
    with open(header_path, 'r', encoding='iso-8859-1') as f:
        for line in f:
            header_lines.append(line.rstrip('\n'))
            if '*END*' in line:
                break

    # Add standard comments after *END*
    header_lines.extend([
        "#",
        "# ------------- End congen output -------------",
        "#",
        "# Harmonic constants.",
        "#",
        "# First line:  name of location",
        "# Second line:  time meridian [whitespace] tzfile",
        "# Third line:  DATUM [whitespace] units",
        "# Remaining lines:  identifier [whitespace] amplitude [whitespace] epoch",
        "#",
        "# The DATUM is the mean lower low water or equivalent constant for",
        "# calibrating the tide height.",
        "#",
        "# The time meridian takes the format [-]HH:MM and is hours east of",
        "# Greenwich.  For most data sets calibrated to Local Standard Time,",
        "# this is your time zone displacement in the _winter_.  Do not include",
        "# Daylight Savings Time!  If a data set is calibrated to GMT / UTC,",
        "# the meridian should be set to 0:00.",
        "#",
        "# The tzfile is a reference to a file in the zoneinfo directory as",
        "# described in the man page for tzset.",
        "#",
        "# Epoch is \"modified\" or \"adapted\" epoch in degrees, also known as",
        "# Kappa Prime.",
        "#",
        "# The constituent identifiers are for readability only.  XTide assumes",
        "# that they are in the same order as defined above.",
        "#",
        "# These data sets are distributed in the hope that they will be useful,",
        "# but WITHOUT ANY WARRANTY; without even the implied warranty of",
        "# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.",
        "#",
    ])

    # Find all ZIP files
    zip_files = sorted(input_path.glob('pegelonline-*-W-*.zip'))
    print(f"\nFound {len(zip_files)} ZIP files to process")

    # Constituents to analyze
    analysis_constituents = list(CONSTITUENT_SPEEDS.keys())

    # Process each station
    station_blocks = []
    processed = 0
    failed = 0

    for i, zip_path in enumerate(zip_files):
        # Skip Zone.Identifier files
        if ':Zone.Identifier' in str(zip_path):
            continue

        station_id = extract_station_name_from_filename(zip_path.name)
        if not station_id:
            continue

        print(f"\n[{i+1}/{len(zip_files)}] Processing {station_id}...")

        try:
            # Extract JSON from ZIP
            with zipfile.ZipFile(zip_path, 'r') as zf:
                json_files = [n for n in zf.namelist() if n.endswith('.json')]
                if not json_files:
                    print(f"  No JSON file found in {zip_path.name}")
                    failed += 1
                    continue

                # Read metadata
                info_content = None
                try:
                    info_content = zf.read('zeitreiheninformation.txt').decode('utf-8')
                except:
                    pass

                # Parse metadata
                station_info = {}
                if info_content:
                    for line in info_content.split('\n'):
                        if '=' in line:
                            key, val = line.split('=', 1)
                            station_info[key.strip()] = val.strip()

                # Extract and parse JSON
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tf:
                    tf.write(zf.read(json_files[0]))
                    temp_json = tf.name

                print(f"  Parsing water levels...")
                data = parse_json_waterlevels(temp_json, downsample_minutes=15)

                Path(temp_json).unlink()

                if data is None:
                    print(f"  Insufficient data")
                    failed += 1
                    continue

                print(f"  Loaded {data['n_points']:,} data points")

                # Get coordinates
                lat, lon = 0.0, 0.0
                longname = station_info.get('station_name', station_id)

                if station_id in station_coords:
                    lat = station_coords[station_id]['lat']
                    lon = station_coords[station_id]['lon']
                    longname = station_coords[station_id].get('longname', longname)

                # Perform harmonic analysis
                print(f"  Performing harmonic analysis...")
                results = harmonic_analysis(data['times'], data['levels'], analysis_constituents)

                print(f"  R^2 = {results['r_squared']:.4f}, RMS = {results['rms_error']:.4f} m")

                # Skip stations with poor fit (likely non-tidal)
                if results['r_squared'] < 0.3:
                    print(f"  Skipping: poor tidal signal (R^2 < 0.3)")
                    failed += 1
                    continue

                # Format station name
                display_name = format_station_name(station_id, longname)

                # Source info
                source_info = {
                    'start_date': station_info.get('start', '').split('T')[0],
                    'end_date': station_info.get('end', '').split('T')[0],
                    'n_observations': data['n_points'],
                    'r_squared': results['r_squared'],
                    'rms_error': results['rms_error'],
                }

                # Generate station block
                block = format_station_block(
                    display_name, lat, lon, results['Z0'],
                    results, source_info
                )
                station_blocks.append(block)
                processed += 1

                print(f"  Successfully processed: {display_name}")

        except Exception as e:
            print(f"  Error: {e}")
            failed += 1
            continue

    # Write output file
    print(f"\n{'='*60}")
    print(f"Writing output to {output_path}...")

    with open(output_path, 'w', encoding='iso-8859-1', errors='replace') as f:
        # Write header
        for line in header_lines:
            f.write(convert_to_iso8859(line) + '\n')

        # Write station blocks
        for block in station_blocks:
            for line in block:
                f.write(convert_to_iso8859(line) + '\n')

    print(f"\nSummary:")
    print(f"  Processed: {processed} stations")
    print(f"  Failed: {failed} stations")
    print(f"  Output: {output_path}")


def main():
    input_dir = "/home/oliver/water_levels/Germany"
    header_file = "/home/oliver/harmonics_working/harmonics_germany_pegelonline_2026-01-23.txt"
    output_file = "/home/oliver/harmonics_working/harmonics_germany_pegelonline_2026-01-23.txt"

    print("="*60)
    print("GENERATE HARMONIC CONSTANTS FROM PEGELONLINE DATA")
    print("="*60)

    process_all_stations(input_dir, header_file, output_file)

    print("\nDone!")


if __name__ == "__main__":
    main()
