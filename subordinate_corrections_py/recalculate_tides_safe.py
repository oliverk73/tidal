#!/usr/bin/env python3
"""
Recalculate tides for corrected stations using odfpy for safe ODS manipulation.
"""

import subprocess
import re
from datetime import datetime, timedelta
from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.text import P

def get_cell_value(cell):
    """Extract value from cell."""
    # Try text content first
    ps = cell.getElementsByType(P)
    if ps:
        text = str(ps[0])
        if text:
            return text
    # Try value attribute
    val = cell.getAttribute('value')
    if val:
        return str(val)
    return ''

def set_cell_value(cell, value):
    """Set cell value safely."""
    # Remove existing text
    for p in cell.getElementsByType(P):
        cell.removeChild(p)
    # Add new text
    p = P()
    p.addText(str(value))
    cell.addElement(p)
    # Update value attribute if it's a number
    try:
        float_val = float(str(value).replace(',', '.'))
        cell.setAttribute('value', str(float_val))
        cell.setAttribute('valuetype', 'float')
    except (ValueError, TypeError):
        pass

def get_row_cells_expanded(row):
    """Get all cells from a row, expanding repeated cells."""
    cells = []
    for cell in row.getElementsByType(TableCell):
        repeat = cell.getAttribute('numbercolumnsrepeated')
        repeat = int(repeat) if repeat else 1
        # For repeated cells, only add the actual cell once for modification
        # but track positions
        cells.append({'cell': cell, 'repeat': repeat})
    return cells

def get_cell_at_index(row_cells, index):
    """Get the actual cell object at a given column index."""
    pos = 0
    for item in row_cells:
        if pos + item['repeat'] > index:
            return item['cell']
        pos += item['repeat']
    return None

def parse_tide_output(output):
    """Parse tide command output."""
    events = []
    for line in output.split('\n'):
        match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(\S+)\s+([\d.]+)\s+(\w+)\s+(High|Low)\s+Tide', line)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            height = float(match.group(4))
            unit = match.group(5)
            tide_type = match.group(6)

            dt_str = f"{date_str} {time_str}"
            dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")

            events.append({
                'datetime': dt,
                'height': height,
                'unit': unit,
                'type': tide_type
            })
    return events

def get_reference_tides(ref_name, target_date):
    """Get tide predictions from xtide."""
    start_dt = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=1)
    end_dt = datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=2)

    try:
        result = subprocess.run(
            ['tide', '-l', ref_name,
             '-b', start_dt.strftime("%Y-%m-%d 00:00"),
             '-e', end_dt.strftime("%Y-%m-%d 00:00"),
             '-m', 'p'],
            capture_output=True, text=True, timeout=60
        )
        events = parse_tide_output(result.stdout + result.stderr)
        unit = events[0]['unit'] if events else 'meters'
        return events, unit
    except Exception as e:
        print(f"Error: {e}")
        return [], 'meters'

def apply_corrections(ref_events, hmin, hmpy, hoff, lmin, lmpy, loff):
    """Apply subordinate station corrections."""
    corrected = []
    for event in ref_events:
        new_event = event.copy()
        if event['type'] == 'High':
            new_event['datetime'] = event['datetime'] + timedelta(minutes=hmin)
            new_event['height'] = event['height'] * hmpy + hoff
        else:
            new_event['datetime'] = event['datetime'] + timedelta(minutes=lmin)
            new_event['height'] = event['height'] * lmpy + loff
        corrected.append(new_event)
    return corrected

def select_events_for_date(events, target_date):
    """Select tide events for the target date."""
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    day_events = [e for e in events
                  if target_dt <= e['datetime'] < target_dt + timedelta(days=1)]
    day_events.sort(key=lambda x: x['datetime'])
    return day_events[:5]

