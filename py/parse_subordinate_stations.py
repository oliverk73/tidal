#!/usr/bin/env python3
"""
Parse subordinate tide station corrections from harmonic_subordinate_corrections.idx
and export to CSV with German decimal separators.
Excludes US stations and US territories.
"""

import re
import csv

INPUT_FILE = "harmonics/harmonic_subordinate_corrections.idx"
OUTPUT_FILE = "subordinate_corrections/subordinate_stations.csv"

# US und US-Außengebiete (zu filtern)
US_CODES = {
    'US',      # USA
    'VI',      # US Virgin Islands
    'PR',      # Puerto Rico
    'GU',      # Guam
    'AS',      # American Samoa
    'MP',      # Northern Mariana Islands
    'UM',      # US Minor Outlying Islands
}

def parse_header_line(line):
    """Parse the header line (starts with t or c)"""
    # Format: tZone:Land:Region: Lon Lat TZ:TZ Name
    # Example: tEur:Neth:: 3.8333 51.3333 1:0 Terneuzen, W. Schelde Rvr

    match = re.match(r'^[tc]([^:]*):([^:]*):([^:]*):?\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+:-?\d+)\s+(.+)$', line)
    if match:
        zone = match.group(1)
        country = match.group(2)
        region = match.group(3)
        lon = match.group(4)
        lat = match.group(5)
        tz = match.group(6)
        name = match.group(7).strip()
        return {
            'zone': zone,
            'country': country,
            'region': region,
            'lon': lon,
            'lat': lat,
            'tz': tz,
            'name': name
        }
    return None

def parse_correction_line(line):
    """Parse the correction line (starts with &)"""
    # Format: &Hmin Hmpy Hoff Lmin Lmpy Loff StationID [tzname] RefFileNum RefName
    # Example: &21 1 1.1 28 1 0 1529 1 Vlissingen, Netherlands
    # or with timezone: &-21 0.99 0 10 0.99 0 0 America/New_York 0 Reedy Point, Delaware

    if not line.startswith('&'):
        return None

    line = line[1:]  # Remove &
    parts = line.split()

    if len(parts) < 8:
        return None

    try:
        hmin = parts[0]
        hmpy = parts[1]
        hoff = parts[2]
        lmin = parts[3]
        lmpy = parts[4]
        loff = parts[5]

        # Find the reference station name
        # It's everything after the last number before a name
        # Look for timezone pattern (e.g., America/New_York or Pacific/Auckland or just a number)

        # Find where the reference station name starts
        # The pattern is: ... StationID [tzname] RefFileNum RefName
        # We need to find RefName which is at the end

        remaining = parts[6:]

        # Find the last standalone number - that's RefFileNum
        # Everything after it is RefName
        ref_file_num_idx = -1
        for i in range(len(remaining) - 1, -1, -1):
            # Check if this is a number and the next item starts a name
            if remaining[i].isdigit() and i < len(remaining) - 1:
                # Check if remaining items form a name (not a timezone)
                potential_name = ' '.join(remaining[i+1:])
                if not remaining[i+1].replace('/', '_').replace('-', '_').replace('_', '').isalpha() or '/' not in remaining[i+1]:
                    ref_file_num_idx = i
                    break

        if ref_file_num_idx == -1:
            # Fallback: assume last number is RefFileNum
            for i in range(len(remaining) - 1, -1, -1):
                if remaining[i].isdigit():
                    ref_file_num_idx = i
                    break

        if ref_file_num_idx >= 0 and ref_file_num_idx < len(remaining) - 1:
            ref_name = ' '.join(remaining[ref_file_num_idx + 1:])
        else:
            ref_name = ''

        return {
            'hmin': hmin,
            'hmpy': hmpy,
            'hoff': hoff,
            'lmin': lmin,
            'lmpy': lmpy,
            'loff': loff,
            'ref_name': ref_name
        }
    except (ValueError, IndexError) as e:
        print(f"Error parsing line: {line} - {e}")
        return None

def german_decimal(value):
    """Convert decimal point to comma for German locale"""
    return str(value).replace('.', ',')

def main():
    stations = []

    with open(INPUT_FILE, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    i = 0
    skipped_us = 0
    total = 0

    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines
        if not line:
            i += 1
            continue

        # Check if this is a header line (starts with t or c)
        if line.startswith('t') or line.startswith('c'):
            header = parse_header_line(line)

            if header:
                total += 1

                # Check if it's a US station
                if header['country'] in US_CODES:
                    skipped_us += 1
                    i += 2  # Skip header and correction line
                    continue

                # Read the next line for corrections
                if i + 1 < len(lines):
                    correction_line = lines[i + 1].strip()
                    if correction_line.startswith('&'):
                        correction = parse_correction_line(correction_line)

                        if correction:
                            stations.append({
                                'name': header['name'],
                                'ref_name': correction['ref_name'],
                                'lon': header['lon'],
                                'lat': header['lat'],
                                'tz': header['tz'],
                                'hmin': correction['hmin'],
                                'hmpy': correction['hmpy'],
                                'hoff': correction['hoff'],
                                'lmin': correction['lmin'],
                                'lmpy': correction['lmpy'],
                                'loff': correction['loff'],
                            })
                        i += 2
                        continue

        i += 1

    # Write to CSV with German decimal separators
    with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')  # Use semicolon for German Excel compatibility

        # Header
        writer.writerow([
            'Station Name',
            'Reference Station',
            'Longitude',
            'Latitude',
            'Timezone',
            'Hmin (High Tide Time Add)',
            'Hmpy (High Tide Level Multiply)',
            'Hoff (High Tide Level Add)',
            'Lmin (Low Tide Time Add)',
            'Lmpy (Low Tide Level Multiply)',
            'Loff (Low Tide Level Add)'
        ])

        # Data rows with German decimal format
        for station in stations:
            writer.writerow([
                station['name'],
                station['ref_name'],
                german_decimal(station['lon']),
                german_decimal(station['lat']),
                station['tz'],
                station['hmin'],
                german_decimal(station['hmpy']),
                german_decimal(station['hoff']),
                station['lmin'],
                german_decimal(station['lmpy']),
                german_decimal(station['loff'])
            ])

    print(f"Verarbeitet: {total} Stationen")
    print(f"US-Stationen übersprungen: {skipped_us}")
    print(f"Exportiert: {len(stations)} Stationen")
    print(f"Ausgabedatei: {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
