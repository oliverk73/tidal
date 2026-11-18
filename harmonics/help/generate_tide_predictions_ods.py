#!/usr/bin/env python3
"""
Generate tide predictions for all German stations and write to ODS file.
"""

import subprocess
import re
import os
from datetime import datetime, timedelta
from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableRow, TableCell
from odf.text import P

def extract_stations(harmonics_file):
    """Extract station information from harmonics text file."""
    stations = []
    current_station = {}

    with open(harmonics_file, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line = line.strip()

        # Look for latitude
        if line.startswith('# !latitude:'):
            current_station['latitude'] = line.split(':')[1].strip()

        # Look for longitude
        elif line.startswith('# !longitude:'):
            current_station['longitude'] = line.split(':')[1].strip()

        # Look for station name (line after coordinates, ends with ", Germany")
        elif line.endswith(', Germany') and not line.startswith('#'):
            current_station['name'] = line
            # Next line should be timezone
            if i + 1 < len(lines):
                tz_line = lines[i + 1].strip()
                # Format: "+01:00 :Europe/Berlin"
                if ':' in tz_line:
                    parts = tz_line.split(':')
                    if len(parts) >= 3:
                        current_station['timezone'] = parts[2].strip() if len(parts) > 2 else tz_line
                    else:
                        current_station['timezone'] = tz_line

            if 'latitude' in current_station and 'longitude' in current_station:
                stations.append(current_station.copy())
            current_station = {}

    return stations

def get_tide_predictions(station_name, start_date, end_date):
    """Get tide predictions using the tide command."""
    # Format dates for tide command
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    try:
        # Run tide command to get high/low tides
        cmd = [
            'tide',
            '-l', station_name,
            '-b', f'{start_str} 00:00',
            '-e', f'{end_str} 23:59',
            '-m', 'p',  # plain text mode
            '-em', 'pSsMm'  # events: high, low tides
        ]

        env = {'HFILE_PATH': '/usr/share/xtide'}
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env, encoding='iso-8859-1')

        if result.returncode != 0:
            print(f"  Error for {station_name}: {result.stderr}")
            return []

        return parse_tide_output(result.stdout)

    except subprocess.TimeoutExpired:
        print(f"  Timeout for {station_name}")
        return []
    except Exception as e:
        print(f"  Exception for {station_name}: {e}")
        return []

def parse_tide_output(output):
    """Parse tide command output to extract times and levels."""
    predictions = []

    for line in output.strip().split('\n'):
        if not line.strip():
            continue

        # Parse line format: "2026-01-27  1:11 AM CET   5.91 meters  High Tide"
        # or "2026-01-27 10:15 AM CET   2.45 meters  High Tide"
        match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s+(AM|PM)\s+\w+\s+([\d.]+)\s+meters?\s+(High|Low)', line)

        if match:
            date_str = match.group(1)
            hour = int(match.group(2))
            minute = int(match.group(3))
            ampm = match.group(4)
            level = float(match.group(5))
            tide_type = match.group(6)

            # Convert to 24-hour format
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0

            time_str = f'{hour:02d}:{minute:02d}'

            predictions.append({
                'date': date_str,
                'time': time_str,
                'level': level,
                'type': tide_type
            })

    return predictions

def create_ods_file(stations, predictions_data, output_file):
    """Create ODS file with tide predictions."""
    doc = OpenDocumentSpreadsheet()
    table = Table(name="Tide Predictions")

    # Determine max number of time/level pairs
    max_pairs = 0
    for preds in predictions_data.values():
        if len(preds) > max_pairs:
            max_pairs = len(preds)

    # Create header row
    header_row = TableRow()
    headers = ['Station', 'Latitude', 'Longitude', 'Timezone']
    for i in range(1, max_pairs + 1):
        headers.extend([f'Time_{i}', f'Level_{i}'])

    for header in headers:
        cell = TableCell()
        cell.addElement(P(text=header))
        header_row.addElement(cell)
    table.addElement(header_row)

    # Add data rows
    for station in stations:
        row = TableRow()

        # Station name
        cell = TableCell()
        cell.addElement(P(text=station['name']))
        row.addElement(cell)

        # Latitude
        cell = TableCell()
        cell.addElement(P(text=station['latitude']))
        row.addElement(cell)

        # Longitude
        cell = TableCell()
        cell.addElement(P(text=station['longitude']))
        row.addElement(cell)

        # Timezone
        cell = TableCell()
        cell.addElement(P(text=station.get('timezone', '')))
        row.addElement(cell)

        # Time/Level pairs
        preds = predictions_data.get(station['name'], [])
        for pred in preds:
            # Time
            cell = TableCell()
            cell.addElement(P(text=pred['time']))
            row.addElement(cell)

            # Level with comma as decimal separator
            level_str = f"{pred['level']:.2f}".replace('.', ',')
            cell = TableCell()
            cell.addElement(P(text=level_str))
            row.addElement(cell)

        # Fill remaining empty cells if needed
        remaining = max_pairs - len(preds)
        for _ in range(remaining * 2):
            cell = TableCell()
            row.addElement(cell)

        table.addElement(row)

    doc.spreadsheet.addElement(table)
    doc.save(output_file)
    print(f"Saved to {output_file}")

def main():
    harmonics_file = '/home/oliver/harmonics_working/harmonics_germany_2026-01-23.txt'
    output_file = '/home/oliver/harmonics_working_help/tide_prediction_pegelonline_2026-01-27.ods'

    # Date range
    start_date = datetime(2026, 1, 27)
    end_date = datetime(2026, 1, 30)

    print("Extracting stations...")
    stations = extract_stations(harmonics_file)
    print(f"Found {len(stations)} stations")

    print("\nGenerating tide predictions...")
    predictions_data = {}

    for i, station in enumerate(stations):
        print(f"  [{i+1}/{len(stations)}] {station['name']}")
        preds = get_tide_predictions(station['name'], start_date, end_date)
        predictions_data[station['name']] = preds

    print(f"\nCreating ODS file...")
    create_ods_file(stations, predictions_data, output_file)
    print("Done!")

if __name__ == '__main__':
    main()
