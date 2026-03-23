#!/usr/bin/env python3
"""
Generate Harmonic Constants from PEGELONLINE water level data.
Outputs in XTide-compatible text format with 175 constituents.

This script processes all ZIP files in water_levels/Germany and generates
harmonic constants using least-squares harmonic analysis.
"""

import json
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
import zipfile
import urllib.request
import re
import tempfile

# All 175 constituents in the exact order from the harmonics file header
CONSTITUENT_ORDER = [
    'J1', 'K1', 'K2', 'L2', 'M1', 'M2', 'M3', 'M4', 'M6', 'M8',
    'N2', '2N2', 'O1', 'OO1', 'P1', 'Q1', '2Q1', 'R2', 'S1', 'S2',
    'S4', 'S6', 'T2', 'LDA2', 'MU2', 'NU2', 'RHO1', 'MK3', '2MK3',
    'MN4', 'MS4', '2SM2', 'MF', 'MSF', 'MM', 'SA', 'SSA',
    'SA-IOS', 'MF-IOS', 'S1-IOS', 'OO1-IOS', 'R2-IOS',
    'A7', '2MK5', '2MK6', '2MN2', '2MN6', '2MS6', '2NM6', '2SK5', '2SM6',
    '3MK7', '3MN8', '3MS2', '3MS4', '3MS8', 'ALP1', 'BET1', 'CHI1',
    'H1', 'H2', 'KJ2', 'ETA2', 'KQ1', 'UPS1', 'M10', 'M12', 'MK4', 'MKS2',
    'MNS2', 'EPS2', 'MO3', 'MP1', 'TAU1', 'MPS2', 'MSK6', 'MSM', 'MSN2',
    'MSN6', 'NLK2', 'NO1', 'OP2', 'OQ2', 'PHI1', 'KP1', 'PI1', 'TK1',
    'PSI1', 'RP1', 'S3', 'SIG1', 'SK3', 'SK4', 'SN4', 'SNK6', 'SO1', 'SO3',
    'THE1', '2PO1', '2NS2', 'MLN2S2', '2ML2S2', 'SKM2', '2MS2K2', 'MKL2S2',
    'M2(KS)2', '2SN(MK)2', '2KM(SN)2', 'NO3', '2MLS4', 'ML4', 'N4', 'SL4',
    'MNO5', '2MO5', 'MSK5', '3KM5', '2MP5', '3MP5', 'MNK5', '2NMLS6', 'MSL6',
    '2ML6', '2MNLS6', '3MLS6', '2MNO7', '2NMK7', '2MSO7', 'MSKO7', '2MSN8',
    '2(MS)8', '2(MN)8', '2MSL8', '4MLS8', '3ML8', '3MK8', '2MSK8', '2M2NK9',
    '3MNK9', '4MK9', '3MSK9', '4MN10', '3MNS10', '4MS10', '3MSL10', '3M2S10',
    '4MSK11', '4MNS12', '5MS12', '4MSL12', '4M2S12', 'M1C', '3MKS2', 'OQ2-HORN',
    'MSK2', 'MSP2', '2MP3', '4MS4', '2MNS4', '2MSK4', '3MN4', '2MSN4', '3MK5',
    '3MO5', '3MNS6', '4MS6', '2MNU6', '3MSK6', 'MKNU6', '3MSN6', 'M7', '2MNK8',
    '2(MS)N10', 'MNUS2', '2MK2'
]

