#!/usr/bin/env python3
"""
Script to remove duplicate stations from HARMONICS_NO_US_no_us.txt that already exist
in the newer file harmonics-dwf-20100529-nonfree_mod.txt.

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

# Known regions/states and their parent countries
REGION_TO_COUNTRY = {
    # UK regions
    'England': 'United Kingdom',
    'Scotland': 'United Kingdom',
    'Wales': 'United Kingdom',
    'Northern Ireland': 'United Kingdom',
    'Isle of Man': 'United Kingdom',
    'Channel Islands': 'United Kingdom',
    'Jersey': 'United Kingdom',
    'Shetland Islands': 'United Kingdom',
    'Western Scotland': 'United Kingdom',
    'Isle of Lewis': 'United Kingdom',
    'Isles of Scilly': 'United Kingdom',
    'Island of Mull': 'United Kingdom',
    'Islay': 'United Kingdom',
    'Gwynedd': 'United Kingdom',
    'Gwent': 'United Kingdom',
    # Canadian provinces/territories
    'British Columbia': 'Canada',
    'Nova Scotia': 'Canada',
    'Newfoundland': 'Canada',
    'New Brunswick': 'Canada',
    'Prince Edward Island': 'Canada',
    'Labrador': 'Canada',
    'Nunavut': 'Canada',
    'Manitoba': 'Canada',
    'Ontario': 'Canada',
    'Quebec': 'Canada',
    'Alberta': 'Canada',
    'Saskatchewan': 'Canada',
    # Countries (map to themselves)
    'Netherlands': 'Netherlands',
    'Germany': 'Germany',
    'Japan': 'Japan',
    'Australia': 'Australia',
    'Mexico': 'Mexico',
    'Brazil': 'Brazil',
    'France': 'France',
    'Spain': 'Spain',
    'Italy': 'Italy',
    'Belgium': 'Belgium',
    'Norway': 'Norway',
    'Sweden': 'Sweden',
    'Denmark': 'Denmark',
    'Finland': 'Finland',
    'Ireland': 'Ireland',
    'Iceland': 'Iceland',
    'Portugal': 'Portugal',
    'New Zealand': 'New Zealand',
    'China': 'China',
    'Korea': 'Korea',
    'Taiwan': 'Taiwan',
    'Philippines': 'Philippines',
    'Indonesia': 'Indonesia',
    'India': 'India',
    'South Africa': 'South Africa',
    'Argentina': 'Argentina',
    'Chile': 'Chile',
    'Peru': 'Peru',
    'Colombia': 'Colombia',
    'Ecuador': 'Ecuador',
}

# For backwards compatibility
KNOWN_COUNTRIES = list(REGION_TO_COUNTRY.keys())

def parse_location_name_full(full_name):
    """Parse location name into components: name, subregion, region/state, country

    Returns: (location_name, subregion, state_or_region, country)

    Examples:
    - "Aberdeen, Scotland" -> ("Aberdeen", "", "Scotland", "United Kingdom")
    - "Lerwick, Shetland Islands, Scotland" -> ("Lerwick", "Shetland Islands", "Scotland", "United Kingdom")
    - "Vancouver, British Columbia" -> ("Vancouver", "", "British Columbia", "Canada")
    - "Bath, Netherlands" -> ("Bath", "", "", "Netherlands")
    """
    # Clean READ suffix first
    clean_name = re.sub(r'\s*- READ.*$', '', full_name, flags=re.IGNORECASE).strip()
    # Remove (2), (3) etc. suffixes for parsing but keep for display
    clean_name_no_num = re.sub(r'\s*\(\d+\)\s*$', '', clean_name).strip()

    parts = [p.strip() for p in clean_name_no_num.split(',')]

    location_name = parts[0] if parts else full_name
    subregion = ''
    state_or_region = ''
    country = ''

    if len(parts) >= 3:
        # e.g., "Lerwick, Shetland Islands, Scotland" or "St. Helier, Jersey, Channel Islands"
        # or "Borkum, Fischerbalje, Germany"
        location_name = parts[0]

        # Check if last part maps to a country
        last_part = parts[-1].strip()
        second_last = parts[-2].strip() if len(parts) > 2 else ''

        if last_part in REGION_TO_COUNTRY:
            country = REGION_TO_COUNTRY[last_part]
            if country == last_part:
                # It's already a country (e.g., Germany, Netherlands)
                # The second_last is a subregion/district, not a state
                subregion = second_last if second_last else ''
                state_or_region = ''
            else:
                # It's a region that maps to a country (e.g., Scotland -> UK)
                state_or_region = last_part
                subregion = second_last
        else:
            # Unknown - treat last as country
            country = last_part
            state_or_region = second_last

    elif len(parts) == 2:
        # e.g., "Aberdeen, Scotland" or "Bath, Netherlands"
        # or "Bremen, Oslebshausen Germany" (country embedded without comma)
        location_name = parts[0]
        last_part = parts[-1].strip()

        # Check if last_part contains an embedded country (e.g., "Oslebshausen Germany")
        for known_region in REGION_TO_COUNTRY:
            if last_part.endswith(' ' + known_region):
                # Found embedded country/region at end
                embedded_subregion = last_part[:-len(known_region)].strip()
                mapped_country = REGION_TO_COUNTRY[known_region]
                if mapped_country == known_region:
                    # It's a country (e.g., Germany)
                    subregion = embedded_subregion
                    country = known_region
                else:
                    # It's a region (e.g., Scotland -> UK)
                    subregion = embedded_subregion
                    state_or_region = known_region
                    country = mapped_country
                break
        else:
            # No embedded country found - use standard parsing
            if last_part in REGION_TO_COUNTRY:
                mapped_country = REGION_TO_COUNTRY[last_part]
                if mapped_country == last_part:
                    # It's a country itself
                    country = last_part
                    state_or_region = ''
                else:
                    # It's a region
                    state_or_region = last_part
                    country = mapped_country
            else:
                # Unknown region/country
                country = last_part

    else:
        location_name = full_name

    return location_name, subregion, state_or_region, country

def parse_location_name(full_name):
    """Legacy function - returns (name, region, country) for compatibility"""
    loc, subregion, state, country = parse_location_name_full(full_name)
    # Combine subregion and state for the region field
    if subregion and state:
        region = f"{subregion}, {state}"
    elif subregion:
        region = subregion
    else:
        region = state
    return loc, region, country

def extract_country_from_name(full_name):
    """Extract country from location name"""
    parts = [p.strip() for p in full_name.split(',')]
    if parts:
        country = parts[-1]
        country = re.sub(r'\s*- READ.*$', '', country, flags=re.IGNORECASE).strip()
        return country
    return ''

def extract_country_flexible(name):
    """Extract country from name, handling various formats"""
    name_lower = name.lower()
    for country in KNOWN_COUNTRIES:
        if country.lower() in name_lower:
            return country
    return ''

def parse_harmonics_file(filepath):
    """Parse harmonics file and extract all stations"""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    lines = content.split('\n')
    stations = []

    station_pattern = re.compile(r'^[A-Z][a-z][^#\n]*[a-zA-Z\)]$')
    constituent_names = {'J1', 'K1', 'K2', 'L2', 'M1', 'M2', 'M3', 'M4', 'M6', 'M8',
                         'N2', 'O1', 'P1', 'Q1', 'R2', 'S1', 'S2', 'S4', 'S6', 'T2',
                         'MF', 'MM', 'SA', 'SSA'}

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line or line.startswith('#'):
            i += 1
            continue

        if station_pattern.match(line) and (',' in line or ' ' in line):
            first_word = line.split()[0] if line.split() else ''
            if first_word not in constituent_names:
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

                if has_coords:
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
                    for j in range(max(0, i-30), i):
                        if '# !latitude:' in lines[j] or '# !longitude:' in lines[j]:
                            station_lines.append(i)
                            break

    # First pass: find start of each station's comment block
    station_starts = []
    for station_line in station_lines:
        start = station_line
        for j in range(station_line - 1, max(0, station_line - 100), -1):
            line = lines[j].strip()
            if line.startswith('#'):
                start = j
            elif not line:
                start = j
            else:
                # Non-comment, non-empty line (e.g., "x 0 0" or constituent data)
                break
        station_starts.append(start)

    # Second pass: create blocks - end of current block = start of next block
    for idx, station_line in enumerate(station_lines):
        start = station_starts[idx]

        if idx + 1 < len(station_lines):
            # End is the start of the next station's block (removes entire block incl. comments)
            end = station_starts[idx + 1]
        else:
            end = len(lines)

        blocks.append({
            'start': start,
            'end': end,
            'name_line': station_line
        })

    return blocks

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

    flex_country1 = extract_country_flexible(name1)
    flex_country2 = extract_country_flexible(name2)

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

    # Criterion 4: Minor variations
    norm_name1 = normalize_name(name1)
    norm_name2 = normalize_name(name2)
    if norm_name1 == norm_name2:
        return True, f"Normalized name match: {name1}"

    norm_name1_flex = re.sub(r'[\s,]+', ' ', normalize_name(name1)).strip()
    norm_name2_flex = re.sub(r'[\s,]+', ' ', normalize_name(name2)).strip()
    if norm_name1_flex == norm_name2_flex:
        return True, f"Flexible normalized name match: {name1}"

    # Criterion 5: Similar name + same timezone + coordinates within 1km
    if station1['timezone'] and station2['timezone']:
        tz1 = station1['timezone'].split()[0] if station1['timezone'] else ''
        tz2 = station2['timezone'].split()[0] if station2['timezone'] else ''

        if tz1 == tz2:
            if (station1['latitude'] is not None and station1['longitude'] is not None and
                station2['latitude'] is not None and station2['longitude'] is not None):
                distance = haversine_distance(
                    station1['latitude'], station1['longitude'],
                    station2['latitude'], station2['longitude']
                )
                if distance < 1.0 and norm_loc1 == norm_loc2:
                    return True, f"Same location, timezone and coords within {distance:.2f}km"

    return False, ""

def main():
    base_dir = '/home/oliver/harmonics'
    new_file = os.path.join(base_dir, 'harmonics-dwf-20070318.txt')
    old_file = os.path.join(base_dir, 'HARMONICS_NO_US_no_us_no_dupes.txt')
    output_file = os.path.join(base_dir, 'HARMONICS_NO_US_no_us_no_dupes2.txt')
    csv_file = os.path.join(base_dir, 'deleted_stations_2007.csv')

    print(f"Parsing newer file: {new_file}")
    new_stations, new_lines = parse_harmonics_file(new_file)
    print(f"Found {len(new_stations)} stations in newer file")

    print(f"\nParsing older file: {old_file}")
    old_stations, old_lines = parse_harmonics_file(old_file)
    print(f"Found {len(old_stations)} stations in older file")

    print("\nFinding station blocks...")
    blocks = find_station_blocks(old_lines)
    print(f"Found {len(blocks)} station blocks")

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
        writer.writerow(['Ortsname', 'Unterregion', 'Bundesstaat/Region', 'Land', 'Latitude', 'Longitude', 'Zeitzone'])

        for dup in duplicates:
            station = dup['old_station']
            loc, subregion, state, country = parse_location_name_full(station['name'])

            # Parse timezone: "0:00 :Europe/London" -> "Europe/London"
            timezone = station['timezone']
            if timezone and ':' in timezone:
                # Extract just the timezone name after the second colon
                tz_parts = timezone.split(':')
                if len(tz_parts) >= 3:
                    timezone = tz_parts[2].strip()
                elif len(tz_parts) == 2 and '/' in tz_parts[1]:
                    timezone = tz_parts[1].strip()

            writer.writerow([
                loc,
                subregion,
                state,
                country,
                station['latitude'] if station['latitude'] else '',
                station['longitude'] if station['longitude'] else '',
                timezone
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
