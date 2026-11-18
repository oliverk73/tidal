#!/usr/bin/env python3
"""
Fix 1111 and 111.1 placeholder values in ODS files.

Rules:
1. If lmin=1111 and hmin!=1111: lmin = hmin
2. If hmin=1111 and lmin!=1111: hmin = lmin
3. If both hmin=1111 AND lmin=1111: both = 0
4. If loff=111.1 and hoff!=111.1: loff = hoff
5. If hoff=111.1 and loff!=111.1: hoff = loff
6. If both hoff=111.1 AND loff=111.1: both = 0
"""

from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.text import P
import sys

def get_cell_value(cell):
    """Extract text value from a cell."""
    ps = cell.getElementsByType(P)
    if ps:
        return str(ps[0])
    return ""

def set_cell_value(cell, value):
    """Set text value in a cell."""
    # Remove existing content
    for p in cell.getElementsByType(P):
        cell.removeChild(p)
    # Add new content
    p = P()
    p.addText(str(value))
    cell.addElement(p)

def get_row_cells(row):
    """Get all cells from a row, handling repeated cells."""
    cells = []
    for cell in row.getElementsByType(TableCell):
        repeat = cell.getAttribute("numbercolumnsrepeated")
        repeat = int(repeat) if repeat else 1
        for _ in range(repeat):
            cells.append(cell)
    return cells

def fix_ods_file(input_file, output_file, hmin_col, hoff_col, lmin_col, loff_col):
    """Fix 1111 and 111.1 values in an ODS file."""
    doc = load(input_file)
    changes = []

    for table in doc.getElementsByType(Table):
        rows = table.getElementsByType(TableRow)

        for row_idx, row in enumerate(rows):
            if row_idx == 0:  # Skip header
                continue

            cells = get_row_cells(row)
            if len(cells) <= max(hmin_col, hoff_col, lmin_col, loff_col):
                continue

            try:
                hmin_val = get_cell_value(cells[hmin_col])
                hoff_val = get_cell_value(cells[hoff_col])
                lmin_val = get_cell_value(cells[lmin_col])
                loff_val = get_cell_value(cells[loff_col])

                if not hmin_val or not lmin_val:
                    continue

                hmin = int(float(hmin_val))
                lmin = int(float(lmin_val))
                hoff = float(hoff_val.replace(',', '.')) if hoff_val else 0
                loff = float(loff_val.replace(',', '.')) if loff_val else 0

            except (ValueError, IndexError):
                continue

            modified = False
            original = {'hmin': hmin, 'lmin': lmin, 'hoff': hoff, 'loff': loff}

            # Fix minutes
            if hmin == 1111 and lmin == 1111:
                set_cell_value(cells[hmin_col], '0')
                set_cell_value(cells[lmin_col], '0')
                modified = True
            elif lmin == 1111:
                set_cell_value(cells[lmin_col], str(hmin))
                modified = True
            elif hmin == 1111:
                set_cell_value(cells[hmin_col], str(lmin))
                modified = True

            # Fix offsets (check both with . and , as decimal separator)
            hoff_is_111 = abs(hoff - 111.1) < 0.1
            loff_is_111 = abs(loff - 111.1) < 0.1

            if hoff_is_111 and loff_is_111:
                set_cell_value(cells[hoff_col], '0')
                set_cell_value(cells[loff_col], '0')
                modified = True
            elif loff_is_111:
                set_cell_value(cells[loff_col], str(hoff))
                modified = True
            elif hoff_is_111:
                set_cell_value(cells[hoff_col], str(loff))
                modified = True

            if modified:
                # Try to get station name
                station_name = get_cell_value(cells[4]) if len(cells) > 4 else f"Row {row_idx+1}"
                changes.append((row_idx+1, station_name, original))

    doc.save(output_file)
    return changes

if __name__ == '__main__':
    # Process subordinate_stations_mapped.ods
    # Columns: land;region;longitude;latitude;station_name;timezone;hmin;hmpy;hoff;lmin;lmpy;loff
    #          0    1      2         3        4            5        6    7    8    9    10   11
    print("=" * 60)
    print("Processing subordinate_stations_mapped.ods")
    print("=" * 60)

    changes = fix_ods_file(
        '/home/oliver/subordinate_corrections/subordinate_stations_mapped.ods',
        '/home/oliver/subordinate_corrections/subordinate_stations_mapped_fixed.ods',
        hmin_col=6, hoff_col=8, lmin_col=9, loff_col=11
    )
    print(f"Total changes: {len(changes)}")
    for row, name, orig in changes[:10]:
        print(f"  Row {row}: {name}")
    if len(changes) > 10:
        print(f"  ... and {len(changes)-10} more")

    # Process subordinate_stations_tide_prediction3.ods
    # Same column structure: hmin=6, hoff=8, lmin=9, loff=11
    print("\n" + "=" * 60)
    print("Processing subordinate_stations_tide_prediction3.ods")
    print("=" * 60)

    changes = fix_ods_file(
        '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3.ods',
        '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_fixed.ods',
        hmin_col=6, hoff_col=8, lmin_col=9, loff_col=11
    )
    print(f"Total changes: {len(changes)}")
    for row, name, orig in changes[:10]:
        print(f"  Row {row}: {name}")
    if len(changes) > 10:
        print(f"  ... and {len(changes)-10} more")
