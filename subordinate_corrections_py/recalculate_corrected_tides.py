#!/usr/bin/env python3
"""
Recalculate tides only for stations where corrections were applied.
"""

import zipfile
import re
import subprocess
from datetime import datetime, timedelta

def parse_tide_output(output):
    """Parse tide command output and extract high/low tide events."""
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
    """Get tide predictions for a reference station from xtide."""
    start_dt = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=1)
    end_dt = datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=2)

    start_date = start_dt.strftime("%Y-%m-%d 00:00")
    end_date = end_dt.strftime("%Y-%m-%d 00:00")

    try:
        result = subprocess.run(
            ['tide', '-l', ref_name, '-b', start_date, '-e', end_date, '-m', 'p'],
            capture_output=True,
            text=True,
            timeout=60
        )
        output = result.stdout + result.stderr
        events = parse_tide_output(output)
        unit = events[0].get('unit', 'meters') if events else 'meters'
        return events, unit
    except Exception as e:
        print(f"Error getting tides for {ref_name}: {e}")
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
    """Select up to 5 tide events for the target date."""
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    target_start = target_dt
    target_end = target_dt + timedelta(days=1)

    day_events = [e for e in events if target_start <= e['datetime'] < target_end]
    day_events.sort(key=lambda x: x['datetime'])

    # Return up to 5 events
    return day_events[:5]

def extract_ods_data(filepath):
    """Extract data from ODS file."""
    with zipfile.ZipFile(filepath, 'r') as z:
        content = z.read('content.xml').decode('utf-8')
        other_files = {}
        for name in z.namelist():
            if name != 'content.xml':
                other_files[name] = z.read(name)
    return content, other_files

def parse_cell_value(cell_xml):
    """Parse value from a cell XML."""
    value_match = re.search(r'office:value="([^"]*)"', cell_xml)
    if value_match:
        return value_match.group(1)
    text_match = re.search(r'<text:p>([^<]*)</text:p>', cell_xml)
    if text_match:
        return text_match.group(1)
    return ''

def identify_corrected_rows(old_content, new_content):
    """Identify rows that were corrected by comparing old and new content."""
    # Find all rows in both files
    row_pattern = r'<table:table-row[^>]*>(.*?)</table:table-row>'

    old_rows = re.findall(row_pattern, old_content, re.DOTALL)
    new_rows = re.findall(row_pattern, new_content, re.DOTALL)

    corrected_indices = []

    for i, (old_row, new_row) in enumerate(zip(old_rows, new_rows)):
        if old_row != new_row:
            corrected_indices.append(i)

    return corrected_indices

def get_row_data(row_xml):
    """Extract cell data from a row."""
    cells = []
    for m in re.finditer(r'<table:table-cell([^>]*)>(.*?)</table:table-cell>', row_xml):
        attrs = m.group(1)
        content = m.group(2)

        repeat_match = re.search(r'table:number-columns-repeated="(\d+)"', attrs)
        repeat = int(repeat_match.group(1)) if repeat_match else 1

        value_match = re.search(r'office:value="([^"]*)"', attrs)
        value = value_match.group(1) if value_match else ''

        text_match = re.search(r'<text:p>([^<]*)</text:p>', content)
        text = text_match.group(1) if text_match else ''

        for _ in range(repeat):
            cells.append({'value': value, 'text': text, 'attrs': attrs, 'content': content, 'full': m.group(0)})

    return cells

def update_cell_value(row_xml, col_idx, new_value, cells):
    """Update a cell value in the row XML."""
    if col_idx >= len(cells):
        return row_xml

    cell = cells[col_idx]
    old_cell = cell['full']

    # Create new cell with updated value
    new_attrs = cell['attrs']
    if 'office:value=' in new_attrs:
        new_attrs = re.sub(r'office:value="[^"]*"', f'office:value="{new_value}"', new_attrs)
    else:
        new_attrs = new_attrs + f' office:value-type="string"'

    new_content = f'<text:p>{new_value}</text:p>'
    new_cell = f'<table:table-cell{new_attrs}>{new_content}</table:table-cell>'

    return row_xml.replace(old_cell, new_cell, 1)