def main():
    input_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_no_1111.ods'
    backup_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_no_1111.ods.backup_before_fix'
    output_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_no_1111_recalc.ods'
    target_date = "2026-01-15"

    print("Loading current file...")
    doc = load(input_file)

    print("Loading backup file to identify changes...")
    doc_backup = load(backup_file)

    # Find corrected rows by comparing values
    corrected_rows = []

    for table in doc.getElementsByType(Table):
        table_backup = doc_backup.getElementsByType(Table)[0]
        rows = table.getElementsByType(TableRow)
        rows_backup = table_backup.getElementsByType(TableRow)

        print(f"Comparing {len(rows)} rows...")

        for row_idx, (row, row_bak) in enumerate(zip(rows, rows_backup)):
            if row_idx == 0:  # Skip header
                continue

            cells = get_row_cells_expanded(row)
            cells_bak = get_row_cells_expanded(row_bak)

            # Get values at correction columns (6, 8, 9, 11)
            def get_val_at(cells_list, idx):
                cell = get_cell_at_index(cells_list, idx)
                return get_cell_value(cell) if cell else ''

            # Check if any correction value changed
            changed = False
            for col in [6, 8, 9, 11]:  # hmin, hoff, lmin, loff
                val_new = get_val_at(cells, col)
                val_old = get_val_at(cells_bak, col)
                if val_new != val_old:
                    changed = True
                    break

            if changed:
                corrected_rows.append(row_idx)

    print(f"Found {len(corrected_rows)} corrected rows")

    # Get unique reference stations
    ref_cache = {}
    stations_data = []

    for table in doc.getElementsByType(Table):
        rows = table.getElementsByType(TableRow)

        for row_idx in corrected_rows:
            row = rows[row_idx]
            cells = get_row_cells_expanded(row)

            def get_val(idx):
                cell = get_cell_at_index(cells, idx)
                return get_cell_value(cell) if cell else ''

            station_name = get_val(4)
            ref_name = get_val(16)

            try:
                hmin = float(get_val(6).replace(',', '.') or '0')
                hmpy = float(get_val(7).replace(',', '.') or '1')
                hoff = float(get_val(8).replace(',', '.') or '0')
                lmin = float(get_val(9).replace(',', '.') or '0')
                lmpy = float(get_val(10).replace(',', '.') or '1')
                loff = float(get_val(11).replace(',', '.') or '0')
            except ValueError:
                print(f"  Skipping {station_name}: invalid values")
                continue

            stations_data.append({
                'row_idx': row_idx,
                'name': station_name,
                'ref_name': ref_name,
                'hmin': hmin, 'hmpy': hmpy, 'hoff': hoff,
                'lmin': lmin, 'lmpy': lmpy, 'loff': loff
            })

            if ref_name and ref_name not in ref_cache:
                ref_cache[ref_name] = None

    print(f"\nFetching tides for {len(ref_cache)} reference stations...")
    for i, ref_name in enumerate(ref_cache.keys()):
        events, unit = get_reference_tides(ref_name, target_date)
        ref_cache[ref_name] = {'events': events, 'unit': unit}
        print(f"  [{i+1}/{len(ref_cache)}] {ref_name}: {len(events)} events")

    print(f"\nUpdating {len(stations_data)} stations...")

    for table in doc.getElementsByType(Table):
        rows = table.getElementsByType(TableRow)

        for station in stations_data:
            row_idx = station['row_idx']
            row = rows[row_idx]
            cells = get_row_cells_expanded(row)

            ref_data = ref_cache.get(station['ref_name'], {'events': [], 'unit': 'meters'})

            if not ref_data['events']:
                print(f"  No data for {station['name']}")
                continue

            # Apply corrections
            corrected = apply_corrections(
                ref_data['events'],
                station['hmin'], station['hmpy'], station['hoff'],
                station['lmin'], station['lmpy'], station['loff']
            )

            selected = select_events_for_date(corrected, target_date)

            # Update cells (time_1=20, level_1=21, time_2=22, ...)
            for j in range(5):
                time_col = 20 + j * 2
                level_col = 21 + j * 2

                time_cell = get_cell_at_index(cells, time_col)
                level_cell = get_cell_at_index(cells, level_col)

                if j < len(selected) and selected[j].get('datetime'):
                    time_str = selected[j]['datetime'].strftime("%H:%M")
                    level_str = f"{selected[j]['height']:.2f}"
                else:
                    time_str = ''
                    level_str = ''

                if time_cell:
                    set_cell_value(time_cell, time_str)
                if level_cell:
                    set_cell_value(level_cell, level_str)

            # Update unit column (17)
            unit_cell = get_cell_at_index(cells, 17)
            if unit_cell:
                set_cell_value(unit_cell, ref_data['unit'])

            print(f"  Updated: {station['name']}")

    print(f"\nSaving to {output_file}...")
    doc.save(output_file)
    print("Done!")

if __name__ == '__main__':
    main()
