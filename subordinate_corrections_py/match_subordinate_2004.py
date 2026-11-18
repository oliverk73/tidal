#!/usr/bin/env python3
"""
Match subordinate stations with reference stations from 2004 harmonics file.
Uses fuzzy name matching, coordinates within 3 km, timezone within 1 hour.
"""

import csv
import re
import math
from difflib import SequenceMatcher


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def normalize_name(name):
    name = name.lower().strip()
    replacements = [
        (r'\bst\.?\s', 'saint '),
        (r'\bpt\.?\s', 'point '),
        (r'\bmt\.?\s', 'mount '),
        (r'\bft\.?\s', 'fort '),
        (r'\bn\.?\s', 'north '),
        (r'\bs\.?\s', 'south '),
        (r'\be\.?\s', 'east '),
        (r'\bw\.?\s', 'west '),
        (r'\bisl?\.?\s', 'island '),
        (r'\bhbr\.?\s', 'harbor '),
        (r'\bharbour\b', 'harbor'),
        (r'\brvr\.?\s', 'river '),
        (r'\bchan\.?\s', 'channel '),
        (r'\bentr\.?\s', 'entrance '),
        (r'\bbrg\.?\s', 'bridge '),
        (r'\bhwy\.?\s', 'highway '),
        (r'\b&\b', 'and'),
    ]
    for pattern, replacement in replacements:
        name = re.sub(pattern, replacement, name)
    name_without_parens = re.sub(r'\([^)]*\)', '', name)
    name_clean = re.sub(r'[^\w\s]', ' ', name_without_parens)
    name_clean = re.sub(r'\s+', ' ', name_clean).strip()
    return name_clean


def extract_core_name(name):
    name = normalize_name(name)
    parts = name.split(',')
    return parts[0].strip() if parts else name


def fuzzy_match_names(name1, name2, threshold=0.6):
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    if norm1 == norm2:
        return True, 1.0
    core1 = extract_core_name(name1)
    core2 = extract_core_name(name2)
    if core1 == core2:
        return True, 0.95
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    if ratio >= threshold:
        return True, ratio
    core_ratio = SequenceMatcher(None, core1, core2).ratio()
    if core_ratio >= threshold:
        return True, core_ratio
    if core1 in norm2 or core2 in norm1:
        return True, 0.7
    return False, max(ratio, core_ratio)


def parse_timezone_offset(tz_string):
    if not tz_string:
        return None
    match = re.match(r'([+-]?)(\d{1,2}):(\d{2})', tz_string)
    if match:
        sign = -1 if match.group(1) == '-' else 1
        hours = int(match.group(2))
        minutes = int(match.group(3))
        return sign * (hours + minutes / 60)
    match = re.match(r'(-?\d+):(\d+)', tz_string)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return hours + minutes / 60
    return None


def timezones_match(tz1, tz2, max_diff_hours=1):
    offset1 = parse_timezone_offset(tz1)
    offset2 = parse_timezone_offset(tz2)
    if offset1 is None or offset2 is None:
        return True
    return abs(offset1 - offset2) <= max_diff_hours


def parse_reference_stations(filepath):
    stations = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('# !longitude:'):
            longitude = float(line.split(':')[1].strip())
            if i + 1 < len(lines) and lines[i + 1].strip().startswith('# !latitude:'):
                latitude = float(lines[i + 1].strip().split(':')[1].strip())
                j = i + 2
                while j < len(lines) and lines[j].strip().startswith('#'):
                    j += 1
                if j < len(lines):
                    station_name = lines[j].strip()
                    if j + 1 < len(lines):
                        tz_line = lines[j + 1].strip()
                        tz_match = re.match(r'([+-]?\d{1,2}:\d{2})\s*:?\s*(\S+)?', tz_line)
                        if tz_match:
                            tz_offset = tz_match.group(1)
                            tz_name = tz_match.group(2) if tz_match.group(2) else ''
                            stations.append({
                                'name': station_name,
                                'longitude': longitude,
                                'latitude': latitude,
                                'tz_offset': tz_offset,
                                'tz_name': tz_name
                            })
        i += 1
    return stations


