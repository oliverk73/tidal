#!/usr/bin/env python3
"""
Remove US locations from harmonics file.
Removes:
- US states
- US territories (Puerto Rico, Guam, American Samoa, US Virgin Islands, etc.)
- Freely associated states (Marshall Islands, Micronesia, Palau)
"""

import re
import csv

INPUT_FILE = "harmonics/HARMONICS_NO_US.txt"
OUTPUT_FILE = "harmonics/HARMONICS_NO_US_no_us.txt"
DELETED_CSV = "deleted_us_locations.csv"
NUM_CONSTITUENTS = 173

# US States (full names and common abbreviations in location names)
US_STATES = {
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
    'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
    'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
    'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
    'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
    'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
    'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
    'West Virginia', 'Wisconsin', 'Wyoming',
    # District
    'District of Columbia', 'D.C.',
}

# US Territories
US_TERRITORIES = {
    'Puerto Rico', 'Guam', 'American Samoa', 'U.S. Virgin Islands',
    'US Virgin Islands', 'Virgin Islands', 'Northern Mariana Islands',
    'Wake Island', 'Midway Islands', 'Midway Island', 'Johnston Atoll',
    'Palmyra Atoll', 'Baker Island', 'Howland Island', 'Jarvis Island',
    'Kingman Reef', 'Navassa Island',
}

# Freely Associated States (to be removed)
ASSOCIATED_STATES = {
    'Marshall Islands', 'Micronesia', 'F.S.M.', 'Palau', 'Palau Islands',
}

# US Timezones (used to identify US locations)
US_TIMEZONES = {
    'America/New_York', 'America/Chicago', 'America/Denver',
    'America/Los_Angeles', 'America/Anchorage', 'America/Juneau',
    'America/Sitka', 'America/Yakutat', 'America/Nome', 'America/Adak',
    'America/Metlakatla', 'America/Phoenix', 'America/Boise',
    'America/Indiana/Indianapolis', 'America/Indiana/Knox',
    'America/Indiana/Marengo', 'America/Indiana/Petersburg',
    'America/Indiana/Tell_City', 'America/Indiana/Vevay',
    'America/Indiana/Vincennes', 'America/Indiana/Winamac',
    'America/Kentucky/Louisville', 'America/Kentucky/Monticello',
    'America/Detroit', 'America/Menominee', 'America/North_Dakota/Beulah',
    'America/North_Dakota/Center', 'America/North_Dakota/New_Salem',
    'Pacific/Honolulu', 'Pacific/Guam', 'Pacific/Pago_Pago',
    'Pacific/Wake', 'Pacific/Midway', 'Pacific/Johnston',
    'America/Puerto_Rico', 'America/Virgin',
    # Also check for Atka (Alaska)
    'America/Atka',
}

# Sovereign countries in Americas (NOT to be removed even with America/ timezone)
SOVEREIGN_COUNTRIES = {
    'Canada', 'Mexico', 'Belize', 'Guatemala', 'Honduras', 'El Salvador',
    'Nicaragua', 'Costa Rica', 'Panama', 'Cuba', 'Jamaica', 'Haiti',
    'Dominican Republic', 'Bahamas', 'Trinidad and Tobago', 'Barbados',
    'Saint Lucia', 'Grenada', 'Saint Vincent', 'Antigua', 'Dominica',
    'Saint Kitts', 'Colombia', 'Venezuela', 'Ecuador', 'Peru', 'Brazil',
    'Bolivia', 'Paraguay', 'Uruguay', 'Argentina', 'Chile', 'Guyana',
    'Suriname', 'French Guiana',
    # Canadian provinces
    'British Columbia', 'Alberta', 'Saskatchewan', 'Manitoba', 'Ontario',
    'Quebec', 'Québec', 'New Brunswick', 'Nova Scotia', 'Prince Edward Island',
    'Newfoundland', 'Yukon', 'Northwest Territories', 'Nunavut',
    # Mexican states
    'Baja California', 'Sonora', 'Chihuahua', 'Coahuila', 'Nuevo León',
    'Tamaulipas', 'Sinaloa', 'Durango', 'Zacatecas', 'Nayarit', 'Jalisco',
    'Aguascalientes', 'San Luis Potosí', 'Guanajuato', 'Querétaro',
    'Hidalgo', 'Veracruz', 'Puebla', 'Tlaxcala', 'Oaxaca', 'Chiapas',
    'Tabasco', 'Campeche', 'Yucatán', 'Quintana Roo', 'Guerrero',
    'Michoacán', 'Colima', 'México', 'Morelos',
}

