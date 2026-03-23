#!/usr/bin/env python3
"""
Script to remove duplicate stations from HARMONICS_no_us2_no_dupes.txt that already exist
in the newer file harmonics-dwf-20070318_no_us_no_dupes.txt.

Duplicate criteria:
1. Exact match of location name line
2. Same location name + country
3. Same location name + state/region
4. Minor variations (special chars, (2), (3), "- READ flaterco.com/pol.html")
5. Similar name + same timezone + coordinates within 1km
"""

import re
import os
import csv
import unicodedata
from math import radians, sin, cos, sqrt, atan2

# Haversine formula to calculate distance between two points
def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two lat/lon points"""
    R = 6371  # Earth radius in km

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c

def normalize_name(name):
    """Normalize station name for comparison"""
    # Remove common suffixes/patterns
    name = re.sub(r'\s*\(2\)\s*$', '', name)
    name = re.sub(r'\s*\(3\)\s*$', '', name)
    name = re.sub(r'\s*\(4\)\s*$', '', name)
    name = re.sub(r'\s*- READ flaterco\.com/pol\.html\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*- READ.*$', '', name, flags=re.IGNORECASE)

    # Normalize unicode characters
    name = unicodedata.normalize('NFKD', name)
    # Remove accents
    name = ''.join(c for c in name if not unicodedata.combining(c))

    # Lowercase and strip
    name = name.lower().strip()

    return name

def parse_location_name(full_name):
    """Parse location name into components: name, region/state, country"""
    # Known countries to detect at end of name without comma
    known_countries = ['Germany', 'Japan', 'Australia', 'Mexico', 'Canada', 'Brazil', 'France',
                      'Spain', 'Italy', 'Netherlands', 'Belgium', 'Norway', 'Sweden', 'Denmark',
                      'Finland', 'Ireland', 'England', 'Scotland', 'Wales', 'Iceland', 'Portugal',
                      'New Zealand', 'China', 'Korea', 'Taiwan', 'Philippines', 'Indonesia',
                      'India', 'South Africa', 'Argentina', 'Chile', 'Peru', 'Colombia', 'Ecuador']

    # First try standard comma-separated parsing
    parts = [p.strip() for p in full_name.split(',')]

    # Check if the last part might contain an embedded country without comma
    # e.g., "Bremen, Oslebshausen Germany" -> parts = ["Bremen", "Oslebshausen Germany"]
    if len(parts) >= 2:
        last_part = parts[-1]
        for country in known_countries:
            if last_part.endswith(' ' + country):
                # Found embedded country - extract it
                region = last_part[:-len(country)].strip()
                return parts[0], region, country

    if len(parts) >= 3:
        name = parts[0]
        region = parts[-2] if len(parts) > 2 else ''
        country = parts[-1]
    elif len(parts) == 2:
        name = parts[0]
        region = ''
        country = parts[-1]
    else:
        name = full_name
        region = ''
        country = ''

    return name, region, country

def extract_country_from_name(full_name):
    """Extract country from location name"""
    parts = [p.strip() for p in full_name.split(',')]
    if parts:
        return parts[-1]
    return ''

def parse_station_block(lines, start_idx):
    """Parse a station data block starting at given index"""
    station = {
        'name': '',
        'full_line': '',
        'timezone': '',
        'latitude': None,
        'longitude': None,
        'country': '',
        'start_line': start_idx,
        'end_line': start_idx
    }

    i = start_idx
    # Go backwards to find metadata
    meta_start = start_idx
    while meta_start > 0 and i > 0:
        i -= 1
        line = lines[i].strip()
        if line.startswith('# !latitude:'):
            station['latitude'] = float(line.split(':')[1].strip())
            meta_start = i
        elif line.startswith('# !longitude:'):
            station['longitude'] = float(line.split(':')[1].strip())
            meta_start = i
        elif line.startswith('# country:'):
            station['country'] = line.split(':')[1].strip()
            meta_start = i
        elif line.startswith('#') and ('Data:' in line or 'pedigree' in line.lower() or 'source' in line.lower()):
            meta_start = i
        elif not line.startswith('#') and line:
            break

    station['start_line'] = meta_start
    station['full_line'] = lines[start_idx].strip()
    station['name'] = station['full_line']

    # Get timezone from next line
    if start_idx + 1 < len(lines):
        tz_line = lines[start_idx + 1].strip()
        if ':' in tz_line:
            station['timezone'] = tz_line

    # Find end of station block (next station or end of file)
    i = start_idx + 1
    while i < len(lines):
        line = lines[i].strip()
        # Check if this is a new station name line
        if line and not line.startswith('#') and not line.startswith('x ') and ',' in line:
            # Check if previous lines have coordinates (indicating new station)
            has_coords = False
            for j in range(max(0, i-20), i):
                if '# !latitude:' in lines[j] or '# !longitude:' in lines[j]:
                    has_coords = True
                    break
            if has_coords:
                break
        # Check for constituent data or end marker
        if line and not line.startswith('#') and not line.startswith('x '):
            # Could be constituent data or station name
            pass
        i += 1

    station['end_line'] = i - 1

    # Extract country if not in metadata
    if not station['country']:
        station['country'] = extract_country_from_name(station['name'])

    return station

def parse_harmonics_file(filepath):
    """Parse harmonics file and extract all stations"""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    lines = content.split('\n')
    stations = []

    # Pattern to match station name lines (not starting with #, contains comma or space,
    # ends with letter, not a constituent name)
    # Also match patterns like "Bremen, Oslebshausen Germany" (missing comma before country)
    station_pattern = re.compile(r'^[A-Z][a-z][^#\n]*[a-zA-Z\)]$')
    constituent_names = {'J1', 'K1', 'K2', 'L2', 'M1', 'M2', 'M3', 'M4', 'M6', 'M8',
                         'N2', 'O1', 'P1', 'Q1', 'R2', 'S1', 'S2', 'S4', 'S6', 'T2',
                         'MF', 'MM', 'SA', 'SSA'}

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines and comments
        if not line or line.startswith('#'):
            i += 1
            continue

        # Check if this looks like a station name
        if station_pattern.match(line) and (',' in line or ' ' in line):
            # Make sure it's not a constituent
            first_word = line.split()[0] if line.split() else ''
            if first_word not in constituent_names:
                # Look for coordinates in preceding lines
                has_coords = False
                lat, lon = None, None
                country = ''
                for j in range(max(0, i-30), i):
                    if '# !latitude:' in lines[j]:
                        try:
                            lat = float(lines[j].split(':')[1].strip())
                            has_coords = True
                        except:
                            pass
                    if '# !longitude:' in lines[j]:
                        try:
                            lon = float(lines[j].split(':')[1].strip())
                        except:
                            pass
                    if '# country:' in lines[j]:
                        country = lines[j].split(':')[1].strip()

                if has_coords:  # Valid station entry with coordinates
                    # Get timezone from next line
                    timezone = ''
                    if i + 1 < len(lines):
                        tz_line = lines[i + 1].strip()
                        if ':' in tz_line and not tz_line.startswith('#'):
                            timezone = tz_line

                    station = {
                        'name': line,
                        'latitude': lat,
                        'longitude': lon,
                        'timezone': timezone,
                        'country': country if country else extract_country_from_name(line),
                        'line_num': i
                    }
                    stations.append(station)

        i += 1

    return stations, lines

def find_station_blocks(lines):
    """Find all station blocks in the file with their line ranges"""
    blocks = []

    # Find all lines that look like station names
    # Also match patterns like "Bremen, Oslebshausen Germany" (missing comma before country)
    station_pattern = re.compile(r'^[A-Z][a-z][^#\n]*[a-zA-Z\)]$')
    constituent_names = {'J1', 'K1', 'K2', 'L2', 'M1', 'M2', 'M3', 'M4', 'M6', 'M8',
                         'N2', 'O1', 'P1', 'Q1', 'R2', 'S1', 'S2', 'S4', 'S6', 'T2',
                         'MF', 'MM', 'SA', 'SSA', 'MN4', 'MS4', 'MK3'}

    station_lines = []
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if line_stripped and not line_stripped.startswith('#'):
            if station_pattern.match(line_stripped) and (',' in line_stripped or ' ' in line_stripped):
                first_word = line_stripped.split()[0] if line_stripped.split() else ''
                if first_word not in constituent_names:
                    # Check for preceding coordinates
                    for j in range(max(0, i-30), i):
                        if '# !latitude:' in lines[j] or '# !longitude:' in lines[j]:
                            station_lines.append(i)
                            break

    # Find block boundaries
    for idx, station_line in enumerate(station_lines):
        # Find start of metadata block (go backwards)
        start = station_line
        for j in range(station_line - 1, max(0, station_line - 50), -1):
            line = lines[j].strip()
            if line.startswith('#') and ('Data:' in line or '!longitude:' in line or
                                         '!latitude:' in line or 'pedigree' in line.lower() or
                                         'source' in line.lower() or 'country:' in line.lower()):
                start = j
            elif line and not line.startswith('#'):
                break

        # Go back a bit more to include leading empty/comment lines
        while start > 0 and (not lines[start-1].strip() or lines[start-1].strip().startswith('#')):
            if start > 1 and '# !latitude:' in lines[start-2]:
                start -= 1
            elif start > 0 and lines[start-1].strip().startswith('# '):
                start -= 1
            else:
                break

        # Find end (next station start or end of file)
        if idx + 1 < len(station_lines):
            end = station_lines[idx + 1]
            # Go back to find where metadata for next station starts
            for j in range(end - 1, station_line, -1):
                line = lines[j].strip()
                if line.startswith('#') and ('Data:' in line or '!longitude:' in line or
                                             '!latitude:' in line):
                    end = j
                    break
        else:
            end = len(lines)

        blocks.append({
            'start': start,
            'end': end,
            'name_line': station_line
        })

    return blocks

def extract_country_flexible(name):
    """Extract country from name, handling cases like 'Bremen, Oslebshausen Germany'"""
    # Known countries to look for
    countries = ['Germany', 'Japan', 'Australia', 'Mexico', 'Canada', 'Brazil', 'France',
                 'Spain', 'Italy', 'Netherlands', 'Belgium', 'Norway', 'Sweden', 'Denmark',
                 'Finland', 'Ireland', 'England', 'Scotland', 'Wales', 'Iceland', 'Portugal',
                 'New Zealand', 'China', 'Korea', 'Taiwan', 'Philippines', 'Indonesia',
                 'India', 'South Africa', 'Argentina', 'Chile', 'Peru', 'Colombia', 'Ecuador',
                 'Venezuela', 'Panama', 'Costa Rica', 'Guatemala', 'Honduras', 'Nicaragua',
                 'Cuba', 'Jamaica', 'Bahamas', 'Barbados', 'Trinidad', 'Antigua', 'Bermuda']

    name_upper = name.lower()
    for country in countries:
        if country.lower() in name_upper:
            return country
    return ''

def is_duplicate(station1, station2):
    """Check if station1 is a duplicate of station2 based on the criteria"""
    name1 = station1['name']
    name2 = station2['name']

    # Criterion 1: Exact match of location name line
    if name1 == name2:
        return True, "Exact name match"

    # Parse names into components
    loc1, region1, country1 = parse_location_name(name1)
    loc2, region2, country2 = parse_location_name(name2)

    # Also try flexible country extraction for names like "Bremen, Oslebshausen Germany"
    flex_country1 = extract_country_flexible(name1)
    flex_country2 = extract_country_flexible(name2)

    # Normalize for comparison
    norm_loc1 = normalize_name(loc1)
    norm_loc2 = normalize_name(loc2)
    norm_country1 = normalize_name(country1) or normalize_name(flex_country1)
    norm_country2 = normalize_name(country2) or normalize_name(flex_country2)
    norm_region1 = normalize_name(region1)
    norm_region2 = normalize_name(region2)

    # Criterion 2: Same location name + country
    if norm_loc1 == norm_loc2 and norm_country1 and norm_country2 and norm_country1 == norm_country2:
        return True, f"Same location and country: {loc1}, {country1 or flex_country1}"

    # Criterion 3: Same location name + state/region
    if norm_loc1 == norm_loc2 and norm_region1 and norm_region2 and norm_region1 == norm_region2:
        return True, f"Same location and region: {loc1}, {region1}"

    # Criterion 4: Minor variations (special chars, (2), (3), READ string)
    norm_name1 = normalize_name(name1)
    norm_name2 = normalize_name(name2)
    if norm_name1 == norm_name2:
        return True, f"Normalized name match: {name1}"

    # Criterion 4b: Check if normalized names with flexible whitespace/comma handling match
    # Handle cases like "Bremen, Oslebshausen Germany" vs "Bremen, Oslebshausen, Germany"
    norm_name1_flex = re.sub(r'[\s,]+', ' ', normalize_name(name1)).strip()
    norm_name2_flex = re.sub(r'[\s,]+', ' ', normalize_name(name2)).strip()
    if norm_name1_flex == norm_name2_flex:
        return True, f"Flexible normalized name match: {name1}"

    # Criterion 5: Similar name + same timezone + coordinates within 1km
    if station1['timezone'] and station2['timezone']:
        # Compare timezone (just the offset part)
        tz1 = station1['timezone'].split()[0] if station1['timezone'] else ''
        tz2 = station2['timezone'].split()[0] if station2['timezone'] else ''

        if tz1 == tz2:
            if (station1['latitude'] is not None and station1['longitude'] is not None and
                station2['latitude'] is not None and station2['longitude'] is not None):
                distance = haversine_distance(
                    station1['latitude'], station1['longitude'],
                    station2['latitude'], station2['longitude']
                )
                # Check if names are similar (start with same location name)
                if distance < 1.0 and norm_loc1 == norm_loc2:
                    return True, f"Same location, timezone and coords within {distance:.2f}km"

    return False, ""

def main():
    base_dir = '/home/oliver/harmonics'
    old_file = os.path.join(base_dir, 'HARMONICS_no_us2_no_dupes.txt')
    new_file = os.path.join(base_dir, 'harmonics-dwf-20070318_no_us_no_dupes.txt')
    output_file = os.path.join(base_dir, 'HARMONICS_no_us2_no_dupes2.txt')
    csv_file = os.path.join(base_dir, 'deleted_stations.csv')

    print(f"Parsing newer file: {new_file}")
    new_stations, new_lines = parse_harmonics_file(new_file)
    print(f"Found {len(new_stations)} stations in newer file")

    print(f"\nParsing older file: {old_file}")
    old_stations, old_lines = parse_harmonics_file(old_file)
    print(f"Found {len(old_stations)} stations in older file")

    # Find station blocks in old file
    print("\nFinding station blocks...")
    blocks = find_station_blocks(old_lines)
    print(f"Found {len(blocks)} station blocks")

    # Build lookup for new stations
    new_station_lookup = {}
    for s in new_stations:
        norm_name = normalize_name(s['name'])
        new_station_lookup[norm_name] = s
        # Also add by location name only
        loc, region, country = parse_location_name(s['name'])
        new_station_lookup[normalize_name(loc)] = s

    # Find duplicates
    duplicates = []
    duplicate_lines = set()

    for i, old_station in enumerate(old_stations):
        for new_station in new_stations:
            is_dup, reason = is_duplicate(old_station, new_station)
            if is_dup:
                duplicates.append({
                    'old_station': old_station,
                    'new_station': new_station,
                    'reason': reason
                })
                duplicate_lines.add(old_station['line_num'])
                break

    print(f"\nFound {len(duplicates)} duplicate stations to remove")

    # Map duplicates to blocks
    blocks_to_remove = set()
    for dup in duplicates:
        line_num = dup['old_station']['line_num']
        for idx, block in enumerate(blocks):
            if block['name_line'] == line_num:
                blocks_to_remove.add(idx)
                break

    print(f"Blocks to remove: {len(blocks_to_remove)}")

    # Create output file without duplicate blocks
    lines_to_remove = set()
    for idx in blocks_to_remove:
        block = blocks[idx]
        for line_num in range(block['start'], block['end']):
            lines_to_remove.add(line_num)

    print(f"Lines to remove: {len(lines_to_remove)}")

    # Write cleaned file
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, line in enumerate(old_lines):
            if i not in lines_to_remove:
                f.write(line + '\n')

    print(f"\nWritten cleaned file to: {output_file}")

    # Write CSV of deleted stations
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Ortsname', 'Bundesstaat/Region', 'Land', 'Latitude', 'Longitude', 'Zeitzone'])

        for dup in duplicates:
            station = dup['old_station']
            loc, region, country = parse_location_name(station['name'])
            writer.writerow([
                loc,
                region,
                country,
                station['latitude'] if station['latitude'] else '',
                station['longitude'] if station['longitude'] else '',
                station['timezone']
            ])

    print(f"Written deleted stations CSV to: {csv_file}")

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Stations in older file: {len(old_stations)}")
    print(f"Stations in newer file: {len(new_stations)}")
    print(f"Duplicates removed: {len(duplicates)}")
    print(f"Stations remaining: {len(old_stations) - len(duplicates)}")

    print("\nDeleted stations:")
    for dup in duplicates:
        print(f"  - {dup['old_station']['name']} ({dup['reason']})")

if __name__ == '__main__':
    main()