# Constituent speeds in degrees per solar hour
CONSTITUENT_SPEEDS = {
    'J1': 15.5854433, 'K1': 15.0410686, 'K2': 30.0821373, 'L2': 29.5284789,
    'M1': 14.4966939, 'M2': 28.9841042, 'M3': 43.4761563, 'M4': 57.9682084,
    'M6': 86.9523126, 'M8': 115.9364169, 'N2': 28.4397295, '2N2': 27.8953548,
    'O1': 13.9430356, 'OO1': 16.1391017, 'P1': 14.9589314, 'Q1': 13.3986609,
    '2Q1': 12.8542862, 'R2': 30.0410667, 'S1': 15.0000000, 'S2': 30.0000000,
    'S4': 60.0000000, 'S6': 90.0000000, 'T2': 29.9589333, 'LDA2': 29.4556253,
    'MU2': 27.9682084, 'NU2': 28.5125831, 'RHO1': 13.4715145, 'MK3': 44.0251729,
    '2MK3': 42.9271398, 'MN4': 57.4238337, 'MS4': 58.9841042, '2SM2': 31.0158958,
    'MF': 1.0980331, 'MSF': 1.0158958, 'MM': 0.5443747, 'SA': 0.0410686,
    'SSA': 0.0821373, 'SA-IOS': 0.0410667, 'MF-IOS': 1.0980331,
    'S1-IOS': 15.0000020, 'OO1-IOS': 16.1391017, 'R2-IOS': 30.0410667,
    'A7': 1.6424078, '2MK5': 73.0092771, '2MK6': 88.0503457, '2MN2': 29.5284789,
    '2MN6': 86.4079379, '2MS6': 87.9682084, '2NM6': 85.8635632, '2SK5': 75.0410686,
    '2SM6': 88.9841042, '3MK7': 101.9933813, '3MN8': 115.3920422, '3MS2': 26.9523126,
    '3MS4': 56.9523126, '3MS8': 116.9523126, 'ALP1': 12.3827651, 'BET1': 14.4145567,
    'CHI1': 14.5695476, 'H1': 28.9430375, 'H2': 29.0251709, 'KJ2': 30.6265120,
    'ETA2': 30.6265120, 'KQ1': 16.6834764, 'UPS1': 16.6834764, 'M10': 144.9205211,
    'M12': 173.9046253, 'MK4': 59.0662415, 'MKS2': 29.0662415, 'MNS2': 27.4238337,
    'EPS2': 27.4238337, 'MO3': 42.9271398, 'MP1': 14.0251729, 'TAU1': 14.0251729,
    'MPS2': 28.9430356, 'MSK6': 89.0662415, 'MSM': 0.4715211, 'MSN2': 30.5443747,
    'MSN6': 87.4238337, 'NLK2': 27.8860711, 'NO1': 14.4966939, 'OP2': 28.9019669,
    'OQ2': 27.3509801, 'PHI1': 15.1232059, 'KP1': 15.1232059, 'PI1': 14.9178647,
    'TK1': 14.9178647, 'PSI1': 15.0821353, 'RP1': 15.0821353, 'S3': 45.0000000,
    'SIG1': 12.9271398, 'SK3': 45.0410686, 'SK4': 60.0821373, 'SN4': 58.4397295,
    'SNK6': 88.5218668, 'SO1': 16.0569644, 'SO3': 43.9430356, 'THE1': 15.5125897,
    '2PO1': 15.9748271, '2NS2': 26.8794590, 'MLN2S2': 26.9523126, '2ML2S2': 27.4966873,
    'SKM2': 31.0980331, '2MS2K2': 27.8039339, 'MKL2S2': 28.5947204, 'M2(KS)2': 29.1483788,
    '2SN(MK)2': 29.3734880, '2KM(SN)2': 30.7086493, 'NO3': 42.3827651, '2MLS4': 57.4966873,
    'ML4': 58.5125831, 'N4': 56.8794590, 'SL4': 59.5284789, 'MNO5': 71.3668693,
    '2MO5': 71.9112440, 'MSK5': 74.0251729, '3KM5': 74.1073101, '2MP5': 72.9271398,
    '3MP5': 71.9933813, 'MNK5': 72.4649024, '2NMLS6': 85.3920422, 'MSL6': 88.5125831,
    '2ML6': 87.4966873, '2MNLS6': 85.9364169, '3MLS6': 86.4807916, '2MNO7': 100.3509735,
    '2NMK7': 100.9046319, '2MSO7': 101.9112440, 'MSKO7': 103.0092771, '2MSN8': 116.4079379,
    '2(MS)8': 117.9682084, '2(MN)8': 114.8476675, '2MSL8': 117.4966873, '4MLS8': 115.4648958,
    '3ML8': 116.4807916, '3MK8': 117.0344499, '2MSK8': 118.0503457, '2M2NK9': 129.8887361,
    '3MNK9': 130.4331108, '4MK9': 130.9774855, '3MSK9': 131.9933813, '4MN10': 144.3761464,
    '3MNS10': 145.3920422, '4MS10': 145.9364169, '3MSL10': 146.4807916, '3M2S10': 146.9523126,
    '4MSK11': 160.9774855, '4MNS12': 174.3761464, '5MS12': 174.9205211, '4MSL12': 175.4648958,
    '4M2S12': 175.9364169, 'M1C': 14.4920521, '3MKS2': 26.8701754, 'OQ2-HORN': 27.3416965,
    'MSK2': 28.9019669, 'MSP2': 29.0251729, '2MP3': 43.0092771, '4MS4': 55.9364169,
    '2MNS4': 56.4079379, '2MSK4': 57.8860711, '3MN4': 58.5125831, '2MSN4': 59.5284789,
    '3MK5': 71.9112440, '3MO5': 73.0092771, '3MNS6': 85.3920422, '4MS6': 85.9364169,
    '2MNU6': 86.4807916, '3MSK6': 86.8701754, 'MKNU6': 87.5788246, '3MSN6': 88.5125831,
    'M7': 101.4490066, '2MNK8': 116.4900752, '2(MS)N10': 146.4079379, 'MNUS2': 27.4966873,
    '2MK2': 27.8860711
}

