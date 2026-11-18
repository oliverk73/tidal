#!/usr/bin/env python3
"""
Recalculate tide predictions in ODS file based on corrected values from CSV.
Only updates cells where values actually change.
"""

import pyexcel_ods3 as ods
import csv
from datetime import datetime, timedelta
import copy

def time_str_to_minutes(time_str):
    """Convert HH:MM time string to minutes from midnight."""
    if not time_str or time_str == '':
        return None
    try:
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None

def minutes_to_time_str(minutes):
    """Convert minutes from midnight to HH:MM time string."""
    if minutes is None:
        return ''
    # Convert to int and handle day overflow
    minutes = int(round(minutes))
    minutes = minutes % (24 * 60)
    if minutes < 0:
        minutes += 24 * 60
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

def parse_correction_value(val):
    """Parse correction value, handling time format like -01:11."""
    if val is None or val == '':
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if ':' in val_str:
        # Time format like -01:11 means -71 minutes
        sign = -1 if val_str.startswith('-') else 1
        val_str = val_str.lstrip('-')
        parts = val_str.split(':')
        try:
            return sign * (int(parts[0]) * 60 + int(parts[1]))
        except (ValueError, IndexError):
            return None
    try:
        return float(val_str)
    except ValueError:
        return None

def calculate_subordinate_tide(ref_time, ref_level, time_offset, level_mpy, level_off):
    """Calculate subordinate station tide from reference station."""
    ref_minutes = time_str_to_minutes(ref_time)
    if ref_minutes is None:
        return None, None

    # Calculate new time
    new_minutes = ref_minutes + (time_offset if time_offset else 0)
    new_time = minutes_to_time_str(new_minutes)

    # Calculate new level
    try:
        ref_level_float = float(ref_level) if ref_level else 0
        mpy = float(level_mpy) if level_mpy else 1
        off = float(level_off) if level_off else 0
        new_level = round(ref_level_float * mpy + off, 2)
    except (ValueError, TypeError):
        new_level = ref_level

    return new_time, new_level

