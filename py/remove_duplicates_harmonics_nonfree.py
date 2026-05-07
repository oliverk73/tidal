#!/usr/bin/env python3
"""
Remove duplicate locations from HARMONICS_NO_US_no_us.txt that already exist
in the newer harmonics-dwf-20100529-nonfree_mod.txt file.

Duplicate criteria:
1. Exact match of location name line
2. Same location name and country
3. Same location name and state/region
4. Similar name (ignoring (2), (3), "- READ flaterco.com/pol.html", special chars)
5. Similar name + same timezone + coordinates within 1 km
"""

import re
import csv
import math
from difflib import SequenceMatcher

# Files
NEWER_FILE = "original/harmonics-dwf-20100529-nonfree_mod.txt"
OLDER_FILE = "harmonics/HARMONICS_NO_US_no_us.txt"
OUTPUT_FILE = "harmonics/HARMONICS_NO_US_no_us_no_dupes.txt"
DELETED_CSV = "deleted_duplicates.csv"
NUM_CONSTITUENTS = 173  # For older file
NUM_CONSTITUENTS_NEW = 175  # For newer file

def normalize_name(name):
    """Normalize location name for comparison."""
    # Remove (2), (3), etc.
    name = re.sub(r'\s*\(\d+\)\s*', '', name)
    # Remove "- READ flaterco.com/pol.html"
    name = re.sub(r'\s*-\s*READ\s+flaterco\.com/pol\.html\s*', '', name, flags=re.IGNORECASE)
    # Normalize whitespace
    name = ' '.join(name.split())
    # Strip
    name = name.strip()
    return name