def parse_subordinate_stations(filepath):
    stations = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line1 = lines[i].strip()
        if line1 and (line1.startswith('t') or line1.startswith('c')):
            match = re.match(r'^[tc]([^:]+):([^:]*):([^:]*):(.*)$', line1)
            if match:
                rest = match.group(4).strip()
                data_match = re.match(r'^(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+:\d+)\s+(.+)$', rest)
                if data_match:
                    longitude = float(data_match.group(1))
                    latitude = float(data_match.group(2))
                    tz_offset = data_match.group(3)
                    station_name = data_match.group(4)
                    tzname = ''
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith('&'):
                        corr_line = lines[i + 1].strip()[1:]
                        parts = corr_line.split()
                        for part in parts:
                            if '/' in part and not part.startswith('-'):
                                tzname = part
                                break
                    stations.append({
                        'name': station_name,
                        'longitude': longitude,
                        'latitude': latitude,
                        'tz_offset': tz_offset,
                        'tz_name': tzname
                    })
        i += 1
    return stations


def format_number(val):
    if isinstance(val, float):
        return str(val).replace('.', ',')
    return val


def main():
    harmonics_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us_no_dupes2.txt'
    subordinate_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes2.idx'
    output_csv = '/home/oliver/subordinate_corrections/subordinate_matches_2004.csv'

    print("Parsing reference stations from 2004 harmonics file...")
    ref_stations = parse_reference_stations(harmonics_file)
    print(f"Found {len(ref_stations)} reference stations")

    print("Parsing subordinate stations...")
    sub_stations = parse_subordinate_stations(subordinate_file)
    print(f"Found {len(sub_stations)} subordinate stations")

    print("Finding matches (fuzzy name + coordinates + timezone)...")
    matches = []
    for sub in sub_stations:
        for ref in ref_stations:
            distance = haversine_distance(sub['latitude'], sub['longitude'], ref['latitude'], ref['longitude'])
            if distance > 3:
                continue
            if not timezones_match(sub['tz_offset'], ref['tz_offset']):
                continue
            name_match, similarity = fuzzy_match_names(sub['name'], ref['name'], 0.6)
            if name_match:
                matches.append({
                    'ref_name': ref['name'],
                    'ref_tz_offset': ref['tz_offset'],
                    'ref_tz_name': ref['tz_name'],
                    'ref_latitude': ref['latitude'],
                    'ref_longitude': ref['longitude'],
                    'sub_name': sub['name'],
                    'sub_tz_offset': sub['tz_offset'],
                    'sub_tz_name': sub['tz_name'],
                    'sub_latitude': sub['latitude'],
                    'sub_longitude': sub['longitude'],
                    'distance_km': round(distance, 3),
                    'name_similarity': round(similarity, 3)
                })
    print(f"Found {len(matches)} matches")

    fieldnames = ['harmonics_file', 'ref_name', 'ref_tz_offset', 'ref_tz_name', 'ref_latitude', 'ref_longitude',
                  'sub_name', 'sub_tz_offset', 'sub_tz_name', 'sub_latitude', 'sub_longitude', 'distance_km', 'name_similarity']

    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for match in matches:
            match['harmonics_file'] = 'harmonics-2004-06-14_no_us_no_dupes2.txt'
            match['ref_latitude'] = format_number(match['ref_latitude'])
            match['ref_longitude'] = format_number(match['ref_longitude'])
            match['sub_latitude'] = format_number(match['sub_latitude'])
            match['sub_longitude'] = format_number(match['sub_longitude'])
            match['distance_km'] = format_number(match['distance_km'])
            match['name_similarity'] = format_number(match['name_similarity'])
            writer.writerow(match)

    print(f"Results saved to: {output_csv}")


if __name__ == '__main__':
    main()