def is_us_location(name, timezone, country_hint=None):
    """
    Determine if a location is in the US or US territories.
    Returns (is_us, reason)
    """
    name_upper = name.upper()

    # Clean name for matching (remove suffixes like (2), (3), etc. and "- READ...")
    clean_name = re.sub(r'\s*\(\d+\)\s*$', '', name)
    clean_name = re.sub(r'\s*-\s*READ.*$', '', clean_name, flags=re.IGNORECASE)

    # Check for US states in the location name
    for state in US_STATES:
        # Match state at end of name or followed by comma/parenthesis
        patterns = [
            f", {state}$",
            f", {state} ",
            f", {state},",
            f", {state}\\(",
            f"\\({state}\\)",
            f", {state} \\(",
            f", {state} Current$",
            f", {state} Current ",
        ]
        for pattern in patterns:
            if re.search(pattern, clean_name, re.IGNORECASE):
                return True, f"US State: {state}"
            if re.search(pattern, name, re.IGNORECASE):
                return True, f"US State: {state}"

    # Check for US territories
    for territory in US_TERRITORIES:
        if territory.lower() in name.lower():
            return True, f"US Territory: {territory}"

    # Check for associated states
    for assoc in ASSOCIATED_STATES:
        if assoc.lower() in name.lower():
            return True, f"Associated State: {assoc}"

    # Check timezone - but only if it's a US timezone AND not a sovereign country
    if timezone:
        tz_clean = timezone.strip().replace(':', '').lstrip('+-0123456789 ')

        if tz_clean in US_TIMEZONES:
            # Check if it's actually a sovereign country
            for country in SOVEREIGN_COUNTRIES:
                if country.lower() in name.lower():
                    return False, None

            # It's a US timezone and not a sovereign country
            return True, f"US Timezone: {tz_clean}"

    return False, None

def extract_location_info(comment_lines, info_lines):
    """Extract location information from comment and info lines."""
    info = {
        'name': '',
        'state_region': '',
        'country': '',
        'latitude': '',
        'longitude': '',
        'timezone': '',
        'units': '',
    }

    # Parse comment lines
    for line in comment_lines:
        if '!latitude:' in line:
            match = re.search(r'!latitude:\s*(-?\d+\.?\d*)', line)
            if match:
                info['latitude'] = match.group(1)
        elif '!longitude:' in line:
            match = re.search(r'!longitude:\s*(-?\d+\.?\d*)', line)
            if match:
                info['longitude'] = match.group(1)
        elif '!units:' in line:
            match = re.search(r'!units:\s*(\w+)', line)
            if match:
                info['units'] = match.group(1)
        elif 'country:' in line.lower():
            match = re.search(r'country:\s*(.+)', line, re.IGNORECASE)
            if match:
                info['country'] = match.group(1).strip()

    # Parse info lines
    if len(info_lines) >= 1:
        name_line = info_lines[0].strip()
        info['name'] = name_line

        # Try to extract state/region and country from name
        parts = name_line.split(',')
        if len(parts) >= 2:
            # Last part might be country
            last_part = parts[-1].strip()
            # Remove (2), (3), etc. and "- READ flaterco.com/pol.html"
            last_part = re.sub(r'\s*\(\d+\)\s*', '', last_part)
            last_part = re.sub(r'\s*-\s*READ.*', '', last_part)
            info['country'] = last_part.strip()

            if len(parts) >= 3:
                info['state_region'] = parts[-2].strip()

    if len(info_lines) >= 2:
        tz_line = info_lines[1].strip()
        info['timezone'] = tz_line

    return info