def main():
    # Load CSV with corrected values
    print("Loading CSV with corrected values...")
    csv_data = {}
    with open("/home/oliver/subordinate_corrections/subordinate_stations_mapped.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            station_name = row['station_name']
            csv_data[station_name] = {
                'hmin': row['hmin'],
                'hmpy': row['hmpy'],
                'hoff': row['hoff'],
                'lmin': row['lmin'],
                'lmpy': row['lmpy'],
                'loff': row['loff'],
                'ref_name': row['ref_name']
            }
    print(f"Loaded {len(csv_data)} stations from CSV")

    # Load ODS
    print("\nLoading ODS file...")
    ods_path = "/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction4.ods"
    ods_data = ods.get_data(ods_path)
    sheet = ods_data["Sheet1"]
    header = sheet[0]
    col_idx = {name: i for i, name in enumerate(header)}
    print(f"Loaded {len(sheet)} rows from ODS")

    # Build reference station data
    print("\nBuilding reference station data...")
    ref_stations = {}
    for i, row in enumerate(sheet[1:], start=1):
        if len(row) <= col_idx.get('station_name', 4):
            continue

        station_name = row[col_idx['station_name']] if col_idx['station_name'] < len(row) else None
        if not station_name:
            continue

        hmin = row[col_idx['hmin']] if col_idx['hmin'] < len(row) else None
        ref_name = row[col_idx['ref_name']] if col_idx['ref_name'] < len(row) else None

        # Reference station: has no hmin and no ref_name
        if (hmin == '' or hmin is None) and (ref_name == '' or ref_name is None):
            time_1 = row[col_idx['time_1']] if col_idx['time_1'] < len(row) else None
            level_1 = row[col_idx['level_1']] if col_idx['level_1'] < len(row) else None
            time_2 = row[col_idx['time_2']] if col_idx['time_2'] < len(row) else None
            level_2 = row[col_idx['level_2']] if col_idx['level_2'] < len(row) else None
            time_3 = row[col_idx['time_3']] if col_idx['time_3'] < len(row) else None
            level_3 = row[col_idx['level_3']] if col_idx['level_3'] < len(row) else None
            time_4 = row[col_idx['time_4']] if col_idx['time_4'] < len(row) else None
            level_4 = row[col_idx['level_4']] if col_idx['level_4'] < len(row) else None

            if time_1:
                ref_stations[station_name] = {
                    'row': i,
                    'times': [time_1, time_2, time_3, time_4],
                    'levels': [level_1, level_2, level_3, level_4]
                }
    print(f"Found {len(ref_stations)} reference stations")

    # Process subordinate stations and find changes
    print("\nProcessing subordinate stations...")
    changes = []

    for i, row in enumerate(sheet[1:], start=1):
        if len(row) <= col_idx.get('station_name', 4):
            continue

        station_name = row[col_idx['station_name']] if col_idx['station_name'] < len(row) else None
        if not station_name or station_name not in csv_data:
            continue

        ref_name = row[col_idx['ref_name']] if col_idx['ref_name'] < len(row) else None
        if not ref_name or ref_name not in ref_stations:
            continue

        # Get CSV correction values
        csv_row = csv_data[station_name]
        hmin = parse_correction_value(csv_row['hmin'])
        hmpy = parse_correction_value(csv_row['hmpy'])
        hoff = parse_correction_value(csv_row['hoff'])
        lmin = parse_correction_value(csv_row['lmin'])
        lmpy = parse_correction_value(csv_row['lmpy'])
        loff = parse_correction_value(csv_row['loff'])

        if hmin is None and lmin is None:
            continue

        # Get reference station data
        ref_data = ref_stations[ref_name]
        ref_times = ref_data['times']
        ref_levels = ref_data['levels']

        # Determine pattern (H-L-H-L or L-H-L-H)
        try:
            l1 = float(ref_levels[0]) if ref_levels[0] else 0
            l2 = float(ref_levels[1]) if ref_levels[1] else 0
            starts_with_high = l1 > l2
        except (ValueError, TypeError):
            starts_with_high = True

        # Calculate new values
        if starts_with_high:
            # Pattern: H-L-H-L
            new_time_1, new_level_1 = calculate_subordinate_tide(ref_times[0], ref_levels[0], hmin, hmpy, hoff)
            new_time_2, new_level_2 = calculate_subordinate_tide(ref_times[1], ref_levels[1], lmin, lmpy, loff)
            new_time_3, new_level_3 = calculate_subordinate_tide(ref_times[2], ref_levels[2], hmin, hmpy, hoff)
            new_time_4, new_level_4 = calculate_subordinate_tide(ref_times[3], ref_levels[3], lmin, lmpy, loff)
        else:
            # Pattern: L-H-L-H
            new_time_1, new_level_1 = calculate_subordinate_tide(ref_times[0], ref_levels[0], lmin, lmpy, loff)
            new_time_2, new_level_2 = calculate_subordinate_tide(ref_times[1], ref_levels[1], hmin, hmpy, hoff)
            new_time_3, new_level_3 = calculate_subordinate_tide(ref_times[2], ref_levels[2], lmin, lmpy, loff)
            new_time_4, new_level_4 = calculate_subordinate_tide(ref_times[3], ref_levels[3], hmin, hmpy, hoff)

        # Get current values
        cur_time_1 = row[col_idx['time_1']] if col_idx['time_1'] < len(row) else ''
        cur_level_1 = row[col_idx['level_1']] if col_idx['level_1'] < len(row) else ''
        cur_time_2 = row[col_idx['time_2']] if col_idx['time_2'] < len(row) else ''
        cur_level_2 = row[col_idx['level_2']] if col_idx['level_2'] < len(row) else ''
        cur_time_3 = row[col_idx['time_3']] if col_idx['time_3'] < len(row) else ''
        cur_level_3 = row[col_idx['level_3']] if col_idx['level_3'] < len(row) else ''
        cur_time_4 = row[col_idx['time_4']] if col_idx['time_4'] < len(row) else ''
        cur_level_4 = row[col_idx['level_4']] if col_idx['level_4'] < len(row) else ''

        # Check for changes and record them
        row_changes = []

        def values_differ(old, new):
            if old == '' and new == '':
                return False
            if old == '' or new == '':
                return True
            try:
                return abs(float(old) - float(new)) > 0.001
            except (ValueError, TypeError):
                return str(old) != str(new)

        if new_time_1 and values_differ(cur_time_1, new_time_1):
            row_changes.append(('time_1', col_idx['time_1'], cur_time_1, new_time_1))
        if new_level_1 is not None and values_differ(cur_level_1, new_level_1):
            row_changes.append(('level_1', col_idx['level_1'], cur_level_1, new_level_1))
        if new_time_2 and values_differ(cur_time_2, new_time_2):
            row_changes.append(('time_2', col_idx['time_2'], cur_time_2, new_time_2))
        if new_level_2 is not None and values_differ(cur_level_2, new_level_2):
            row_changes.append(('level_2', col_idx['level_2'], cur_level_2, new_level_2))
        if new_time_3 and values_differ(cur_time_3, new_time_3):
            row_changes.append(('time_3', col_idx['time_3'], cur_time_3, new_time_3))
        if new_level_3 is not None and values_differ(cur_level_3, new_level_3):
            row_changes.append(('level_3', col_idx['level_3'], cur_level_3, new_level_3))
        if new_time_4 and values_differ(cur_time_4, new_time_4):
            row_changes.append(('time_4', col_idx['time_4'], cur_time_4, new_time_4))
        if new_level_4 is not None and values_differ(cur_level_4, new_level_4):
            row_changes.append(('level_4', col_idx['level_4'], cur_level_4, new_level_4))

        if row_changes:
            changes.append({
                'row_idx': i,
                'station': station_name,
                'changes': row_changes
            })

    print(f"\nFound {len(changes)} rows with tide value changes")

    # Show first 10 changes
    print("\nFirst 10 rows with changes:")
    for ch in changes[:10]:
        print(f"  Row {ch['row_idx']}: {ch['station'][:40]}")
        for field, col, old, new in ch['changes']:
            print(f"    {field}: {old} -> {new}")

    if len(changes) > 10:
        print(f"  ... and {len(changes) - 10} more rows")

    # Apply changes
    print("\nApplying changes to ODS data...")
    cells_changed = 0
    for ch in changes:
        row_idx = ch['row_idx']
        for field, col, old, new in ch['changes']:
            # Ensure row is long enough
            while len(sheet[row_idx]) <= col:
                sheet[row_idx].append('')
            sheet[row_idx][col] = new
            cells_changed += 1

    print(f"Changed {cells_changed} cells in {len(changes)} rows")

    # Save ODS
    print("\nSaving ODS file...")
    ods.save_data(ods_path, ods_data)
    print(f"Saved to {ods_path}")

    return len(changes), cells_changed

if __name__ == "__main__":
    rows_changed, cells_changed = main()
    print(f"\n=== Summary ===")
    print(f"Rows modified: {rows_changed}")
    print(f"Cells modified: {cells_changed}")