# Constituents with duplicate frequencies (aliases) - map to primary constituent
CONSTITUENT_ALIASES = {
    'SA-IOS': 'SA', 'MF-IOS': 'MF', 'S1-IOS': 'S1', 'OO1-IOS': 'OO1', 'R2-IOS': 'R2',
    '2MN2': 'L2', 'ETA2': 'KJ2', 'UPS1': 'KQ1', 'EPS2': 'MNS2', 'TAU1': 'MP1',
    'KP1': 'PHI1', 'TK1': 'PI1', 'RP1': 'PSI1', 'MLN2S2': '3MS2', '3MN4': 'ML4',
    '3MK5': '2MO5', '3MO5': '2MK5', '3MNS6': '2NMLS6', '4MS6': '2MNLS6',
    '2MNU6': '3MLS6', '3MSN6': 'MSL6', 'MSK2': 'OP2', 'MNUS2': '2ML2S2',
    '2MK2': 'NLK2', 'MO3': '2MK3', 'NO1': 'M1'
}

# Station name corrections
STATION_NAME_CORRECTIONS = {
    'STEUBENHOFT': 'Steubenhoeft',
    'CUXHAVENSTEUBENHFT': 'Cuxhaven Steubenhoeft',
    'BHVALTERLEUCHTTURM': 'Bremerhaven Alter Leuchtturm',
    'BORKUMFISCHERBALJE': 'Borkum Fischerbalje',
    'BORKUMSDSTRAND': 'Borkum Suedstrand',
    'BREMERVRDEUW': 'Bremervoerde UW',
    'BRUNSBTTELMPM': 'Brunsbuettel MPM',
    'BARDOWICKOP': 'Bardowick OP',
    'BARDOWICKUP': 'Bardowick UP',
    'EIDERSPERRWERKAP': 'Eidersperrwerk AP',
    'EIDERSPERRWERKBP': 'Eidersperrwerk BP',
    'ELSFLETHOHRT': 'Elsfleth Ohrt',
    'EMDENNEUESEESCHLEUSE': 'Emden Neue Seeschleuse',
    'BUTTELERHRNE': 'Butteler Hoerne',
    'DREYSCHLOOT': 'Dreyschloot',
    'DUKEGAT': 'Dukegat',
    'DWARSGAT': 'Dwarsgat',
    'ELMSHORNHAFEN': 'Elmshorn Hafen',
}


def fetch_station_coordinates():
    """Fetch station coordinates from PEGELONLINE API."""
    url = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json"
    try:
        print("Fetching station coordinates from PEGELONLINE API...")
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))

        coords = {}
        for station in data:
            shortname = station.get('shortname', '').upper().replace(' ', '').replace('-', '')
            shortname = shortname.replace('Ü', 'UE').replace('Ö', 'OE').replace('Ä', 'AE').replace('ß', 'SS')
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
    match = re.match(r'pegelonline-([a-z0-9äöüß]+)-W-', filename, re.IGNORECASE)
    if match:
        name = match.group(1).upper()
        name = name.replace('Ü', 'UE').replace('Ö', 'OE').replace('Ä', 'AE').replace('ß', 'SS')
        return name
    return None


