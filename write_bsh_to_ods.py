#!/usr/bin/env python3
"""
Write all 88 BSH tide predictions (28-31 Jan 2026) into the ODS spreadsheet.
Adds BSH rows with Source='BSH', Datum='PNP' for each station.
Skips stations that already have BSH entries in the ODS.
"""

import glob
import re
import ezodf
from pathlib import Path

ODS_PATH = Path("/home/oliver/harmonics_working_help/tide_prediction_pegelonline_utide.ods")
BSH_DIR = Path("/home/oliver/harmonics_working_help/BSH")


def parse_bsh_file(filepath):
    """Parse a BSH prediction file, return station name and events for 28-31 Jan 2026."""
    name = ""
    pnp_nhn = None  # PNP offset to NHN
    events = []  # list of (day, hour, minute, hw_nw, height_pnp)

    with open(filepath, "r", encoding="latin-1") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("A04#"):
                # Station name
                name = line.split("#")[2].strip()
            elif line.startswith("D01#"):
                # PNP to NHN offset, e.g. "- 5.04"
                val = line.split("#")[2].strip()
                try:
                    pnp_nhn = float(val)
                except ValueError:
                    pass
            elif line.startswith("VB2#"):
                parts = line.split("#")
                hw_nw = parts[3].strip()  # 'H' or 'N'
                date_str = parts[5].strip()
                time_str = parts[6].strip()
                height_str = parts[7].strip()

                m = re.match(r"(\d+)\.\s*(\d+)\.(\d+)", date_str)
                if not m:
                    continue
                day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))

                # Only 28-31 January 2026
                if year != 2026 or month != 1 or day < 28 or day > 31:
                    continue

                # Parse time
                tm = re.match(r"(\d+):(\d+)", time_str)
                if not tm:
                    continue
                hour, minute = int(tm.group(1)), int(tm.group(2))

                # Parse height
                try:
                    height = float(height_str)
                except ValueError:
                    continue

                events.append((day, hour, minute, hw_nw, height))

    # Sort events chronologically
    events.sort(key=lambda e: (e[0], e[1], e[2]))

    return name, pnp_nhn, events


def get_existing_bsh_stations(sheet):
    """Get set of BSH station names already in the ODS."""
    existing = set()
    for r in range(1, sheet.nrows()):
        src = sheet[r, 1].value
        if src == "BSH":
            station = sheet[r, 0].value
            if station:
                existing.add(station.strip())
    return existing


def find_insert_position(sheet):
    """Find the row after the last data row to append new BSH entries."""
    last_data_row = 0
    for r in range(1, sheet.nrows()):
        if sheet[r, 0].value or sheet[r, 1].value:
            last_data_row = r
    return last_data_row + 1


def main():
    # Parse all BSH files
    bsh_files = sorted(glob.glob(str(BSH_DIR / "DE__*2026.txt")))
    print(f"Found {len(bsh_files)} BSH files")

    stations = []
    for filepath in bsh_files:
        name, pnp_nhn, events = parse_bsh_file(filepath)
        if events:
            stations.append((name, pnp_nhn, events))
            print(f"  {name}: {len(events)} events (28-31 Jan)")
        else:
            print(f"  {name}: NO events for 28-31 Jan - SKIPPED")

    print(f"\nStations with data: {len(stations)}")

    # Open ODS
    doc = ezodf.opendoc(str(ODS_PATH))
    sheet = doc.sheets[0]
    print(f"\nODS: {sheet.name}, {sheet.nrows()} rows, {sheet.ncols()} cols")

    # Check existing BSH stations
    existing = get_existing_bsh_stations(sheet)
    print(f"Existing BSH stations in ODS: {len(existing)}")
    for s in sorted(existing):
        print(f"  - {s}")

    # Filter out already-existing stations
    new_stations = [(n, p, e) for n, p, e in stations if n not in existing]
    print(f"\nNew stations to add: {len(new_stations)}")

    if not new_stations:
        print("Nothing to add!")
        return

    # Find insert position
    insert_row = find_insert_position(sheet)
    print(f"Insert position: row {insert_row}")

    # We need to add rows: for each station, 1 data row + 1 blank separator
    rows_needed = len(new_stations) * 2  # data row + separator
    current_rows = sheet.nrows()
    current_cols = sheet.ncols()

    # Ensure sheet has enough rows
    if insert_row + rows_needed > current_rows:
        sheet.append_rows(insert_row + rows_needed - current_rows + 10)
        print(f"Expanded sheet to {sheet.nrows()} rows")

    # Determine max Time/Level columns needed
    max_events = max(len(e) for _, _, e in new_stations)
    cols_needed = 7 + max_events * 2  # 7 header cols + time/level pairs
    if cols_needed > current_cols:
        sheet.append_columns(cols_needed - current_cols)
        print(f"Expanded sheet to {sheet.ncols()} cols")

    # Write new BSH stations
    row = insert_row
    for name, pnp_nhn, events in sorted(new_stations, key=lambda x: x[0]):
        # Write data row
        sheet[row, 0].set_value(name)
        sheet[row, 1].set_value("BSH")
        sheet[row, 2].set_value("PNP")
        # Col 3-5 empty (Datum Wert, Lat, Lon)
        sheet[row, 6].set_value("Europe/Berlin")

        # Write time/level pairs
        for i, (day, hour, minute, hw_nw, height) in enumerate(events):
            time_col = 7 + i * 2
            level_col = 8 + i * 2
            time_str = f"{hour}:{minute:02d}"
            sheet[row, time_col].set_value(time_str)
            sheet[row, level_col].set_value(height)

        row += 1
        # Blank separator row
        row += 1

    print(f"\nWrote {len(new_stations)} new BSH stations ({row - insert_row} rows)")

    # Save
    doc.save()
    print(f"Saved to {ODS_PATH}")


if __name__ == "__main__":
    main()
