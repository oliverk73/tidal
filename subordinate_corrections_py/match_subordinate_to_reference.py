#!/usr/bin/env python3
"""
Match subordinate stations from .idx file with reference stations from harmonics .txt file.
Uses fuzzy name matching, coordinate distance (<=3km), and timezone comparison (<=1h).
"""

import re
import csv
import math
from difflib import SequenceMatcher

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km."""
    R = 6371  # Earth's radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

def parse_timezone_offset(tz_string):
    """Parse timezone offset to minutes. Returns None if unparseable."""
    if not tz_string:
        return None

    tz_string = tz_string.strip()

    # Format: +HH:MM or -HH:MM or +H:M or -H:M or just H:M
    match = re.match(r'([+-])?(\d{1,2}):(\d{1,2})', tz_string)
    if match:
        sign = -1 if match.group(1) == '-' else 1
        hours = int(match.group(2))
        minutes = int(match.group(3))
        return sign * (hours * 60 + minutes)

    # Format: just a number (hours)
    try:
        hours = float(tz_string)
        return int(hours * 60)
    except:
        return None

def timezone_diff_ok(tz1, tz2, max_diff_hours=1):
    """Check if two timezones are within max_diff_hours of each other."""
    offset1 = parse_timezone_offset(tz1)
    offset2 = parse_timezone_offset(tz2)

    if offset1 is None or offset2 is None:
        return True  # If we can't parse, assume OK

    diff_minutes = abs(offset1 - offset2)
    return diff_minutes <= max_diff_hours * 60

def normalize_name(name):
    """Normalize station name for comparison."""
    name = name.lower()
    # Common abbreviations
    name = re.sub(r'\bst\.\s*', 'saint ', name)
    name = re.sub(r'\bmt\.\s*', 'mount ', name)
    name = re.sub(r'\bhbr\b', 'harbour', name)
    name = re.sub(r'\bhrbr\b', 'harbour', name)
    name = re.sub(r'\bharbor\b', 'harbour', name)
    name = re.sub(r'\bisl\b', 'island', name)
    name = re.sub(r'\bisls\b', 'islands', name)
    name = re.sub(r'\brvr\b', 'river', name)
    name = re.sub(r'\bch\b', 'channel', name)
    name = re.sub(r'\binl\b', 'inlet', name)
    name = re.sub(r'\bstr\b', 'strait', name)
    name = re.sub(r'\bsd\b', 'sound', name)
    name = re.sub(r'\bpt\b', 'point', name)
    name = re.sub(r'\bko\b', '', name)  # Japanese harbor suffix
    name = re.sub(r'\bwan\b', '', name)  # Japanese bay suffix
    # Remove extra spaces and punctuation
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def name_similarity(name1, name2):
    """Calculate similarity between two names."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    # Direct match after normalization
    if norm1 == norm2:
        return 1.0

    # Check if one contains the other
    if norm1 in norm2 or norm2 in norm1:
        return 0.8

    # Fuzzy match
    return SequenceMatcher(None, norm1, norm2).ratio()

def parse_reference_stations(harmonics_file):
    """Parse reference stations from harmonics .txt file."""
    stations = []

    with open(harmonics_file, 'r', encoding='iso-8859-1') as f:
        content = f.read()

    # Split into blocks - each station starts with metadata comments
    # Pattern: # !longitude: followed by # !latitude: followed by station name
    pattern = r'# !longitude:\s*(-?[\d.]+)\s*\n# !latitude:\s*(-?[\d.]+)\s*\n([^\n#]+)\n([+-]?\d{1,2}:\d{2})\s*:?([^\n]*)'

    for match in re.finditer(pattern, content):
        lon = float(match.group(1))
        lat = float(match.group(2))
        name = match.group(3).strip()
        tz_offset = match.group(4).strip()
        tz_name = match.group(5).strip() if match.group(5) else ''

        stations.append({
            'name': name,
            'tz_offset': tz_offset,
            'tz_name': tz_name,
            'latitude': lat,
            'longitude': lon
        })

    return stations

