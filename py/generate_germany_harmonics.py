#!/usr/bin/env python3
"""
Generate harmonic constants from German Pegelonline water level data.
Appends stations to existing XTide harmonics file.
Output encoding: ISO-8859-1
"""

import numpy as np
from datetime import datetime, timedelta
import zipfile
import json
import os
import sys
import urllib.request

# Tidal constituent frequencies (degrees per hour)
# Must match the order in the harmonics file header
CONSTITUENTS_ORDERED = [
    ('J1', 15.5854433),
    ('K1', 15.0410686),
    ('K2', 30.0821373),
    ('L2', 29.5284789),
    ('M1', 14.4966939),
    ('M2', 28.9841042),
    ('M3', 43.4761563),
    ('M4', 57.9682084),
    ('M6', 86.9523126),
    ('M8', 115.9364169),
    ('N2', 28.4397295),
    ('2N2', 27.8953548),
    ('O1', 13.9430356),
    ('OO1', 16.1391017),
    ('P1', 14.9589314),
    ('Q1', 13.3986609),
    ('2Q1', 12.8542862),
    ('R2', 30.0410667),
    ('S1', 15.0000000),
    ('S2', 30.0000000),
    ('S4', 60.0000000),
    ('S6', 90.0000000),
    ('T2', 29.9589333),
    ('LDA2', 29.4556253),
    ('MU2', 27.9682084),
    ('NU2', 28.5125831),
    ('RHO1', 13.4715145),
    ('MK3', 44.0251729),
    ('2MK3', 42.9271398),
    ('MN4', 57.4238337),
    ('MS4', 58.9841042),
    ('2SM2', 31.0158958),
    ('MF', 1.0980331),
    ('MSF', 1.0158958),
    ('MM', 0.5443747),
    ('SA', 0.0410686),
    ('SSA', 0.0821373),
    ('SA-IOS', 0.0410667),
    ('MF-IOS', 1.0980331),
    ('S1-IOS', 15.0000020),
    ('OO1-IOS', 16.1391017),
    ('R2-IOS', 30.0410667),
    ('A7', 1.6424078),
    ('2MK5', 73.0092771),
    ('2MK6', 88.0503457),
    ('2MN2', 29.5284789),
    ('2MN6', 86.4079379),
    ('2MS6', 87.9682084),
    ('2NM6', 85.8635632),
    ('2SK5', 75.0410686),
    ('2SM6', 88.9841042),
    ('3MK7', 101.9933813),
    ('3MN8', 115.3920422),
    ('3MS2', 26.9523126),
    ('3MS4', 56.9523126),
    ('3MS8', 116.9523126),
    ('ALP1', 12.3827651),
    ('BET1', 14.4145567),
    ('CHI1', 14.5695476),
    ('H1', 28.9430375),
    ('H2', 29.0251709),
    ('KJ2', 30.6265120),
    ('ETA2', 30.6265120),
    ('KQ1', 16.6834764),
    ('UPS1', 16.6834764),
    ('M10', 144.9205211),
    ('M12', 173.9046253),
    ('MK4', 59.0662415),
    ('MKS2', 29.0662415),
    ('MNS2', 27.4238337),
    ('EPS2', 27.4238337),
    ('MO3', 42.9271398),
    ('MP1', 14.0251729),
    ('TAU1', 14.0251729),
    ('MPS2', 28.9430356),
    ('MSK6', 89.0662415),
    ('MSM', 0.4715211),
    ('MSN2', 30.5443747),
    ('MSN6', 87.4238337),
    ('NLK2', 27.8860711),
    ('NO1', 14.4966939),
    ('OP2', 28.9019669),
    ('OQ2', 27.3509801),
    ('PHI1', 15.1232059),
    ('KP1', 15.1232059),
    ('PI1', 14.9178647),
    ('TK1', 14.9178647),
    ('PSI1', 15.0821353),
    ('RP1', 15.0821353),
    ('S3', 45.0000000),
    ('SIG1', 12.9271398),
    ('SK3', 45.0410686),
    ('SK4', 60.0821373),
    ('SN4', 58.4397295),
    ('SNK6', 88.5218668),
    ('SO1', 16.0569644),
    ('SO3', 43.9430356),
    ('THE1', 15.5125897),
    ('2PO1', 15.9748271),
    ('2NS2', 26.8794590),
    ('MLN2S2', 26.9523126),
    ('2ML2S2', 27.4966873),
    ('SKM2', 31.0980331),
    ('2MS2K2', 27.8039339),
    ('MKL2S2', 28.5947204),
    ('M2(KS)2', 29.1483788),
    ('2SN(MK)2', 29.3734880),
    ('2KM(SN)2', 30.7086493),
    ('NO3', 42.3827651),
    ('2MLS4', 57.4966873),
    ('ML4', 58.5125831),
    ('N4', 56.8794590),
    ('SL4', 59.5284789),
    ('MNO5', 71.3668693),
    ('2MO5', 71.9112440),
    ('MSK5', 74.0251729),
    ('3KM5', 74.1073101),
    ('2MP5', 72.9271398),
    ('3MP5', 71.9933813),
    ('MNK5', 72.4649024),
    ('2NMLS6', 85.3920422),
    ('MSL6', 88.5125831),
    ('2ML6', 87.4966873),
    ('2MNLS6', 85.9364169),
    ('3MLS6', 86.4807916),
    ('2MNO7', 100.3509735),
    ('2NMK7', 100.9046319),
    ('2MSO7', 101.9112440),
    ('MSKO7', 103.0092771),
    ('2MSN8', 116.4079379),
    ('2(MS)8', 117.9682084),
    ('2(MN)8', 114.8476675),
    ('2MSL8', 117.4966873),
    ('4MLS8', 115.4648958),
    ('3ML8', 116.4807916),
    ('3MK8', 117.0344499),
    ('2MSK8', 118.0503457),
    ('2M2NK9', 129.8887361),
    ('3MNK9', 130.4331108),
    ('4MK9', 130.9774855),
    ('3MSK9', 131.9933813),
    ('4MN10', 144.3761464),
    ('3MNS10', 145.3920422),
    ('4MS10', 145.9364169),
    ('3MSL10', 146.4807916),
    ('3M2S10', 146.9523126),
    ('4MSK11', 160.9774855),
    ('4MNS12', 174.3761464),
    ('5MS12', 174.9205211),
    ('4MSL12', 175.4648958),
    ('4M2S12', 175.9364169),
    ('M1C', 14.4920521),
    ('3MKS2', 26.8701754),
    ('OQ2-HORN', 27.3416965),
    ('MSK2', 28.9019669),
    ('MSP2', 29.0251729),
    ('2MP3', 43.0092771),
    ('4MS4', 55.9364169),
    ('2MNS4', 56.4079379),
    ('2MSK4', 57.8860711),
    ('3MN4', 58.5125831),
    ('2MSN4', 59.5284789),
    ('3MK5', 71.9112440),
    ('3MO5', 73.0092771),
    ('3MNS6', 85.3920422),
    ('4MS6', 85.9364169),
    ('2MNU6', 86.4807916),
    ('3MSK6', 86.8701754),
    ('MKNU6', 87.5788246),
    ('3MSN6', 88.5125831),
    ('M7', 101.4490066),
    ('2MNK8', 116.4900752),
    ('2(MS)N10', 146.4079379),
    ('MNUS2', 27.4966873),
    ('2MK2', 27.8860711),
]

