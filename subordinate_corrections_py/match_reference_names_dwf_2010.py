#!/usr/bin/env python3
"""
Match reference station names from .idx file with reference stations from harmonics .txt file.
Uses fuzzy matching on the beginning of names, with timezone as a hint.
"""

import re
import csv
from difflib import SequenceMatcher

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
    """Parse subordinate stations and their reference station names from .idx file."""
    stations = []
    with open(idx_file, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith('t'):
            # Parse t line: tRegion:SubRegion:: longitude latitude tz_offset StationName
            match = re.match(r't[^:]*:[^:]*:?[^:]*:\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?\d+:\d+)\s+(.+)', line)
            if match:
                lon = float(match.group(1))
                lat = float(match.group(2))
                tz_offset = match.group(3)
                name = match.group(4).strip()

                # Get reference station name from & line
                ref_name = ''
                ref_tz = ''
                if i + 1 < len(lines) and lines[i + 1].startswith('&'):
                    amp_line = lines[i + 1].strip()
                    # Format: &hmin hmpy hoff lmin lmpy loff 0 TzName 0 RefName
                    # Find timezone name and reference station name
                    tz_match = re.search(r'\s([A-Za-z_/]+)\s+0\s+(.+)$', amp_line)
                    if tz_match:
                        ref_tz = tz_match.group(1)
                        ref_name = tz_match.group(2).strip()

                stations.append({
                    'sub_name': name,
                    'sub_tz_offset': tz_offset,
                    'sub_latitude': lat,
                    'sub_longitude': lon,
                    'ref_name_idx': ref_name,
                    'ref_tz_name': ref_tz
                })

        i += 1

    return stations

def normalize_name(name):
    """Normalize station name for comparison."""
    name = name.lower()
    # Common abbreviations
    name = re.sub(r'\bst\.\s*', 'saint ', name)
    name = re.sub(r'\bmt\.\s*', 'mount ', name)
    name = re.sub(r'\bhbr\b', 'harbour', name)
    name = re.sub(r'\bharbor\b', 'harbour', name)
    name = re.sub(r'\bisl\b', 'island', name)
    name = re.sub(r'\brvr\b', 'river', name)
    name = re.sub(r'\bpt\b', 'point', name)
    # Remove extra spaces and punctuation
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def get_name_start(name, ratio=0.7):
    """Get the beginning portion of a name (70% of words or characters)."""
    words = name.split()
    if len(words) > 1:
        # Use 70% of words
        num_words = max(1, int(len(words) * ratio))
        return ' '.join(words[:num_words])
    else:
        # Use 70% of characters for single word
        num_chars = max(3, int(len(name) * ratio))
        return name[:num_chars]

def name_start_similarity(name1, name2, ratio=0.7):
    """Calculate similarity between the beginnings of two names."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    start1 = get_name_start(norm1, ratio)
    start2 = get_name_start(norm2, ratio)

    # Direct match
    if start1 == start2:
        return 1.0

    # Check if one start contains the other
    if start1 in norm2 or start2 in norm1:
        return 0.85

    # Fuzzy match on starts
    return SequenceMatcher(None, start1, start2).ratio()

def parse_timezone_offset_minutes(tz_string):
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

def timezones_similar(tz1, tz2):
    """Check if timezones are similar (within 1 hour)."""
    offset1 = parse_timezone_offset_minutes(tz1)
    offset2 = parse_timezone_offset_minutes(tz2)
    if offset1 is None or offset2 is None:
        return True  # Can't compare, assume OK
    return abs(offset1 - offset2) <= 60

def find_reference_matches(sub_stations, ref_stations, min_similarity=0.7):
    """Find matching reference stations for each subordinate station."""
    results = []

    for sub in sub_stations:
        ref_name_idx = sub['ref_name_idx']
        if not ref_name_idx:
            continue

        matches = []
        for ref in ref_stations:
            similarity = name_start_similarity(ref_name_idx, ref['name'])

            if similarity >= min_similarity:
                tz_hint = "OK" if timezones_similar(sub['sub_tz_offset'], ref['tz_offset']) else "DIFF"
                matches.append({
                    'ref_harmonics_name': ref['name'],
                    'ref_harmonics_tz': ref['tz_offset'],
                    'ref_harmonics_lat': ref['latitude'],
                    'ref_harmonics_lon': ref['longitude'],
                    'similarity': similarity,
                    'tz_hint': tz_hint
                })

        # Sort by similarity (best first), then by timezone match
        matches.sort(key=lambda x: (-x['similarity'], x['tz_hint'] != 'OK'))

        if matches:
            # If best match is clear (similarity >= 0.95 and timezone OK), only use that one
            best = matches[0]
            if best['similarity'] >= 0.95 and best['tz_hint'] == 'OK':
                matches = [best]

            for match in matches:
                results.append({
                    'sub_name': sub['sub_name'],
                    'sub_tz_offset': sub['sub_tz_offset'],
                    'sub_latitude': sub['sub_latitude'],
                    'sub_longitude': sub['sub_longitude'],
                    'ref_name_idx': ref_name_idx,
                    'ref_harmonics_name': match['ref_harmonics_name'],
                    'ref_harmonics_tz': match['ref_harmonics_tz'],
                    'ref_harmonics_lat': match['ref_harmonics_lat'],
                    'ref_harmonics_lon': match['ref_harmonics_lon'],
                    'similarity': match['similarity'],
                    'tz_hint': match['tz_hint']
                })

    return results

def main():
    harmonics_file = '/home/oliver/harmonics_working/harmonics-dwf-20100529-nonfree_edit.txt'
    idx_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes7.idx'
    output_csv = '/home/oliver/subordinate_corrections/subordinate_reference_matches_dwf_2010.csv'

    print("Parsing reference stations from harmonics file...")
    ref_stations = parse_reference_stations(harmonics_file)
    print(f"  Found {len(ref_stations)} reference stations")

    print("Parsing subordinate stations from .idx file...")
    sub_stations = parse_subordinate_stations(idx_file)
    print(f"  Found {len(sub_stations)} subordinate stations")

    # Get unique reference names from idx
    unique_refs = set(s['ref_name_idx'] for s in sub_stations if s['ref_name_idx'])
    print(f"  Unique reference station names in idx: {len(unique_refs)}")

    print("Finding reference name matches (70% start similarity)...")
    results = find_reference_matches(sub_stations, ref_stations, min_similarity=0.7)
    print(f"  Found {len(results)} matches")

    print(f"Writing to {output_csv}...")
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow([
            'sub_name', 'sub_tz_offset', 'sub_latitude', 'sub_longitude',
            'ref_name_idx', 'ref_harmonics_name', 'ref_harmonics_tz',
            'ref_harmonics_lat', 'ref_harmonics_lon', 'similarity', 'tz_hint'
        ])

        for r in results:
            writer.writerow([
                r['sub_name'],
                r['sub_tz_offset'],
                str(r['sub_latitude']).replace('.', ','),
                str(r['sub_longitude']).replace('.', ','),
                r['ref_name_idx'],
                r['ref_harmonics_name'],
                r['ref_harmonics_tz'],
                str(r['ref_harmonics_lat']).replace('.', ','),
                str(r['ref_harmonics_lon']).replace('.', ','),
                str(round(r['similarity'], 3)).replace('.', ','),
                r['tz_hint']
            ])

    print("Done!")

    # Show some examples
    if results:
        print("\nExamples:")
        shown = set()
        for r in results[:20]:
            key = (r['ref_name_idx'], r['ref_harmonics_name'])
            if key not in shown:
                print(f"  IDX: {r['ref_name_idx']}")
                print(f"  -> Harmonics: {r['ref_harmonics_name']} (sim: {r['similarity']:.2f}, tz: {r['tz_hint']})")
                print()
                shown.add(key)

if __name__ == '__main__':
    main()