def parse_harmonics_file(filename):
    """Parse the harmonics file and yield data blocks."""
    with open(filename, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    # Normalize line endings
    lines = [line.replace('\r\n', '\n').replace('\r', '\n') for line in lines]

    # Find the start of data blocks (after "MERCHANTABILITY" line)
    data_start = 0
    for i, line in enumerate(lines):
        if 'MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE' in line:
            data_start = i + 1
            break

    # Find header end (everything before data blocks)
    header_lines = lines[:data_start]

    # Parse data blocks
    i = data_start
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines
        if not line:
            i += 1
            continue

        # Check if this is a comment line (start of a new block)
        if line.startswith('#'):
            block_start = i
            comment_lines = []

            # Collect comment lines (including empty comment lines)
            while i < len(lines):
                current = lines[i].strip()
                if current.startswith('#') or current == '':
                    comment_lines.append(lines[i])
                    i += 1
                    # If we hit a non-comment, non-empty line, we're at the info section
                    if i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('#'):
                        break
                else:
                    break

            # Remove trailing empty lines from comment_lines
            while comment_lines and not comment_lines[-1].strip():
                comment_lines.pop()

            # Collect info lines (3 lines: name, timezone, datum)
            info_lines = []
            for _ in range(3):
                if i < len(lines) and not lines[i].strip().startswith('#'):
                    info_lines.append(lines[i])
                    i += 1
                else:
                    break

            # Only process if we have valid info lines
            if len(info_lines) >= 1 and info_lines[0].strip():
                # Collect constituent lines (NUM_CONSTITUENTS lines)
                constituent_lines = []
                for _ in range(NUM_CONSTITUENTS):
                    if i < len(lines):
                        constituent_lines.append(lines[i])
                        i += 1
                    else:
                        break

                # Yield the complete block
                block_lines = comment_lines + info_lines + constituent_lines
                yield {
                    'comment_lines': comment_lines,
                    'info_lines': info_lines,
                    'constituent_lines': constituent_lines,
                    'all_lines': block_lines,
                    'start_line': block_start,
                }
        else:
            i += 1

    # Also yield the header
    yield {
        'header': header_lines,
    }

def main():
    print("Parsing harmonics file...")

    blocks = list(parse_harmonics_file(INPUT_FILE))

    # Separate header from data blocks
    header = None
    data_blocks = []
    for block in blocks:
        if 'header' in block:
            header = block['header']
        else:
            data_blocks.append(block)

    print(f"Found {len(data_blocks)} data blocks")

    # Process blocks
    kept_blocks = []
    deleted_locations = []

    for block in data_blocks:
        info = extract_location_info(block['comment_lines'], block['info_lines'])

        is_us, reason = is_us_location(
            info['name'],
            info['timezone'],
            info.get('country')
        )

        if is_us:
            deleted_locations.append({
                'name': info['name'],
                'state_region': info['state_region'],
                'country': info['country'],
                'latitude': info['latitude'],
                'longitude': info['longitude'],
                'timezone': info['timezone'],
                'reason': reason,
            })
        else:
            kept_blocks.append(block)

    print(f"Kept: {len(kept_blocks)} locations")
    print(f"Deleted: {len(deleted_locations)} US locations")

    # Write output file
    print(f"\nWriting {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='iso-8859-1') as f:
        # Write header
        if header:
            for line in header:
                f.write(line)

        # Write kept blocks
        for block in kept_blocks:
            for line in block['all_lines']:
                f.write(line)

    # Write deleted locations CSV
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
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Deleted locations: {DELETED_CSV}")

if __name__ == '__main__':
    main()