# Constituents we can reliably analyze (subset for analysis)
ANALYSIS_CONSTITUENTS = [
    'M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1',
    'M4', 'MS4', 'MN4', 'M6', '2MS6', '2MN6',
    'SA', 'SSA', 'MM', 'MF', 'MSF',
    'L2', 'T2', '2N2', 'MU2', 'NU2',
    'M1', 'J1', 'OO1', '2Q1', 'RHO1',
    'M3', 'MK3', '2MK3',
    'S4', 'S6', 'M8',
    '2SM2', 'MSK6'
]


def get_pegelonline_stations():
    """Fetch station metadata from Pegelonline API."""
    url = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
        # Create lookup by UUID
        stations = {}
        for s in data:
            stations[s['uuid']] = {
                'name': s.get('longname', s.get('shortname', '')),
                'shortname': s.get('shortname', ''),
                'latitude': s.get('latitude'),
                'longitude': s.get('longitude'),
                'water': s.get('water', {}).get('longname', ''),
                'agency': s.get('agency', '')
            }
        return stations
    except Exception as e:
        print(f"Error fetching stations: {e}")
        return {}


def parse_pegelonline_zip(zip_path):
    """Parse water level data from Pegelonline ZIP export."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        # Find JSON file
        json_files = [f for f in zf.namelist() if f.endswith('.json')]
        if not json_files:
            raise ValueError(f"No JSON file found in {zip_path}")

        # Read JSON data
        with zf.open(json_files[0]) as f:
            timeseries = json.load(f)

        # Read metadata
        metadata = {}
        if 'zeitreiheninformation.txt' in zf.namelist():
            with zf.open('zeitreiheninformation.txt') as f:
                for line in f.read().decode('utf-8').splitlines():
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        metadata[key.strip()] = value.strip()

    return timeseries, metadata


def timeseries_to_arrays(timeseries):
    """Convert timeseries to numpy arrays."""
    times = []
    levels = []

    # Parse first timestamp to get reference
    first_ts = datetime.fromisoformat(timeseries[0]['timestamp'].replace('Z', '+00:00'))

    for entry in timeseries:
        if entry.get('value') is None:
            continue
        ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
        # Convert to hours since start
        hours = (ts - first_ts).total_seconds() / 3600.0
        times.append(hours)
        levels.append(entry['value'] / 100.0)  # cm to meters

    return np.array(times), np.array(levels), first_ts


def harmonic_analysis(times, levels, constituents):
    """
    Perform harmonic analysis using least squares.
    Returns dict of {name: (amplitude, phase)} for each constituent.
    """
    n_obs = len(times)
    n_constit = len(constituents)

    # Build design matrix: h(t) = A0 + sum_i [a_i*cos + b_i*sin]
    A = np.ones((n_obs, 1 + 2 * n_constit))

    freq_dict = {name: freq for name, freq in CONSTITUENTS_ORDERED}

    for i, name in enumerate(constituents):
        if name not in freq_dict:
            print(f"Warning: Unknown constituent {name}")
            continue
        omega = np.radians(freq_dict[name])  # deg/hour to rad/hour
        A[:, 1 + 2*i] = np.cos(omega * times)
        A[:, 2 + 2*i] = np.sin(omega * times)

    # Solve least squares
    try:
        x, residuals, rank, s = np.linalg.lstsq(A, levels, rcond=None)
    except Exception as e:
        print(f"Least squares failed: {e}")
        return None, None

    mean_level = x[0]
    results = {}

    for i, name in enumerate(constituents):
        a_cos = x[1 + 2*i]
        a_sin = x[2 + 2*i]

        amplitude = np.sqrt(a_cos**2 + a_sin**2)
        # Phase (epoch) in degrees
        phase = np.degrees(np.arctan2(a_sin, a_cos))
        if phase < 0:
            phase += 360

        results[name] = (amplitude, phase)

    return mean_level, results


def to_iso_8859_1(text):
    """Convert text to ISO-8859-1 compatible, replacing incompatible chars."""
    # German umlauts should work in ISO-8859-1
    try:
        text.encode('iso-8859-1')
        return text
    except UnicodeEncodeError:
        # Replace characters that can't be encoded
        replacements = {
            '\u2013': '-',  # en-dash
            '\u2014': '-',  # em-dash
            '\u2018': "'",  # left single quote
            '\u2019': "'",  # right single quote
            '\u201c': '"',  # left double quote
            '\u201d': '"',  # right double quote
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        # Try again, replace remaining with ?
        result = []
        for char in text:
            try:
                char.encode('iso-8859-1')
                result.append(char)
            except UnicodeEncodeError:
                result.append('?')
        return ''.join(result)


def to_title_case(text):
    """Convert text to title case (first letter uppercase, rest lowercase)."""
    words = text.split()
    result = []
    for word in words:
        if word:
            # Handle special cases like "UP", "OP", "UW" etc.
            result.append(word.capitalize())
    return ' '.join(result)


def format_station_entry(station_name, latitude, longitude, mean_level,
                         harmonics, water_body='', station_uuid=''):
    """Format a station entry for XTide harmonics file."""
    lines = []

    # Hot comments (metadata)
    lines.append("# ")
    lines.append("# BEGIN HOT COMMENTS")
    lines.append("# country: Germany")
    lines.append("# source: Pegelonline WSV")
    lines.append("# restriction: Public domain")
    lines.append("# station_id_context: Pegelonline")
    lines.append(f"# station_id: {station_uuid}")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append("# datum: Mean Sea Level")
    lines.append("# confidence: 8")
    lines.append("# !units: meters")
    lines.append(f"# !longitude: {longitude:.4f}")
    lines.append(f"# !latitude: {latitude:.4f}")

    # Station name (title case)
    station_title = to_title_case(station_name)
    water_title = to_title_case(water_body)
    name = to_iso_8859_1(f"{station_title}, {water_title}, Germany")
    lines.append(name)

    # Timezone: +01:00 for CET calibrated data
    lines.append("+01:00 :Europe/Berlin")

    # Datum (mean level) and units
    lines.append(f"{mean_level:.4f} meters")

    # All 175 constituents in order
    for const_name, const_freq in CONSTITUENTS_ORDERED:
        if const_name in harmonics:
            amp, phase = harmonics[const_name]
            if amp > 0.0001:  # Only include if significant
                lines.append(f"{const_name:16s} {amp:7.4f}  {phase:6.2f}")
            else:
                lines.append("x 0 0")
        else:
            lines.append("x 0 0")

    return '\n'.join(lines)


def process_station(zip_path, api_stations, processed_names):
    """Process a single station ZIP file."""
    print(f"\nProcessing: {os.path.basename(zip_path)}")

    try:
        timeseries, metadata = parse_pegelonline_zip(zip_path)
    except Exception as e:
        print(f"  Error reading ZIP: {e}")
        return None

    station_uuid = metadata.get('station_uuid', '')
    station_name = metadata.get('station_name', '')
    water_body = metadata.get('station_water', '')

    # Check for duplicate names
    if station_name in processed_names:
        print(f"  Skipping duplicate: {station_name}")
        return None

    print(f"  Station: {station_name}")
    print(f"  Water: {water_body}")
    print(f"  UUID: {station_uuid}")
    print(f"  Data points: {len(timeseries)}")

    # Get coordinates from API
    if station_uuid in api_stations:
        api_info = api_stations[station_uuid]
        latitude = api_info['latitude']
        longitude = api_info['longitude']
        print(f"  Coordinates: {latitude:.4f}N, {longitude:.4f}E")
    else:
        print(f"  WARNING: No coordinates found for {station_uuid}")
        # Try to find by name
        for uuid, info in api_stations.items():
            if info['shortname'].upper() == station_name.upper():
                latitude = info['latitude']
                longitude = info['longitude']
                print(f"  Found by name: {latitude:.4f}N, {longitude:.4f}E")
                break
        else:
            print(f"  SKIPPING: No coordinates available")
            return None

    # Convert to arrays
    try:
        times, levels, start_time = timeseries_to_arrays(timeseries)
    except Exception as e:
        print(f"  Error converting data: {e}")
        return None

    print(f"  Time span: {times[-1]/24/365.25:.1f} years")
    print(f"  Level range: {levels.min():.2f}m to {levels.max():.2f}m")

    # Downsample for faster analysis (hourly data is fine for tides)
    # Original is 1-minute data
    step = 15  # Use 15-minute intervals
    times_ds = times[::step]
    levels_ds = levels[::step]
    print(f"  Downsampled to {len(times_ds)} points")

    # Perform harmonic analysis
    print(f"  Running harmonic analysis...")
    mean_level, harmonics = harmonic_analysis(times_ds, levels_ds, ANALYSIS_CONSTITUENTS)

    if harmonics is None:
        print(f"  Analysis failed")
        return None

    print(f"  Mean level: {mean_level:.4f}m")

    # Show top constituents
    sorted_harmonics = sorted(harmonics.items(), key=lambda x: x[1][0], reverse=True)
    print(f"  Top 5 constituents:")
    for name, (amp, phase) in sorted_harmonics[:5]:
        print(f"    {name:6s}: {amp:.4f}m @ {phase:.1f}deg")

    # Format entry
    entry = format_station_entry(
        station_name=station_name,
        latitude=latitude,
        longitude=longitude,
        mean_level=mean_level,
        harmonics=harmonics,
        water_body=water_body,
        station_uuid=station_uuid
    )

    return station_name, entry


def main():
    # Configuration
    zip_dir = "/home/oliver/water_levels/Germany"
    output_file = "/home/oliver/harmonics_working/harmonics_germany_pegelonline_2026-01-23.txt"
    max_stations = 20

    # Get list of ZIP files (excluding Zone.Identifier files)
    zip_files = sorted([
        os.path.join(zip_dir, f)
        for f in os.listdir(zip_dir)
        if f.endswith('.zip') and 'Zone.Identifier' not in f
    ])[:max_stations]

    print(f"Found {len(zip_files)} ZIP files to process")
    print("Files:")
    for f in zip_files:
        print(f"  {os.path.basename(f)}")

    # Fetch station coordinates from API
    print("\nFetching station metadata from Pegelonline API...")
    api_stations = get_pegelonline_stations()
    print(f"Got {len(api_stations)} stations from API")

    # Process stations
    processed_names = set()
    entries = []

    for zip_path in zip_files:
        result = process_station(zip_path, api_stations, processed_names)
        if result:
            name, entry = result
            processed_names.add(name)
            entries.append(entry)

    print(f"\n{'='*60}")
    print(f"Successfully processed {len(entries)} stations")

    if entries:
        # Append to existing file
        print(f"\nAppending to {output_file}")

        with open(output_file, 'a', encoding='iso-8859-1') as f:
            for entry in entries:
                f.write('\n')
                f.write(entry)

        print("Done!")

        # List processed stations
        print("\nProcessed stations:")
        for name in sorted(processed_names):
            print(f"  - {name}")
    else:
        print("No stations were processed successfully")


if __name__ == "__main__":
    main()
