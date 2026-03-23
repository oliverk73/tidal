#!/usr/bin/env python3
"""
Generate tide predictions for all stations from /usr/share/xtide harmonics
and export to ODS file.
"""

import subprocess
import re
from datetime import datetime
import os

try:
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell
    from odf.text import P
except ImportError:
    print("Installing odfpy...")
    subprocess.run(['pip', 'install', 'odfpy'], check=True)
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell
    from odf.text import P


def run_tide_command(args):
    """Run tide command and return output."""
    result = subprocess.run(['tide'] + args, capture_output=True, text=True)
    return result.stdout


def get_all_stations():
    """Get list of all available stations."""
    output = run_tide_command(['-m', 'l'])
    stations = []

    for line in output.strip().split('\n'):
        # Skip header lines
        if line.startswith('Indexing') or line.startswith('Location list') or not line.strip():
            continue

        # Extract station name (everything before "Ref" or "Sub")
        match = re.match(r'^(.+?)\s+(Ref|Sub)\s+(.+)$', line.strip())
        if match:
            name = match.group(1).strip()
            station_type = match.group(2)
            coords = match.group(3).strip()
            stations.append((name, station_type, coords))

    return stations


def get_station_info(station_name):
    """Get detailed info about a station."""
    output = run_tide_command(['-l', station_name, '-m', 'a'])

    info = {
        'name': station_name,
        'latitude': None,
        'longitude': None,
        'timezone': None,
        'units': None,
        'type': None
    }

    for line in output.strip().split('\n'):
        if line.startswith('Indexing'):
            continue

        if 'Coordinates' in line:
            # Parse: Coordinates   48.3786° N, 4.4867° W
            coords_match = re.search(r'([\d.]+)°\s*([NS]),?\s*([\d.]+)°\s*([EW])', line)
            if coords_match:
                lat = float(coords_match.group(1))
                if coords_match.group(2) == 'S':
                    lat = -lat
                lon = float(coords_match.group(3))
                if coords_match.group(4) == 'W':
                    lon = -lon
                info['latitude'] = lat
                info['longitude'] = lon

        elif 'Time zone' in line:
            # Parse: Time zone     :Europe/Paris
            tz_match = re.search(r'Time zone\s+:?(.+)', line)
            if tz_match:
                info['timezone'] = tz_match.group(1).strip()

        elif 'Native units' in line:
            # Parse: Native units  meters
            units_match = re.search(r'Native units\s+(\w+)', line)
            if units_match:
                info['units'] = units_match.group(1).strip()

        elif 'Type' in line and 'station' in line:
            # Parse: Type          Reference station, tide
            type_match = re.search(r'Type\s+(.+)', line)
            if type_match:
                info['type'] = type_match.group(1).strip()

    return info


def get_tide_predictions(station_name, start_date, end_date):
    """Get high/low tide predictions for a station."""
    output = run_tide_command([
        '-l', station_name,
        '-b', start_date,
        '-e', end_date,
        '-m', 'p'
    ])

    tides = []

    for line in output.strip().split('\n'):
        if line.startswith('Indexing') or not line.strip():
            continue
        if station_name in line and '°' in line:
            # This is the header with coordinates
            continue

        # Parse tide events: 2026-01-22  1:01 AM CET   1.59 meters  Low Tide
        if 'High Tide' in line or 'Low Tide' in line:
            # Extract datetime and level
            match = re.match(
                r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s*([AP]M)\s+(\w+)\s+([\d.]+)\s+(\w+)\s+(High|Low)\s+Tide',
                line.strip()
            )
            if match:
                date_str = match.group(1)
                time_str = match.group(2)
                am_pm = match.group(3)
                tz_abbr = match.group(4)
                level = float(match.group(5))
                unit = match.group(6)
                tide_type = match.group(7)

                # Convert to 24-hour format
                time_obj = datetime.strptime(f"{time_str} {am_pm}", "%I:%M %p")
                time_24h = time_obj.strftime("%H:%M")

                tides.append({
                    'time': time_24h,
                    'level': level,
                    'type': tide_type,
                    'timezone': tz_abbr
                })

    return tides