def main():
    old_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_no_1111.ods.backup_before_fix'
    new_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_no_1111.ods'
    output_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_recalc.ods'
    target_date = "2026-01-15"

    print("Loading files...")
    old_content, _ = extract_ods_data(old_file)
    new_content, other_files = extract_ods_data(new_file)

    print("Identifying corrected rows...")
    corrected_indices = identify_corrected_rows(old_content, new_content)
    print(f"Found {len(corrected_indices)} corrected rows")

    # Parse all rows
    row_pattern = r'<table:table-row[^>]*>(.*?)</table:table-row>'
    rows = list(re.finditer(row_pattern, new_content, re.DOTALL))

    # Get reference stations for corrected rows
    ref_cache = {}
    stations_to_process = []

    print("Extracting station data...")
    for idx in corrected_indices:
        if idx == 0 or idx >= len(rows):  # Skip header
            continue

        row_xml = rows[idx].group(0)
        cells = get_row_data(row_xml)

        if len(cells) < 17:
            continue

        station_name = cells[4]['text'] or cells[4]['value']
        ref_name = cells[16]['text'] or cells[16]['value']

        try:
            hmin = float((cells[6]['value'] or cells[6]['text'] or '0').replace(',', '.'))
            hmpy = float((cells[7]['value'] or cells[7]['text'] or '1').replace(',', '.'))
            hoff = float((cells[8]['value'] or cells[8]['text'] or '0').replace(',', '.'))
            lmin = float((cells[9]['value'] or cells[9]['text'] or '0').replace(',', '.'))
            lmpy = float((cells[10]['value'] or cells[10]['text'] or '1').replace(',', '.'))
            loff = float((cells[11]['value'] or cells[11]['text'] or '0').replace(',', '.'))
        except ValueError as e:
            print(f"  Skipping {station_name}: invalid values")
            continue

        stations_to_process.append({
            'idx': idx,
            'name': station_name,
            'ref_name': ref_name,
            'hmin': hmin, 'hmpy': hmpy, 'hoff': hoff,
            'lmin': lmin, 'lmpy': lmpy, 'loff': loff
        })

        if ref_name and ref_name not in ref_cache:
            ref_cache[ref_name] = None  # Mark for fetching

    print(f"\nFetching reference station tides for {len(ref_cache)} stations...")
    for i, ref_name in enumerate(ref_cache.keys()):
        events, unit = get_reference_tides(ref_name, target_date)
        ref_cache[ref_name] = {'events': events, 'unit': unit}
        status = f"{len(events)} events" if events else "NO DATA"
        print(f"  [{i+1}/{len(ref_cache)}] {ref_name}: {status}")

    print(f"\nRecalculating tides for {len(stations_to_process)} stations...")

    updated_content = new_content
    success = 0
    errors = 0

    for station in stations_to_process:
        idx = station['idx']
        ref_name = station['ref_name']
        ref_data = ref_cache.get(ref_name, {'events': [], 'unit': 'meters'})

        if not ref_data['events']:
            print(f"  No reference data for {station['name']}")
            errors += 1
            continue

        # Apply corrections
        corrected = apply_corrections(
            ref_data['events'],
            station['hmin'], station['hmpy'], station['hoff'],
            station['lmin'], station['lmpy'], station['loff']
        )

        # Select events for target date
        selected = select_events_for_date(corrected, target_date)

        # Get current row
        row_match = list(re.finditer(row_pattern, updated_content, re.DOTALL))[idx]
        row_xml = row_match.group(0)
        cells = get_row_data(row_xml)

        # Update time and level columns (20-29 for time_1 to level_5)
        new_row = row_xml
        for j, event in enumerate(selected):
            time_col = 20 + j * 2  # time_1=20, time_2=22, time_3=24, time_4=26, time_5=28
            level_col = 21 + j * 2  # level_1=21, level_2=23, level_3=25, level_4=27, level_5=29

            if event and event.get('datetime'):
                time_str = event['datetime'].strftime("%H:%M")
                level_str = f"{event['height']:.2f}"
            else:
                time_str = ''
                level_str = ''

            cells = get_row_data(new_row)  # Re-parse after each update
            if time_col < len(cells):
                new_row = update_cell_value(new_row, time_col, time_str, cells)
            cells = get_row_data(new_row)
            if level_col < len(cells):
                new_row = update_cell_value(new_row, level_col, level_str, cells)

        # Also update level_unit column (17)
        cells = get_row_data(new_row)
        if 17 < len(cells):
            new_row = update_cell_value(new_row, 17, ref_data['unit'], cells)

        updated_content = updated_content.replace(row_xml, new_row, 1)
        success += 1
        print(f"  Updated: {station['name']} (hmin={station['hmin']}, lmin={station['lmin']}, hoff={station['hoff']}, loff={station['loff']})")

    print(f"\nWriting output file...")
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('content.xml', updated_content.encode('utf-8'))
        for name, data in other_files.items():
            z.writestr(name, data)

    print(f"\nDone! {success} stations updated, {errors} errors")
    print(f"Output: {output_file}")

if __name__ == '__main__':
    main()
