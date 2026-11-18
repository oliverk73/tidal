#!/usr/bin/env python3
"""
Generate tide predictions from DWF TCD file and write into [DWF] rows of existing ODS file.
"""
import subprocess
import re
from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.text import P

# ODF namespace for table attributes
TABLE_NS = 'urn:oasis:names:tc:opendocument:xmlns:table:1.0'


def get_cell_text(cell):
    p = cell.getElementsByType(P)
    return str(p[0]) if p else ""


def set_cell_text(cell, text):
    for p in cell.getElementsByType(P):
        cell.removeChild(p)
    cell.addElement(P(text=text))


def expand_row_to_column(row, target_col):
    """
    Expand all compressed cells in a row up to and including target_col.
    This ensures cells[target_col] maps to the correct logical column.
    Returns the expanded cells list.
    """
    cells = row.getElementsByType(TableCell)

    # Build list of cells that need expansion, tracking which ones affect our range
    expansions_needed = []
    logical_col = 0
    raw_idx = 0

    while raw_idx < len(cells) and logical_col <= target_col:
        cell = cells[raw_idx]
        repeat_attr = cell.getAttrNS(TABLE_NS, 'number-columns-repeated')
        repeat_count = int(repeat_attr) if repeat_attr else 1

        if repeat_count > 1 and logical_col + repeat_count > target_col:
            # This repeated cell spans into or past our target - need to expand it
            # But only expand up to what we need
            expansions_needed.append((raw_idx, repeat_count))

        logical_col += repeat_count
        raw_idx += 1

    # Expand cells - work backwards to preserve indices
    for raw_idx, repeat_count in reversed(expansions_needed):
        cells = row.getElementsByType(TableCell)
        if raw_idx >= len(cells):
            continue

        cell = cells[raw_idx]
        repeat_attr = cell.getAttrNS(TABLE_NS, 'number-columns-repeated')
        if not repeat_attr:
            continue

        # Remove the repeated attribute
        cell.removeAttrNS(TABLE_NS, 'number-columns-repeated')

        # Get current text
        current_text = get_cell_text(cell)

        # Insert (repeat_count - 1) new cells after this one
        next_sibling = cell.nextSibling
        for _ in range(repeat_count - 1):
            new_cell = TableCell()
            if current_text:
                new_cell.addElement(P(text=current_text))
            if next_sibling:
                row.insertBefore(new_cell, next_sibling)
            else:
                row.addElement(new_cell)

    return row.getElementsByType(TableCell)


def get_tide_predictions(station_name, tcd_file):
    try:
        cmd = [
            'tide',
            '-l', station_name,
            '-b', '2026-01-28 00:00',
            '-e', '2026-01-31 23:59',
            '-m', 'p',
            '-em', 'pSsMm',
        ]
        env = {'HFILE_PATH': tcd_file}
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                env=env, encoding='iso-8859-1')
        if result.returncode != 0:
            return []
        return parse_tide_output(result.stdout)
    except Exception as e:
        print(f"    Error: {e}")
        return []


def parse_tide_output(output):
    predictions = []
    for line in output.strip().split('\n'):
        if not line.strip():
            continue
        match = re.match(
            r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s+(AM|PM)\s+\w+\s+([\d.]+)\s+meters?\s+(High|Low)',
            line
        )
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
            level_str = f'{level:.2f}'.replace('.', ',')
            predictions.append((time_str, level_str))
    return predictions


def main():
    ods_file = '/home/oliver/harmonics_working_help/tide_prediction_pegelonline_utide.ods'
    tcd_file = '/usr/share/xtide/harmonics-dwf-20070318_no_us_no_dupes.tcd'

    print("Loading ODS file...")
    doc = load(ods_file)
    table = doc.spreadsheet.getElementsByType(Table)[0]
    rows = table.getElementsByType(TableRow)

    # Find header columns
    header_row = rows[0]
    header_cells = header_row.getElementsByType(TableCell)
    headers = [get_cell_text(c) for c in header_cells]

    time1_idx = None
    for i, h in enumerate(headers):
        if h == 'Time_1':
            time1_idx = i
            break

    if time1_idx is None:
        print("ERROR: Time_1 column not found!")
        return

    max_pairs = (len(headers) - time1_idx) // 2
    print(f"Time_1 at column {time1_idx}, max pairs: {max_pairs}")

    processed = 0
    skipped = 0

    for row_idx in range(1, len(rows)):
        cells = rows[row_idx].getElementsByType(TableCell)
        if not cells:
            continue

        station_name = get_cell_text(cells[0])
        if not station_name:
            continue

        # Only process [DWF] rows
        if '[DWF]' not in station_name:
            skipped += 1
            continue

        # Strip " [DWF]" to get the actual station name for tide lookup
        tide_name = station_name.replace(' [DWF]', '')

        print(f"  [{processed+1}] {tide_name}...", end='', flush=True)

        preds = get_tide_predictions(tide_name, tcd_file)
        print(f" {len(preds)} predictions")

        # Expand any compressed/repeated cells up to the last Time/Level column
        # This is crucial: ODS compresses empty cells with number-columns-repeated
        last_col_needed = time1_idx + max_pairs * 2 - 1
        cells = expand_row_to_column(rows[row_idx], last_col_needed)

        # Ensure enough cells
        while len(cells) < time1_idx + max_pairs * 2:
            new_cell = TableCell()
            rows[row_idx].addElement(new_cell)
            cells = rows[row_idx].getElementsByType(TableCell)

        # Write predictions
        for p_idx, (time_str, level_str) in enumerate(preds[:max_pairs]):
            time_col = time1_idx + p_idx * 2
            level_col = time1_idx + p_idx * 2 + 1
            if time_col < len(cells):
                set_cell_text(cells[time_col], time_str)
            if level_col < len(cells):
                set_cell_text(cells[level_col], level_str)

        # Clear remaining
        for p_idx in range(len(preds), max_pairs):
            time_col = time1_idx + p_idx * 2
            level_col = time1_idx + p_idx * 2 + 1
            if time_col < len(cells):
                set_cell_text(cells[time_col], '')
            if level_col < len(cells):
                set_cell_text(cells[level_col], '')

        processed += 1

    print(f"\nProcessed DWF: {processed}, Skipped non-DWF: {skipped}")
    print(f"Saving to {ods_file}...")
    doc.save(ods_file)
    print("Done!")


if __name__ == '__main__':
    main()