def count_constituents(station_name, harmonics_file):
    """Count the number of constituents for a station in the harmonics file."""
    # This is a simplified approach - would need proper TCD parsing for accuracy
    # For now, return None or a default value
    return None


def create_ods_file(stations_data, output_file):
    """Create ODS file with tide predictions."""
    doc = OpenDocumentSpreadsheet()
    table = Table(name="Tide Predictions")

    # Create header row
    headers = [
        'Station', 'Latitude', 'Longitude', 'Timezone', '# Constituents', 'Level Unit'
    ]

    # Find max number of tide events
    max_tides = max(len(s.get('tides', [])) for s in stations_data) if stations_data else 0

    for i in range(1, max_tides + 1):
        headers.extend([f'time_{i}', f'level_{i}'])

    header_row = TableRow()
    for header in headers:
        cell = TableCell()
        cell.addElement(P(text=str(header)))
        header_row.addElement(cell)
    table.addElement(header_row)

    # Add data rows
    for station_data in stations_data:
        row = TableRow()

        # Station name
        cell = TableCell()
        cell.addElement(P(text=str(station_data.get('name', ''))))
        row.addElement(cell)

        # Latitude
        cell = TableCell()
        lat = station_data.get('latitude', '')
        cell.addElement(P(text=str(lat) if lat is not None else ''))
        row.addElement(cell)

        # Longitude
        cell = TableCell()
        lon = station_data.get('longitude', '')
        cell.addElement(P(text=str(lon) if lon is not None else ''))
        row.addElement(cell)

        # Timezone
        cell = TableCell()
        cell.addElement(P(text=str(station_data.get('timezone', ''))))
        row.addElement(cell)

        # Constituents
        cell = TableCell()
        constituents = station_data.get('constituents', '')
        cell.addElement(P(text=str(constituents) if constituents else ''))
        row.addElement(cell)

        # Level Unit
        cell = TableCell()
        cell.addElement(P(text=str(station_data.get('units', ''))))
        row.addElement(cell)

        # Add tide events
        tides = station_data.get('tides', [])
        for tide in tides:
            # Time (24-hour format, no date)
            cell = TableCell()
            cell.addElement(P(text=str(tide.get('time', ''))))
            row.addElement(cell)

            # Level
            cell = TableCell()
            cell.addElement(P(text=str(tide.get('level', ''))))
            row.addElement(cell)

        # Fill remaining columns with empty cells
        for _ in range(max_tides - len(tides)):
            cell = TableCell()
            cell.addElement(P(text=''))
            row.addElement(cell)
            cell = TableCell()
            cell.addElement(P(text=''))
            row.addElement(cell)

        table.addElement(row)

    doc.spreadsheet.addElement(table)
    doc.save(output_file)
    print(f"Saved to {output_file}")


def main():
    start_date = "2026-01-22 00:00"
    end_date = "2026-01-26 00:00"  # 25. Januar bis Ende des Tages
    output_file = "/home/oliver/harmonics/help/tide_prediction_pierre_lavergne_v10.ods"

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    print("Getting list of all stations...")
    stations = get_all_stations()
    print(f"Found {len(stations)} stations")

    stations_data = []

    for i, (name, station_type, coords) in enumerate(stations):
        print(f"Processing {i+1}/{len(stations)}: {name}")

        # Get station info
        info = get_station_info(name)

        # Get tide predictions
        tides = get_tide_predictions(name, start_date, end_date)

        station_data = {
            'name': name,
            'latitude': info['latitude'],
            'longitude': info['longitude'],
            'timezone': info['timezone'],
            'units': info['units'],
            'constituents': None,  # Would need TCD parsing
            'tides': tides
        }

        stations_data.append(station_data)

    print(f"\nCreating ODS file with {len(stations_data)} stations...")
    create_ods_file(stations_data, output_file)
    print("Done!")


if __name__ == "__main__":
    main()