def format_station_name(raw_name, longname=None):
    """Format station name for display."""
    upper = raw_name.upper().replace('Ü', 'UE').replace('Ö', 'OE').replace('Ä', 'AE')
    if upper in STATION_NAME_CORRECTIONS:
        return STATION_NAME_CORRECTIONS[upper]

    if longname and len(longname) > 2:
        # Convert German umlauts
        name = longname
        name = name.replace('ü', 'ue').replace('ö', 'oe').replace('ä', 'ae').replace('ß', 'ss')
        name = name.replace('Ü', 'Ue').replace('Ö', 'Oe').replace('Ä', 'Ae')
        return name.title()

    name = raw_name.replace('-', ' ').replace('_', ' ')
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    return name.title()


def parse_json_waterlevels(json_path, downsample_minutes=15):
    """Parse water level JSON file."""
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

    if len(times_hours) < 1000:
        return None

    times = np.array(times_hours)
    levels = np.array(levels_m)

    # Sort by time
    sort_idx = np.argsort(times)
    times = times[sort_idx]
    levels = levels[sort_idx]

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


def get_analysis_constituents():
    """Get unique constituents for analysis (excluding aliases)."""
    unique = []
    seen_speeds = set()

    for name in CONSTITUENT_ORDER:
        if name in CONSTITUENT_ALIASES:
            continue
        speed = CONSTITUENT_SPEEDS.get(name)
        if speed is None:
            continue
        speed_key = round(speed, 5)
        if speed_key not in seen_speeds:
            unique.append(name)
            seen_speeds.add(speed_key)

    return unique


def harmonic_analysis(times, levels):
    """Perform harmonic analysis using least squares."""
    analysis_constituents = get_analysis_constituents()

    n_obs = len(times)
    n_constit = len(analysis_constituents)

    # Build design matrix
    A = np.ones((n_obs, 1 + 2 * n_constit), dtype=np.float64)

    for i, name in enumerate(analysis_constituents):
        omega = np.radians(CONSTITUENT_SPEEDS[name])
        A[:, 1 + 2*i] = np.cos(omega * times)
        A[:, 2 + 2*i] = np.sin(omega * times)

    # Solve least squares
    x, residuals, rank, s = np.linalg.lstsq(A, levels, rcond=None)

    results = {
        'Z0': x[0],
        'constituents': {},
    }

    for i, name in enumerate(analysis_constituents):
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

    # Fill aliases with values from their primary constituents
    for alias, primary in CONSTITUENT_ALIASES.items():
        if primary in results['constituents']:
            results['constituents'][alias] = results['constituents'][primary].copy()
        else:
            results['constituents'][alias] = {'amplitude': 0.0, 'phase': 0.0}

    # Calculate fit statistics
    h_predicted = A @ x
    residual_values = levels - h_predicted
    ss_res = np.sum(residual_values**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)

    results['r_squared'] = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    results['rms_error'] = np.sqrt(np.mean(residual_values**2))

    return results


def format_station_block(station_name, lat, lon, datum, results, source_info=None):
    """Format a single station block in XTide format with 175 constituents."""
    lines = []

    # Hot comments (metadata)
    lines.append("# Harmonic constants derived from PEGELONLINE data")
    if source_info:
        if 'start_date' in source_info and source_info['start_date']:
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

    # All 175 constituents in order
    for const_name in CONSTITUENT_ORDER:
        if const_name in results['constituents']:
            c = results['constituents'][const_name]
            amp = c['amplitude']
            phase = c['phase']
            if amp >= 0.0001:  # >= 0.1mm
                lines.append(f"{const_name:16s} {amp:.4f}  {phase:.2f}")
            else:
                lines.append("x 0 0")
        else:
            lines.append("x 0 0")

    return lines


