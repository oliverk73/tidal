#!/usr/bin/env python3
"""
Parse harmonic_subordinate_corrections idx file to CSV.
"""

import re
import csv

def parse_idx_file(idx_file):
    """Parse idx file and extract subordinate stations."""
    stations = []

    with open(idx_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith('t'):
            # Parse t line: tLand:Region:SubRegion: longitude latitude tz_offset StationName
            match = re.match(r't([^:]*):([^:]*):([^:]*):?\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?\d+:\d+)\s+(.+)', line)
            if match:
                land = match.group(1)
                region = match.group(2)
                subregion = match.group(3)
                lon = match.group(4)
                lat = match.group(5)
                tz_offset = match.group(6)
                name = match.group(7).strip()

                station = {
                    'land': land,
                    'region': region,
                    'longitude': lon,
                    'latitude': lat,
                    'station_name': name,
                    'timezone': tz_offset,
                }

                # Parse & line for corrections and reference station
                if i + 1 < len(lines) and lines[i + 1].strip().startswith('&'):
                    amp_line = lines[i + 1].strip()

                    # Try new format first: &hmin hmpy hoff lmin lmpy loff sta_id tzname ref_file_num ref_name
                    amp_match = re.match(r'&(-?\d+)\s+([\d.]+)\s+(-?[\d.]+)\s+(-?\d+)\s+([\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\S+/\S+)\s+(\d+)\s+(.+)', amp_line)
                    if amp_match:
                        station['hmin'] = amp_match.group(1)
                        station['hmpy'] = amp_match.group(2)
                        station['hoff'] = amp_match.group(3)
                        station['lmin'] = amp_match.group(4)
                        station['lmpy'] = amp_match.group(5)
                        station['loff'] = amp_match.group(6)
                        station['sta_id'] = amp_match.group(7)
                        station['tzname'] = amp_match.group(8)
                        station['ref_file_num'] = amp_match.group(9)
                        station['ref_name'] = amp_match.group(10).strip()
                        i += 1
                    else:
                        # Try old format: &hmin hmpy hoff lmin lmpy loff sta_id ref_file_num ref_name (no tzname)
                        amp_match_old = re.match(r'&(-?\d+)\s+([\d.]+)\s+(-?[\d.]+)\s+(-?\d+)\s+([\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(.+)', amp_line)
                        if amp_match_old:
                            station['hmin'] = amp_match_old.group(1)
                            station['hmpy'] = amp_match_old.group(2)
                            station['hoff'] = amp_match_old.group(3)
                            station['lmin'] = amp_match_old.group(4)
                            station['lmpy'] = amp_match_old.group(5)
                            station['loff'] = amp_match_old.group(6)
                            station['sta_id'] = amp_match_old.group(7)
                            station['tzname'] = ''  # No timezone in old format
                            station['ref_file_num'] = amp_match_old.group(8)
                            station['ref_name'] = amp_match_old.group(9).strip()
                            i += 1

                stations.append(station)

        i += 1

    return stations

def main():
    idx_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes9_ref_mapped.idx'
    output_file = '/home/oliver/subordinate_corrections/subordinate_stations_mapped.csv'

    print(f"Parsing {idx_file}...")
    stations = parse_idx_file(idx_file)
    print(f"Found {len(stations)} stations")

    # Write CSV
    fieldnames = [
        'land', 'region', 'longitude', 'latitude', 'station_name', 'timezone',
        'hmin', 'hmpy', 'hoff', 'lmin', 'lmpy', 'loff',
        'sta_id', 'tzname', 'ref_file_num', 'ref_name'
    ]

    with open(output_file, 'w', encoding='latin-1', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for station in stations:
            writer.writerow(station)

    print(f"Written to {output_file}")

    # Show reference station stats
    ref_stations = set(s.get('ref_name', '') for s in stations)
    print(f"\nUnique reference stations: {len(ref_stations)}")
    for ref in sorted(ref_stations)[:20]:
        count = sum(1 for s in stations if s.get('ref_name') == ref)
        print(f"  {ref}: {count} subordinate stations")

if __name__ == '__main__':
    main()
