#!/usr/bin/env python3
"""
Remove US stations from harmonics file based on stations_clean.csv
"""
import csv
import re

def read_us_station_names(csv_file):
    """Read US station names from CSV file"""
    us_stations = set()

    with open(csv_file, 'r', encoding='iso-8859-1') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            if row['Verified_Country'] == 'United States':
                # Get the original station name
                original_name = row['Original_Name'].strip()
                us_stations.add(original_name)

    print(f"Found {len(us_stations)} US stations to remove")
    return us_stations

def is_station_name_line(line):
    """
    Check if a line is likely a station name.
    Station names:
    - Don't start with '#' (comments)
    - Don't start with '*' (markers)
    - Don't start with digits (constituent data, years, numbers)
    - Don't start with '+' or '-' followed by digit (time meridian)
    - Don't start with 'x ' (constituent placeholder)
    - Are not empty or just whitespace
    - Don't match constituent pattern (letters/numbers followed by whitespace and numbers)
    """
    line_stripped = line.strip()

    if not line_stripped:
        return False
    if line.startswith('#') or line.startswith('*'):
        return False
    if line.startswith('x '):
        return False

    # Check for time meridian line (e.g., "+09:00 :Asia/Tokyo")
    if re.match(r'^[+-]\d+:\d+', line_stripped):
        return False

    # Check for datum line (e.g., "1.8000 meters")
    if re.match(r'^\d+\.\d+\s+(meters|feet)', line_stripped):
        return False

    # Check for constituent data line (e.g., "K1              0.2480  212.22")
    # Constituent lines have a pattern: WORD WHITESPACE NUMBER WHITESPACE NUMBER
    if re.match(r'^[A-Z0-9\-]+\s+\d+\.\d+\s+\d+\.\d+', line_stripped):
        return False

    # Check for pure number lines
    if re.match(r'^[\d\s\.\-]+$', line_stripped):
        return False

    # If we get here, it's likely a station name
    return True

def remove_us_stations_from_harmonics(input_file, output_file, us_stations):
    """Remove US stations from harmonics file"""
    removed_count = 0
    kept_count = 0
    current_station_name = None
    skip_current_station = False
    station_block = []
    in_station = False

    with open(input_file, 'r', encoding='iso-8859-1') as inf:
        with open(output_file, 'w', encoding='iso-8859-1') as outf:
            for line in inf:
                # Check if this is a new station name
                if is_station_name_line(line):
                    # Write out the previous station block if we were keeping it
                    if in_station:
                        if not skip_current_station:
                            for block_line in station_block:
                                outf.write(block_line)
                            kept_count += 1
                        else:
                            removed_count += 1

                    # Start new station
                    current_station_name = line.strip()
                    skip_current_station = current_station_name in us_stations
                    station_block = [line]
                    in_station = True

                    if skip_current_station:
                        print(f"Removing: {current_station_name}")

                elif in_station:
                    # Continue accumulating current station
                    station_block.append(line)
                else:
                    # Header/preamble lines before any station
                    outf.write(line)

            # Write out the last station if keeping it
            if in_station:
                if not skip_current_station:
                    for block_line in station_block:
                        outf.write(block_line)
                    kept_count += 1
                else:
                    removed_count += 1

    print(f"\nProcessing complete:")
    print(f"  Stations removed: {removed_count}")
    print(f"  Stations kept: {kept_count}")
    return removed_count, kept_count

def main():
    csv_file = '/home/oliver/harmonics_working/stations_clean.csv'
    input_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us_no_dupes2.txt'
    output_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us2_no_dupes2.txt'

    print("Reading US station names from CSV...")
    us_stations = read_us_station_names(csv_file)

    print(f"\nRemoving US stations from {input_file}...")
    removed, kept = remove_us_stations_from_harmonics(input_file, output_file, us_stations)

    print(f"\nOutput written to: {output_file}")

if __name__ == '__main__':
    main()
