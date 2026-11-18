#!/usr/bin/env python3
"""
Remove matched subordinate stations from the idx file.
"""

import csv
import re


def load_matches(csv_file):
    """Load subordinate station names from matches CSV."""
    matched_names = set()

    with open(csv_file, 'r', encoding='utf-8') as f:
        # CSV uses semicolon delimiter
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            matched_names.add(row['sub_name'])

    return matched_names


def remove_matched_stations(input_file, output_file, matched_names):
    """Remove matched stations from idx file."""

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    output_lines = []
    removed_count = 0

    i = 0
    while i < len(lines):
        line1 = lines[i].strip()

        # Check if this is a station line (starts with 't' for tide or 'c' for current)
        if line1 and (line1.startswith('t') or line1.startswith('c')):
            # Parse station name from line
            match = re.match(r'^[tc]([^:]+):([^:]*):([^:]*):(.*)$', line1)
            if match:
                rest = match.group(4).strip()
                # Parse: longitude latitude tz_offset station_name
                data_match = re.match(r'^(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+:\d+)\s+(.+)$', rest)
                if data_match:
                    station_name = data_match.group(4)

                    # Check if this station should be removed
                    if station_name in matched_names:
                        removed_count += 1
                        # Skip this line and the next & line
                        if i + 1 < len(lines) and lines[i + 1].strip().startswith('&'):
                            i += 2
                        else:
                            i += 1
                        continue

            # Keep this station
            output_lines.append(lines[i])
            if i + 1 < len(lines) and lines[i + 1].strip().startswith('&'):
                output_lines.append(lines[i + 1])
                i += 2
            else:
                i += 1
        else:
            i += 1

    # Write output file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)

    return removed_count, len(output_lines) // 2


def main():
    csv_file = '/home/oliver/subordinate_corrections/subordinate_matches_2010.csv'
    input_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us.idx'
    output_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes1.idx'

    print("Loading matches...")
    matched_names = load_matches(csv_file)
    print(f"Found {len(matched_names)} stations to remove")

    print("Removing matched stations...")
    removed, remaining = remove_matched_stations(input_file, output_file, matched_names)

    print(f"Removed: {removed} stations")
    print(f"Remaining: {remaining} stations")
    print(f"Saved to: {output_file}")


if __name__ == '__main__':
    main()
