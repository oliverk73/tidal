#!/usr/bin/env python3
"""
Match subordinate stations from .idx file with reference stations from harmonics .txt file.
Uses coordinate distance (<=3km) and timezone comparison (<=1h).
"""

import re
import csv
import math

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km."""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def parse_timezone_offset(tz_string):
    """Parse timezone offset to minutes."""
    if not tz_string:
        return None
    tz_string = tz_string.strip()
    match = re.match(r'([+-])?0?(\d{1,2}):(\d{1,2})', tz_string)
    if match:
        sign = -1 if match.group(1) == '-' else 1
        hours = int(match.group(2))
        minutes = int(match.group(3))
        return sign * (hours * 60 + minutes)
    return None

def timezone_diff_ok(tz1, tz2, max_diff_hours=1):
    """Check if two timezones are within max_diff_hours of each other."""
    offset1 = parse_timezone_offset(tz1)
    offset2 = parse_timezone_offset(tz2)
    if offset1 is None or offset2 is None:
        return True
    diff_minutes = abs(offset1 - offset2)
    return diff_minutes <= max_diff_hours * 60

def parse_reference_stations(harmonics_file):
    """Parse reference stations from harmonics .txt file."""
    stations = []
    with open(harmonics_file, 'r', encoding='iso-8859-1') as f:
        content = f.read()
    pattern = r'# !longitude:\s*(-?[\d.]+)\s*\n# !latitude:\s*(-?[\d.]+)\s*\n([^\n#]+)\n([+-]?\d{1,2}:\d{2})\s*:?([^\n]*)'
    for match in re.finditer(pattern, content):
        lon = float(match.group(1))
        lat = float(match.group(2))
        name = match.group(3).strip()
        tz_offset = match.group(4).strip()
        stations.append({
            'name': name,
            'tz_offset': tz_offset,
            'latitude': lat,
            'longitude': lon
        })
    return stations

def parse_subordinate_stations(idx_file):
    """Parse subordinate stations from .idx file."""
    stations = []
    with open(idx_file, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if line.startswith('t'):
            match = re.match(r't[^:]*:[^:]*:?[^:]*:\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?\d+:\d+)\s+(.+)', line)
            if match:
                lon = float(match.group(1))
                lat = float(match.group(2))
                tz_offset = match.group(3)
                name = match.group(4).strip()
                stations.append({
                    'name': name,
                    'tz_offset': tz_offset,
                    'latitude': lat,
                    'longitude': lon
                })
    return stations

def find_matches(ref_stations, sub_stations, max_distance_km=3):
    """Find matching stations based on coordinates and timezone."""
    matches = []
    for sub in sub_stations:
        for ref in ref_stations:
            distance = haversine_distance(sub['latitude'], sub['longitude'], ref['latitude'], ref['longitude'])
            if distance > max_distance_km:
                continue
            if not timezone_diff_ok(sub['tz_offset'], ref['tz_offset']):
                continue
            matches.append({
                'ref_name': ref['name'],
                'ref_tz_offset': ref['tz_offset'],
                'ref_latitude': ref['latitude'],
                'ref_longitude': ref['longitude'],
                'sub_name': sub['name'],
                'sub_tz_offset': sub['tz_offset'],
                'sub_latitude': sub['latitude'],
                'sub_longitude': sub['longitude'],
                'distance_km': round(distance, 3)
            })
    return matches

def main():
    harmonics_file = '/home/oliver/harmonics_working/harmonics_pierre_lavergne_v10_no_dupes4.txt'
    idx_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes6.idx'
    output_csv = '/home/oliver/subordinate_corrections/subordinate_matches_pierre_lavergne_v10.csv'

    print("Parsing reference stations...")
    ref_stations = parse_reference_stations(harmonics_file)
    print(f"  Found {len(ref_stations)} reference stations")

    print("Parsing subordinate stations...")
    sub_stations = parse_subordinate_stations(idx_file)
    print(f"  Found {len(sub_stations)} subordinate stations")

    print("Finding matches (distance <= 3km, timezone <= 1h)...")
    matches = find_matches(ref_stations, sub_stations)
    print(f"  Found {len(matches)} matches")

    print(f"Writing to {output_csv}...")
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow([
            'harmonics_file',
            'ref_name', 'ref_tz_offset', 'ref_latitude', 'ref_longitude',
            'sub_name', 'sub_tz_offset', 'sub_latitude', 'sub_longitude',
            'distance_km'
        ])
        for match in matches:
            writer.writerow([
                'harmonics_pierre_lavergne_v10_no_dupes4.txt',
                match['ref_name'],
                match['ref_tz_offset'],
                str(match['ref_latitude']).replace('.', ','),
                str(match['ref_longitude']).replace('.', ','),
                match['sub_name'],
                match['sub_tz_offset'],
                str(match['sub_latitude']).replace('.', ','),
                str(match['sub_longitude']).replace('.', ','),
                str(match['distance_km']).replace('.', ',')
            ])
    print("Done!")

if __name__ == '__main__':
    main()