def extract_name_parts(name_line):
    """Extract location name, state/region, and country from name line."""
    name_line = name_line.strip()

    # Remove suffixes
    clean = normalize_name(name_line)

    parts = clean.split(',')

    location = parts[0].strip() if len(parts) > 0 else ''
    state_region = parts[-2].strip() if len(parts) >= 3 else ''
    country = parts[-1].strip() if len(parts) >= 2 else ''

    return {
        'full_name': name_line,
        'normalized': clean,
        'location': location,
        'state_region': state_region,
        'country': country,
    }

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km."""
    R = 6371  # Earth's radius in km

    try:
        lat1, lon1 = float(lat1), float(lon1)
        lat2, lon2 = float(lat2), float(lon2)
    except (ValueError, TypeError):
        return float('inf')

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))

    return R * c

def similar_names(name1, name2, threshold=0.85):
    """Check if two names are similar using sequence matching."""
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio() >= threshold

def parse_harmonics_file(filename, num_constituents):
    """Parse harmonics file and extract location data."""
    with open(filename, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    # Normalize line endings
    lines = [line.replace('\r\n', '\n').replace('\r', '\n') for line in lines]

    # Find data start
    data_start = 0
    for i, line in enumerate(lines):
        if 'MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE' in line:
            data_start = i + 1
            break

    header_lines = lines[:data_start]
    locations = []

    i = data_start
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line.startswith('#'):
            block_start = i
            comment_lines = []

            # Collect comment lines
            while i < len(lines):
                current = lines[i].strip()
                if current.startswith('#') or current == '':
                    comment_lines.append(lines[i])
                    i += 1
                    if i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('#'):
                        break
                else:
                    break

            # Remove trailing empty lines
            while comment_lines and not comment_lines[-1].strip():
                comment_lines.pop()

            # Collect info lines
            info_lines = []
            for _ in range(3):
                if i < len(lines) and not lines[i].strip().startswith('#'):
                    info_lines.append(lines[i])
                    i += 1
                else:
                    break

            if len(info_lines) >= 1 and info_lines[0].strip():
                # Collect constituent lines
                constituent_lines = []
                for _ in range(num_constituents):
                    if i < len(lines):
                        constituent_lines.append(lines[i])
                        i += 1
                    else:
                        break

                # Extract location info
                name_line = info_lines[0].strip()
                timezone = info_lines[1].strip() if len(info_lines) > 1 else ''

                # Extract coordinates from comments
                lat, lon = '', ''
                for cline in comment_lines:
                    if '!latitude:' in cline:
                        match = re.search(r'!latitude:\s*(-?\d+\.?\d*)', cline)
                        if match:
                            lat = match.group(1)
                    elif '!longitude:' in cline:
                        match = re.search(r'!longitude:\s*(-?\d+\.?\d*)', cline)
                        if match:
                            lon = match.group(1)

                name_parts = extract_name_parts(name_line)

                locations.append({
                    'name_line': name_line,
                    'normalized': name_parts['normalized'],
                    'location': name_parts['location'],
                    'state_region': name_parts['state_region'],
                    'country': name_parts['country'],
                    'timezone': timezone,
                    'latitude': lat,
                    'longitude': lon,
                    'comment_lines': comment_lines,
                    'info_lines': info_lines,
                    'constituent_lines': constituent_lines,
                    'all_lines': comment_lines + info_lines + constituent_lines,
                })
        else:
            i += 1

    return header_lines, locations

def is_duplicate(old_loc, new_locations):
    """Check if old location is a duplicate of any new location."""
    old_name = old_loc['name_line']
    old_normalized = old_loc['normalized']
    old_location = old_loc['location']
    old_country = old_loc['country']
    old_state = old_loc['state_region']
    old_tz = old_loc['timezone']
    old_lat = old_loc['latitude']
    old_lon = old_loc['longitude']

    for new_loc in new_locations:
        new_name = new_loc['name_line']
        new_normalized = new_loc['normalized']
        new_location = new_loc['location']
        new_country = new_loc['country']
        new_state = new_loc['state_region']
        new_tz = new_loc['timezone']
        new_lat = new_loc['latitude']
        new_lon = new_loc['longitude']

        # Criterion 1: Exact match of name line
        if old_name == new_name:
            return True, f"Exact match: {new_name}"

        # Criterion 2: Normalized names match exactly
        if old_normalized == new_normalized:
            return True, f"Normalized match: {new_normalized}"

        # Criterion 3: Same location name and country
        if old_location and new_location and old_country and new_country:
            if old_location.lower() == new_location.lower() and old_country.lower() == new_country.lower():
                return True, f"Same location+country: {old_location}, {old_country}"

        # Criterion 4: Same location name and state/region
        if old_location and new_location and old_state and new_state:
            if old_location.lower() == new_location.lower() and old_state.lower() == new_state.lower():
                return True, f"Same location+state: {old_location}, {old_state}"

        # Criterion 5: Similar name + same timezone + coordinates within 1 km
        if similar_names(old_normalized, new_normalized, 0.85):
            if old_tz == new_tz:
                distance = haversine_distance(old_lat, old_lon, new_lat, new_lon)
                if distance < 1.0:
                    return True, f"Similar name+tz+coords (<1km): {new_normalized}"

    return False, None

def main():
    print("Parsing newer file (harmonics-dwf-20100529-nonfree_mod.txt)...")
    _, new_locations = parse_harmonics_file(NEWER_FILE, NUM_CONSTITUENTS_NEW)
    print(f"  Found {len(new_locations)} locations")

    print("\nParsing older file (HARMONICS_NO_US_no_us.txt)...")
    header_lines, old_locations = parse_harmonics_file(OLDER_FILE, NUM_CONSTITUENTS)
    print(f"  Found {len(old_locations)} locations")

    print("\nChecking for duplicates...")
    kept_locations = []
    deleted_locations = []

    for i, old_loc in enumerate(old_locations):
        if (i + 1) % 500 == 0:
            print(f"  Processed {i + 1}/{len(old_locations)}...")

        is_dup, reason = is_duplicate(old_loc, new_locations)

        if is_dup:
            deleted_locations.append({
                'name': old_loc['name_line'],
                'state_region': old_loc['state_region'],
                'country': old_loc['country'],
                'latitude': old_loc['latitude'],
                'longitude': old_loc['longitude'],
                'timezone': old_loc['timezone'],
                'reason': reason,
            })
        else:
            kept_locations.append(old_loc)

    print(f"\nResults:")
    print(f"  Kept: {len(kept_locations)}")
    print(f"  Deleted (duplicates): {len(deleted_locations)}")

    # Write output file
    print(f"\nWriting {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='iso-8859-1') as f:
        for line in header_lines:
            f.write(line)
        for loc in kept_locations:
            for line in loc['all_lines']:
                f.write(line)

    # Write deleted CSV
    print(f"Writing {DELETED_CSV}...")
    with open(DELETED_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow([
            'Ortsname', 'Bundesstaat/Region', 'Land',
            'Latitude', 'Longitude', 'Zeitzone', 'Löschgrund'
        ])
        for loc in deleted_locations:
            writer.writerow([
                loc['name'],
                loc['state_region'],
                loc['country'],
                loc['latitude'].replace('.', ',') if loc['latitude'] else '',
                loc['longitude'].replace('.', ',') if loc['longitude'] else '',
                loc['timezone'],
                loc['reason'],
            ])

    print("\nDone!")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Deleted list: {DELETED_CSV}")

if __name__ == '__main__':
    main()