def convert_to_iso8859(text):
    """Convert text to ISO-8859-1."""
    replacements = {
        '\u00f6': 'oe', '\u00e4': 'ae', '\u00fc': 'ue',
        '\u00d6': 'Oe', '\u00c4': 'Ae', '\u00dc': 'Ue',
        '\u00df': 'ss',
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    try:
        return text.encode('iso-8859-1').decode('iso-8859-1')
    except UnicodeEncodeError:
        return text.encode('iso-8859-1', errors='replace').decode('iso-8859-1')


def process_all_stations(input_dir, header_file, output_file):
    """Process all water level ZIP files and generate harmonics file."""
    input_path = Path(input_dir)
    header_path = Path(header_file)
    output_path = Path(output_file)

    # Get station coordinates
    station_coords = fetch_station_coordinates()

    # Read header from existing file (up to second *END*)
    print(f"\nReading header from {header_path}...")
    header_lines = []
    end_count = 0
    with open(header_path, 'r', encoding='iso-8859-1') as f:
        for line in f:
            header_lines.append(line.rstrip('\n'))
            if '*END*' in line and not line.strip().startswith('#'):
                end_count += 1
                if end_count == 2:
                    break

    print(f"  Read {len(header_lines)} header lines")

    # Add standard comments after header
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

    # Find all ZIP files (exclude Zone.Identifier files)
    all_files = list(input_path.glob('pegelonline-*-W-*.zip'))
    zip_files = sorted([f for f in all_files if 'Zone.Identifier' not in str(f) and not str(f).endswith(':Zone.Identifier')])
    print(f"\nFound {len(zip_files)} ZIP files to process (excluded Zone.Identifier files)")

    # Process each station
    station_blocks = []
    processed = 0
    failed = 0

    for i, zip_path in enumerate(zip_files):
        if ':Zone.Identifier' in str(zip_path):
            continue

        station_id = extract_station_name_from_filename(zip_path.name)
        if not station_id:
            continue

        print(f"\n[{i+1}/{len(zip_files)}] Processing {station_id}...")

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                json_files = [n for n in zf.namelist() if n.endswith('.json')]
                if not json_files:
                    print(f"  No JSON file found")
                    failed += 1
                    continue

                # Read metadata
                station_info = {}
                try:
                    info_content = zf.read('zeitreiheninformation.txt').decode('utf-8')
                    for line in info_content.split('\n'):
                        if '=' in line:
                            key, val = line.split('=', 1)
                            station_info[key.strip()] = val.strip()
                except:
                    pass

                # Extract and parse JSON
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
                lat, lon = 54.0, 9.0  # Default for Germany
                longname = station_info.get('station_name', station_id)

                if station_id in station_coords:
                    lat = station_coords[station_id]['lat']
                    lon = station_coords[station_id]['lon']
                    longname = station_coords[station_id].get('longname', longname)

                # Perform harmonic analysis
                print(f"  Performing harmonic analysis with {len(get_analysis_constituents())} unique constituents...")
                results = harmonic_analysis(data['times'], data['levels'])

                print(f"  R^2 = {results['r_squared']:.4f}, RMS = {results['rms_error']:.4f} m")

                # Skip stations with poor fit
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
            import traceback
            traceback.print_exc()
            failed += 1
            continue

    # Write output file
    print(f"\n{'='*60}")
    print(f"Writing output to {output_path}...")

    with open(output_path, 'w', encoding='iso-8859-1', errors='replace') as f:
        for line in header_lines:
            f.write(convert_to_iso8859(line) + '\n')

        for block in station_blocks:
            for line in block:
                f.write(convert_to_iso8859(line) + '\n')

    print(f"\nSummary:")
    print(f"  Processed: {processed} stations")
    print(f"  Failed: {failed} stations")
    print(f"  Output: {output_path}")


def main():
    input_dir = "/home/oliver/water_levels/Germany"
    header_file = "/home/oliver/harmonics_working/harmonics-dwf-20070318_no_us_no_dupes.txt"
    output_file = "/home/oliver/harmonics_working/harmonics_germany_2026-01-23.txt"

    print("="*60)
    print("GENERATE HARMONIC CONSTANTS FROM PEGELONLINE DATA")
    print("175 Constituents - XTide Format")
    print("="*60)

    process_all_stations(input_dir, header_file, output_file)

    print("\nDone!")


if __name__ == "__main__":
    main()
