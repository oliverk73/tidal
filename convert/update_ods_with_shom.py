#!/usr/bin/env python3
"""
Update ODS file with SHOM comparison data for Ajaccio and Primel.
"""

import subprocess
import json
import re
from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.text import P, A


def fetch_shom_station_info(harbor_name):
    """Fetch station info from SHOM WFS service."""
    # We'll use the cached data since we already know it
    station_data = {
        'AJACCIO': {
            'toponyme': 'Ajaccio (SHOM)',
            'lat': 41.922703,
            'lon': 8.762839,
            'timezone': 'Europe/Paris',
            'units': 'meters'
        },
        'PRIMEL': {
            'toponyme': 'Anse de Primel (SHOM)',
            'lat': 48.716667,
            'lon': -3.833333,
            'timezone': 'Europe/Paris',
            'units': 'meters'
        }
    }
    return station_data.get(harbor_name.upper())


def fetch_shom_tides(harbor_name, date="2026-01-22", duration=4):
    """Fetch tide predictions from SHOM API."""
    url = f"https://services.data.shom.fr/b2q8lrcdl4s04cbabsj4nhcb/hdm/spm/hlt?harborName={harbor_name}&date={date}&utc=standard&correlation=0&duration={duration}"

    result = subprocess.run([
        'curl', '-s', url,
        '-H', 'Accept: application/json',
        '-H', 'Referer: https://maree.shom.fr/',
        '-H', 'Origin: https://maree.shom.fr'
    ], capture_output=True, text=True)

    try:
        data = json.loads(result.stdout)
        return data
    except json.JSONDecodeError:
        print(f"Error fetching tides for {harbor_name}: {result.stdout}")
        return None


def extract_tides_flat(tide_data):
    """Extract tide times and levels as flat list."""
    tides = []
    for date in sorted(tide_data.keys()):
        for entry in tide_data[date]:
            tide_type, time_str, level, _ = entry
            if time_str != "--:--" and level != "---":
                tides.append({
                    'time': time_str,
                    'level': level
                })
    return tides


def get_cell_text(cell):
    """Extract text from a cell, including links."""
    text = ''
    for p in cell.getElementsByType(P):
        for a in p.getElementsByType(A):
            href = a.getAttribute('href')
            if href:
                text += href
        if p.firstChild and not p.getElementsByType(A):
            try:
                text += str(p.firstChild.data) if hasattr(p.firstChild, 'data') else str(p.firstChild)
            except:
                text += str(p.firstChild)
    return text


def update_ods_file(input_file, output_file):
    """Update ODS file with SHOM data."""
    doc = load(input_file)
    table = doc.spreadsheet.getElementsByType(Table)[0]
    rows = list(table.getElementsByType(TableRow))

    # Find rows with SHOM URLs and the empty rows after them
    shom_data = {}

    for i, row in enumerate(rows):
        cells = list(row.getElementsByType(TableCell))
        if cells:
            first_cell_text = get_cell_text(cells[0])

            # Check if this row has a SHOM URL
            if 'maree.shom.fr' in first_cell_text:
                # Extract harbor name from URL
                match = re.search(r'/harbor/([^/]+)/', first_cell_text)
                if match:
                    harbor_name = match.group(1)
                    shom_data[i] = harbor_name
                    print(f"Found URL row {i}: {harbor_name}")

    # Fetch data and update the URL rows
    for row_idx, harbor_name in shom_data.items():
        print(f"Fetching data for {harbor_name}...")

        # Get station info
        station_info = fetch_shom_station_info(harbor_name)

        # Get tide predictions
        tide_data = fetch_shom_tides(harbor_name)

        if station_info and tide_data:
            tides = extract_tides_flat(tide_data)

            # Get the row to update (the URL row itself)
            row = rows[row_idx]
            cells = list(row.getElementsByType(TableCell))

            # Clear existing cells and add new data
            # Remove old cells
            for cell in cells:
                row.removeChild(cell)

            # Add new cells with SHOM data
            # URL (keep empty or the URL)
            cell = TableCell()
            cell.addElement(P(text="SHOM"))
            row.addElement(cell)

            # Station name
            cell = TableCell()
            cell.addElement(P(text=station_info['toponyme']))
            row.addElement(cell)

            # Latitude
            cell = TableCell()
            cell.addElement(P(text=str(station_info['lat'])))
            row.addElement(cell)

            # Longitude
            cell = TableCell()
            cell.addElement(P(text=str(station_info['lon'])))
            row.addElement(cell)

            # Timezone
            cell = TableCell()
            cell.addElement(P(text=station_info['timezone']))
            row.addElement(cell)

            # Constituents (empty for SHOM)
            cell = TableCell()
            cell.addElement(P(text=""))
            row.addElement(cell)

            # Units
            cell = TableCell()
            cell.addElement(P(text=station_info['units']))
            row.addElement(cell)

            # Add tide times and levels
            for tide in tides:
                cell = TableCell()
                cell.addElement(P(text=tide['time']))
                row.addElement(cell)

                cell = TableCell()
                cell.addElement(P(text=tide['level']))
                row.addElement(cell)

            print(f"  Added {len(tides)} tide events for {harbor_name}")

    # Save the updated document
    doc.save(output_file)
    print(f"\nSaved to {output_file}")


if __name__ == "__main__":
    input_file = "/home/oliver/harmonics/help/tide_prediction_pierre_lavergne_v10.ods"
    output_file = "/home/oliver/harmonics/help/tide_prediction_pierre_lavergne_v10.ods"

    update_ods_file(input_file, output_file)
