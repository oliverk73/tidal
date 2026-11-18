#!/usr/bin/env python3
"""
Remove subordinate stations from .idx file based on CSV delete markers.
"""

import csv
import re

def load_stations_to_delete(csv_file):
    """Load station names marked for deletion from CSV."""
    stations = set()
    with open(csv_file, 'r', encoding='utf-8') as f:
        # CSV uses semicolon as delimiter
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            # Check "To do" column (with space, not hyphen)
            if row.get('To do', '').strip().lower() == 'delete':
                sub_name = row.get('sub_name', '').strip()
                if sub_name:
                    stations.add(sub_name)
    return stations

def remove_stations_from_idx(idx_file, output_file, stations_to_delete):
    """Remove stations from .idx file."""

    with open(idx_file, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    output_lines = []
    removed_count = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this is a station line (starts with 't')
        if line.startswith('t'):
            # Extract station name - it's at the end after coordinates
            # Format: tRegion:SubRegion:: lon lat tz_offset StationName
            # The station name is everything after "0:0 " or similar timezone offset
            match = re.search(r'\d+:\d+\s+(.+)$', line.rstrip())
            if match:
                station_name = match.group(1).strip()

                if station_name in stations_to_delete:
                    # Skip this line and the next & line
                    removed_count += 1
                    i += 1  # Skip t line
                    if i < len(lines) and lines[i].startswith('&'):
                        i += 1  # Skip & line
                    continue

        output_lines.append(line)
        i += 1

    with open(output_file, 'w', encoding='iso-8859-1') as f:
        f.writelines(output_lines)

    return removed_count

if __name__ == '__main__':
    csv_file = '/home/oliver/subordinate_corrections/subordinate_matches_2004_distance_matches.csv'
    idx_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes3.idx'
    output_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes4.idx'

    print("Loading stations to delete from CSV...")
    stations_to_delete = load_stations_to_delete(csv_file)
    print(f"Found {len(stations_to_delete)} stations marked for deletion")

    print("\nRemoving stations from .idx file...")
    removed = remove_stations_from_idx(idx_file, output_file, stations_to_delete)

    print(f"\nRemoved {removed} stations")
    print(f"Output: {output_file}")

    # Show some examples of what was removed
    if stations_to_delete:
        print("\nExamples of deleted stations:")
        for station in list(stations_to_delete)[:10]:
            print(f"  - {station}")
