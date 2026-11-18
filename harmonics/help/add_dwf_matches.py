#!/usr/bin/env python3
"""
Find matching stations between Pegelonline and DWF harmonics files,
generate tide predictions for DWF stations, and add to ODS file.
"""

import subprocess
import re
import math
from datetime import datetime
from odf.opendocument import load, OpenDocumentSpreadsheet
from odf.table import Table, TableRow, TableCell
from odf.text import P

def extract_stations_from_harmonics(harmonics_file, encoding='iso-8859-1'):
    """Extract station information from harmonics text file."""
    stations = []
    current_station = {}

    with open(harmonics_file, 'r', encoding=encoding, errors='replace') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line = line.strip()

        # Look for latitude
        if line.startswith('# !latitude:'):
            current_station['latitude'] = float(line.split(':')[1].strip())

        # Look for longitude
        elif line.startswith('# !longitude:'):
            current_station['longitude'] = float(line.split(':')[1].strip())

        # Look for station name (line ends with ", Germany" and doesn't start with #)
        elif line.endswith(', Germany') and not line.startswith('#'):
            current_station['name'] = line
            # Next line should be timezone
            if i + 1 < len(lines):
                tz_line = lines[i + 1].strip()
                # Format: "+01:00 :Europe/Berlin"
                if ':' in tz_line:
                    parts = tz_line.split(':')
                    if len(parts) >= 3:
                        current_station['timezone'] = parts[2].strip()
                    else:
                        current_station['timezone'] = tz_line

            if 'latitude' in current_station and 'longitude' in current_station:
                stations.append(current_station.copy())
            current_station = {}

    return stations

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km."""
    R = 6371  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

def normalize_name(name):
    """Normalize station name for comparison."""
    # Remove country suffix
    name = re.sub(r',\s*Germany$', '', name)
    # Convert to lowercase
    name = name.lower()
    # Replace umlauts
    name = name.replace('ä', 'a').replace('ö', 'o').replace('ü', 'u').replace('ß', 'ss')
    # Remove special chars and extra spaces
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def find_matches(pegelonline_stations, dwf_stations, max_distance_km=10):
    """Find matching stations based on name similarity and coordinates."""
    matches = []

    for dwf in dwf_stations:
        dwf_norm = normalize_name(dwf['name'])
        best_match = None
        best_score = 0

        for pegel in pegelonline_stations:
            pegel_norm = normalize_name(pegel['name'])

            # Calculate coordinate distance
            distance = haversine_distance(
                dwf['latitude'], dwf['longitude'],
                pegel['latitude'], pegel['longitude']
            )

            # Name similarity check
            name_match = False

            # Extract main name (first word or part before parenthesis)
            dwf_main = dwf_norm.split()[0] if dwf_norm else ''
            pegel_main = pegel_norm.split()[0] if pegel_norm else ''

            # Check if main names match or one contains the other
            if dwf_main and pegel_main:
                if dwf_main == pegel_main:
                    name_match = True
                elif dwf_main in pegel_norm or pegel_main in dwf_norm:
                    name_match = True

            # Score based on distance and name match
            if distance <= max_distance_km:
                score = (max_distance_km - distance) / max_distance_km
                if name_match:
                    score += 1  # Bonus for name match

                if score > best_score:
                    best_score = score
                    best_match = {
                        'dwf': dwf,
                        'pegelonline': pegel,
                        'distance_km': distance,
                        'name_match': name_match
                    }

        if best_match:
            matches.append(best_match)
            print(f"  Match: {dwf['name']}")
            print(f"    -> {best_match['pegelonline']['name']}")
            print(f"    Distance: {best_match['distance_km']:.2f} km, Name match: {best_match['name_match']}")

    return matches

def get_tide_predictions(station_name, start_date, end_date, tcd_file):
    """Get tide predictions using the tide command."""
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    try:
        cmd = [
            'tide',
            '-l', station_name,
            '-b', f'{start_str} 00:00',
            '-e', f'{end_str} 23:59',
            '-m', 'p',
            '-em', 'pSsMm'
        ]

        env = {'HFILE_PATH': tcd_file}
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                              env=env, encoding='iso-8859-1')

        if result.returncode != 0:
            print(f"    Error: {result.stderr}")
            return []

        return parse_tide_output(result.stdout)

    except Exception as e:
        print(f"    Exception: {e}")
        return []

def parse_tide_output(output):
    """Parse tide command output to extract times and levels."""
    predictions = []

    for line in output.strip().split('\n'):
        if not line.strip():
            continue

        match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s+(AM|PM)\s+\w+\s+([\d.]+)\s+meters?\s+(High|Low)', line)

        if match:
            hour = int(match.group(2))
            minute = int(match.group(3))
            ampm = match.group(4)
            level = float(match.group(5))

            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0

            time_str = f'{hour:02d}:{minute:02d}'

            predictions.append({
                'time': time_str,
                'level': level
            })

    return predictions

def add_to_ods(ods_file, matches, predictions_data):
    """Add matched station predictions to existing ODS file."""
    doc = load(ods_file)
    table = doc.spreadsheet.getElementsByType(Table)[0]

    # Count existing columns to know how many time/level pairs we need
    header_row = table.getElementsByType(TableRow)[0]
    header_cells = header_row.getElementsByType(TableCell)

    # Find max pairs from existing header
    max_pairs = 0
    for cell in header_cells:
        p = cell.getElementsByType(P)
        if p:
            text = str(p[0])
            if text.startswith('Time_'):
                try:
                    num = int(text.replace('Time_', ''))
                    if num > max_pairs:
                        max_pairs = num
                except:
                    pass

    print(f"  Existing max pairs: {max_pairs}")

    # Add rows for each match
    for match in matches:
        dwf = match['dwf']
        preds = predictions_data.get(dwf['name'], [])

        row = TableRow()

        # Station name (with DWF suffix to distinguish)
        cell = TableCell()
        cell.addElement(P(text=f"{dwf['name']} [DWF]"))
        row.addElement(cell)

        # Latitude
        cell = TableCell()
        cell.addElement(P(text=str(dwf['latitude'])))
        row.addElement(cell)

        # Longitude
        cell = TableCell()
        cell.addElement(P(text=str(dwf['longitude'])))
        row.addElement(cell)

        # Timezone
        cell = TableCell()
        cell.addElement(P(text=dwf.get('timezone', 'Europe/Berlin')))
        row.addElement(cell)

        # Time/Level pairs
        for pred in preds[:max_pairs]:
            # Time
            cell = TableCell()
            cell.addElement(P(text=pred['time']))
            row.addElement(cell)

            # Level with comma
            level_str = f"{pred['level']:.2f}".replace('.', ',')
            cell = TableCell()
            cell.addElement(P(text=level_str))
            row.addElement(cell)

        # Fill remaining empty cells
        remaining = max_pairs - len(preds)
        for _ in range(remaining * 2):
            cell = TableCell()
            row.addElement(cell)

        table.addElement(row)

    doc.save(ods_file)
    print(f"  Added {len(matches)} rows to {ods_file}")

def main():
    pegelonline_file = '/home/oliver/harmonics_working/harmonics_germany_2026-01-23.txt'
    dwf_file = '/home/oliver/harmonics_working/harmonics-dwf-20070318_no_us_no_dupes.txt'
    ods_file = '/home/oliver/harmonics_working_help/tide_prediction_pegelonline_2026-01-27.ods'

    # TCD file is in /usr/share/xtide
    dwf_tcd = '/usr/share/xtide'

    start_date = datetime(2026, 1, 27)
    end_date = datetime(2026, 1, 30)

    print("Extracting Pegelonline stations...")
    pegelonline_stations = extract_stations_from_harmonics(pegelonline_file)
    print(f"  Found {len(pegelonline_stations)} stations")

    print("\nExtracting DWF stations (Germany only)...")
    all_dwf_stations = extract_stations_from_harmonics(dwf_file)
    # Filter to Germany only
    dwf_stations = [s for s in all_dwf_stations if s['name'].endswith(', Germany')]
    print(f"  Found {len(dwf_stations)} German stations")

    print("\nFinding matches...")
    matches = find_matches(pegelonline_stations, dwf_stations, max_distance_km=15)
    print(f"\nTotal matches found: {len(matches)}")

    if not matches:
        print("No matches found!")
        return

    print("\nGenerating tide predictions for DWF stations...")
    predictions_data = {}

    for match in matches:
        dwf_name = match['dwf']['name']
        print(f"  {dwf_name}")
        preds = get_tide_predictions(dwf_name, start_date, end_date, dwf_tcd)
        predictions_data[dwf_name] = preds
        print(f"    Got {len(preds)} predictions")

    print("\nAdding to ODS file...")
    add_to_ods(ods_file, matches, predictions_data)

    print("\nDone!")

if __name__ == '__main__':
    main()
