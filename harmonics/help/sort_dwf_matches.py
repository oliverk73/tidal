#!/usr/bin/env python3
"""
Reorganize ODS file so DWF stations appear directly below their Pegelonline matches.
"""

from odf.opendocument import load, OpenDocumentSpreadsheet
from odf.table import Table, TableRow, TableCell
from odf.text import P
import copy

def get_cell_text(cell):
    """Extract text from a cell."""
    p = cell.getElementsByType(P)
    if p:
        return str(p[0])
    return ""

def clone_row(row):
    """Create a deep copy of a row."""
    new_row = TableRow()
    for cell in row.getElementsByType(TableCell):
        new_cell = TableCell()
        p = cell.getElementsByType(P)
        if p:
            new_cell.addElement(P(text=str(p[0])))
        new_row.addElement(new_cell)
    return new_row

def main():
    ods_file = '/home/oliver/harmonics_working_help/tide_prediction_pegelonline_2026-01-27.ods'

    print("Loading ODS file...")
    doc = load(ods_file)
    table = doc.spreadsheet.getElementsByType(Table)[0]
    rows = table.getElementsByType(TableRow)

    # Collect all row data
    all_rows = []
    header_row = None
    pegelonline_rows = []
    dwf_rows = []

    for i, row in enumerate(rows):
        cells = row.getElementsByType(TableCell)
        if not cells:
            continue

        station_name = get_cell_text(cells[0])

        if i == 0:  # Header
            header_row = row
        elif '[DWF]' in station_name:
            dwf_rows.append({
                'row': row,
                'name': station_name,
                'lat': get_cell_text(cells[1]) if len(cells) > 1 else '',
                'lon': get_cell_text(cells[2]) if len(cells) > 2 else ''
            })
        else:
            pegelonline_rows.append({
                'row': row,
                'name': station_name,
                'lat': get_cell_text(cells[1]) if len(cells) > 1 else '',
                'lon': get_cell_text(cells[2]) if len(cells) > 2 else ''
            })

    print(f"Found {len(pegelonline_rows)} Pegelonline stations")
    print(f"Found {len(dwf_rows)} DWF stations")

    # Define the matches (from previous script output)
    matches = {
        'Büsum (Schleuse), Germany': 'Büsum (Schleuse), Germany [DWF]',
        'Bremerhaven (Alter Leuchtturm), Germany': 'Bremerhaven (Alter Leuchtturm), Germany [DWF]',
        'Oslebshausen (Weser), Germany': 'Bremen, Oslebshausen, Germany [DWF]',
        'Brunsbüttel (Elbe), Germany': 'Brunsbüttel, Germany [DWF]',
        'Borkum (Fischerbalje), Germany': 'Borkum (Fischerbalje), Germany [DWF]',
        'Cuxhaven-Steubenhöft (Elbe), Germany': 'Cuxhaven (Steubenhöft), Germany [DWF]',
        'Emden (Ems, Große Seeschleuse), Germany': 'Emden (Neue Seeschleuse), Germany [DWF]',
        'Cranz (Este-Sperrwerk), Germany': 'Hamburg (St. Pauli), Germany [DWF]',
        'Helgoland (Binnenhafen), Germany': 'Helgoland, Germany [DWF]',
        'Husum (Schleuse), Germany': 'Husum (Speerwerk), Germany [DWF]',
        'Norderney (Riffgat), Germany': 'Norderney (Riffgat), Germany [DWF]',
        'Wilhelmshaven (Alter Vorhafen), Germany': 'Wilhelmshaven (Alter Vorhafen), Germany [DWF]',
    }

    # Build a lookup for DWF rows by name
    dwf_by_name = {d['name']: d for d in dwf_rows}

    # Create new table structure
    print("\nReorganizing rows...")
    new_doc = OpenDocumentSpreadsheet()
    new_table = Table(name="Tide Predictions")

    # Add header
    new_table.addElement(clone_row(header_row))

    # Add Pegelonline rows with DWF matches inserted below
    matched_dwf = set()
    for pegel in pegelonline_rows:
        # Add Pegelonline row
        new_table.addElement(clone_row(pegel['row']))

        # Check if there's a matching DWF station
        pegel_name = pegel['name']
        if pegel_name in matches:
            dwf_name = matches[pegel_name]
            if dwf_name in dwf_by_name:
                # Add DWF row directly below
                new_table.addElement(clone_row(dwf_by_name[dwf_name]['row']))
                matched_dwf.add(dwf_name)
                print(f"  Inserted {dwf_name} below {pegel_name}")

    # Add any unmatched DWF rows at the end (shouldn't happen with our data)
    for dwf in dwf_rows:
        if dwf['name'] not in matched_dwf:
            new_table.addElement(clone_row(dwf['row']))
            print(f"  Added unmatched: {dwf['name']}")

    new_doc.spreadsheet.addElement(new_table)

    # Save
    print(f"\nSaving to {ods_file}...")
    new_doc.save(ods_file)

    # Verify
    doc2 = load(ods_file)
    table2 = doc2.spreadsheet.getElementsByType(Table)[0]
    rows2 = table2.getElementsByType(TableRow)
    print(f"New file has {len(rows2)} rows")

    print("\nDone!")

if __name__ == '__main__':
    main()
