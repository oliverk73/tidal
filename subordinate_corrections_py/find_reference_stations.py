#!/usr/bin/env python3
"""
Find reference stations from idx file in all harmonics txt files.
Creates a mapping of idx reference name -> harmonics station name + file.
"""

import os
import re
import glob

def extract_reference_stations_from_idx(idx_file):
    """Extract unique reference station names from idx file."""
    ref_stations = set()

    with open(idx_file, 'rb') as f:
        content = f.read()

    # Decode with latin-1 to handle special characters
    text = content.decode('latin-1', errors='replace')

    # Find all & lines and extract reference station at the end
    # Format: &num num num num num num num Timezone 0 RefStationName
    pattern = r'&[^\n]+\s+0\s+([A-Za-z][^\n]+)'

    for match in re.finditer(pattern, text):
        ref_name = match.group(1).strip()
        # Filter out malformed entries
        if ref_name and not ref_name[0].isdigit() and len(ref_name) > 3:
            ref_stations.add(ref_name)

    return sorted(ref_stations)

def find_station_in_harmonics(station_name, harmonics_files):
    """Find a station in harmonics files. Returns list of (file, exact_name, lat, lon)."""
    results = []

    for hfile in harmonics_files:
        with open(hfile, 'r', encoding='latin-1', errors='replace') as f:
            content = f.read()

        # First try exact match
        if station_name in content:
            # Find the station block with coordinates
            pattern = rf'# !longitude:\s*(-?[\d.]+)\s*\n# !latitude:\s*(-?[\d.]+)\s*\n({re.escape(station_name)})\n([+-]?\d{{1,2}}:\d{{2}})'
            match = re.search(pattern, content)
            if match:
                lon = float(match.group(1))
                lat = float(match.group(2))
                exact_name = match.group(3)
                tz = match.group(4)
                results.append({
                    'file': os.path.basename(hfile),
                    'name': exact_name,
                    'lat': lat,
                    'lon': lon,
                    'tz': tz,
                    'match_type': 'exact'
                })

    return results

def main():
    idx_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes9.idx'
    harmonics_dir = '/home/oliver/harmonics_working'
    output_file = '/home/oliver/subordinate_corrections/reference_station_mapping_all.csv'

    # Get all harmonics files
    harmonics_files = glob.glob(os.path.join(harmonics_dir, 'harmonic*.txt'))
    print(f"Found {len(harmonics_files)} harmonics files:")
    for f in harmonics_files:
        print(f"  - {os.path.basename(f)}")

    # Extract reference stations from idx
    print(f"\nExtracting reference stations from {os.path.basename(idx_file)}...")
    ref_stations = extract_reference_stations_from_idx(idx_file)
    print(f"Found {len(ref_stations)} unique reference stations")

    # Find each reference station in harmonics files
    print("\nSearching for reference stations in harmonics files...")

    found = []
    not_found = []

    for ref_name in ref_stations:
        results = find_station_in_harmonics(ref_name, harmonics_files)
        if results:
            for r in results:
                found.append({
                    'ref_name_idx': ref_name,
                    'harmonics_file': r['file'],
                    'harmonics_name': r['name'],
                    'lat': r['lat'],
                    'lon': r['lon'],
                    'tz': r['tz'],
                    'match_type': r['match_type']
                })
        else:
            not_found.append(ref_name)

    # Write results
    print(f"\nResults:")
    print(f"  Found: {len(found)} matches for {len(ref_stations) - len(not_found)} stations")
    print(f"  Not found: {len(not_found)} stations")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("ref_name_idx;harmonics_file;harmonics_name;lat;lon;tz;match_type\n")
        for entry in found:
            f.write(f"{entry['ref_name_idx']};{entry['harmonics_file']};{entry['harmonics_name']};{entry['lat']};{entry['lon']};{entry['tz']};{entry['match_type']}\n")

    print(f"\nMapping written to: {output_file}")

    # Print not found stations
    if not_found:
        print("\nStations NOT FOUND in any harmonics file:")
        for name in not_found:
            print(f"  - {name}")

        # Write not found to separate file
        not_found_file = '/home/oliver/subordinate_corrections/reference_stations_not_found.txt'
        with open(not_found_file, 'w', encoding='utf-8') as f:
            for name in not_found:
                f.write(f"{name}\n")
        print(f"\nNot found list written to: {not_found_file}")

if __name__ == '__main__':
    main()