def parse_subordinate_stations(idx_file):
    """Parse subordinate stations from .idx file."""
    stations = []

    with open(idx_file, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith('t'):
            # Parse t line: tRegion:SubRegion:: longitude latitude tz_offset StationName
            match = re.match(r't[^:]*:[^:]*::\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?\d+:\d+)\s+(.+)', line)
            if match:
                lon = float(match.group(1))
                lat = float(match.group(2))
                tz_offset = match.group(3)
                name = match.group(4).strip()

                # Get timezone from & line
                tz_name = ''
                if i + 1 < len(lines) and lines[i + 1].startswith('&'):
                    amp_line = lines[i + 1]
                    # Find timezone name in & line (after the numbers)
                    tz_match = re.search(r'\s([A-Za-z_/]+)\s+0\s+', amp_line)
                    if tz_match:
                        tz_name = tz_match.group(1)

                stations.append({
                    'name': name,
                    'tz_offset': tz_offset,
                    'tz_name': tz_name,
                    'latitude': lat,
                    'longitude': lon
                })

        i += 1

    return stations

def find_matches(ref_stations, sub_stations, max_distance_km=3, min_name_similarity=0.5):
    """Find matching stations between reference and subordinate."""
    matches = []

    for sub in sub_stations:
        for ref in ref_stations:
            # Check distance first (fastest filter)
            distance = haversine_distance(
                sub['latitude'], sub['longitude'],
                ref['latitude'], ref['longitude']
            )

            if distance > max_distance_km:
                continue

            # Check timezone
            if not timezone_diff_ok(sub['tz_offset'], ref['tz_offset']):
                continue

            # Check name similarity
            similarity = name_similarity(sub['name'], ref['name'])
            if similarity < min_name_similarity:
                continue

            matches.append({
                'ref_name': ref['name'],
                'ref_tz_offset': ref['tz_offset'],
                'ref_tz_name': ref['tz_name'],
                'ref_latitude': str(ref['latitude']).replace('.', ','),
                'ref_longitude': str(ref['longitude']).replace('.', ','),
                'sub_name': sub['name'],
                'sub_tz_offset': sub['tz_offset'],
                'sub_tz_name': sub['tz_name'],
                'sub_latitude': str(sub['latitude']).replace('.', ','),
                'sub_longitude': str(sub['longitude']).replace('.', ','),
                'distance_km': str(round(distance, 3)).replace('.', ','),
                'name_similarity': str(round(similarity, 3)).replace('.', ',')
            })

    return matches

def main():
    harmonics_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    idx_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes4.idx'
    output_csv = '/home/oliver/subordinate_corrections/subordinate_matches_old.csv'

    print("Parsing reference stations from harmonics file...")
    ref_stations = parse_reference_stations(harmonics_file)
    print(f"  Found {len(ref_stations)} reference stations")

    print("\nParsing subordinate stations from .idx file...")
    sub_stations = parse_subordinate_stations(idx_file)
    print(f"  Found {len(sub_stations)} subordinate stations")

    print("\nFinding matches (distance <= 3km, timezone <= 1h, name similarity >= 0.5)...")
    matches = find_matches(ref_stations, sub_stations)
    print(f"  Found {len(matches)} matches")

    print(f"\nWriting results to {output_csv}...")
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow([
            'harmonics_file',
            'ref_name', 'ref_tz_offset', 'ref_latitude', 'ref_longitude',
            'sub_name', 'sub_tz_offset', 'sub_latitude', 'sub_longitude',
            'distance_km', 'name_similarity'
        ])

        for match in matches:
            writer.writerow([
                'harmonics_old_no_us_no_dupes3.txt',
                match['ref_name'],
                match['ref_tz_offset'],
                match['ref_latitude'],
                match['ref_longitude'],
                match['sub_name'],
                match['sub_tz_offset'],
                match['sub_latitude'],
                match['sub_longitude'],
                match['distance_km'],
                match['name_similarity']
            ])

    print("Done!")

    # Show some examples
    if matches:
        print("\nExamples of matches:")
        for match in matches[:10]:
            print(f"  {match['ref_name']}")
            print(f"    <-> {match['sub_name']}")
            print(f"    Distance: {match['distance_km']} km, Similarity: {match['name_similarity']}")
            print()

if __name__ == '__main__':
    main()
