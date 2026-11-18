#!/usr/bin/env python3
"""
Generate tide predictions from UTide TCD file and write to existing ODS file.
Only writes to non-[DWF] rows.
"""
import subprocess
import re
from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.text import P


def get_cell_text(cell):
    p = cell.getElementsByType(P)
    return str(p[0]) if p else ""


def set_cell_text(cell, text):
    """Replace cell text content."""
    # Remove existing P elements
    for p in cell.getElementsByType(P):
        cell.removeChild(p)
    cell.addElement(P(text=text))


def get_tide_predictions(station_name, tcd_file):
    """Get tide predictions using tide command for 28.01-31.01.2026."""
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
    """Parse tide output into list of (time_str, level_str) tuples."""
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
    ods_file = '/home/oliver/harmonics_working_help/tide_prediction_pegelonline_2026-01-27.ods'
    tcd_file = '/usr/share/xtide/harmonics_utide_germany_2026-01-27.tcd'
    output_file = '/home/oliver/harmonics_working_help/tide_prediction_pegelonline_utide.ods'

    print("Loading ODS file...")
    doc = load(ods_file)
    table = doc.spreadsheet.getElementsByType(Table)[0]
    rows = table.getElementsByType(TableRow)

    # Find header columns
    header_row = rows[0]
    header_cells = header_row.getElementsByType(TableCell)
    headers = [get_cell_text(c) for c in header_cells]

    # Find Time_1 column index
    time1_idx = None
    for i, h in enumerate(headers):
        if h == 'Time_1':
            time1_idx = i
            break

    if time1_idx is None:
        print("ERROR: Time_1 column not found!")
        return

    print(f"Time_1 starts at column {time1_idx}")
    max_pairs = (len(headers) - time1_idx) // 2
    print(f"Max prediction pairs: {max_pairs}")

    # Process each row
    processed = 0
    skipped_dwf = 0

    for row_idx in range(1, len(rows)):
        cells = rows[row_idx].getElementsByType(TableCell)
        if not cells:
            continue

        station_name = get_cell_text(cells[0])
        if not station_name:
            continue

        if '[DWF]' in station_name:
            # Clear any existing values in Time/Level columns
            for col in range(time1_idx, min(time1_idx + max_pairs * 2, len(cells))):
                set_cell_text(cells[col], '')
            skipped_dwf += 1
            continue

        print(f"  [{processed+1}] {station_name}...", end='', flush=True)

        preds = get_tide_predictions(station_name, tcd_file)
        print(f" {len(preds)} predictions")

        # Write predictions into Time/Level columns
        # Ensure we have enough cells
        while len(cells) < time1_idx + max_pairs * 2:
            new_cell = TableCell()
            rows[row_idx].addElement(new_cell)
            cells = rows[row_idx].getElementsByType(TableCell)

        for p_idx, (time_str, level_str) in enumerate(preds[:max_pairs]):
            time_col = time1_idx + p_idx * 2
            level_col = time1_idx + p_idx * 2 + 1

            if time_col < len(cells):
                set_cell_text(cells[time_col], time_str)
            if level_col < len(cells):
                set_cell_text(cells[level_col], level_str)

        # Clear remaining pairs
        for p_idx in range(len(preds), max_pairs):
            time_col = time1_idx + p_idx * 2
            level_col = time1_idx + p_idx * 2 + 1
            if time_col < len(cells):
                set_cell_text(cells[time_col], '')
            if level_col < len(cells):
                set_cell_text(cells[level_col], '')

        processed += 1

    print(f"\nProcessed: {processed}, Skipped DWF: {skipped_dwf}")
    print(f"Saving to {output_file}...")
    doc.save(output_file)
    print("Done!")


if __name__ == '__main__':
    main()
