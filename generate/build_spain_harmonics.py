#!/usr/bin/env python3
"""
Generates a complete XTide harmonics text file for Spanish tide stations.
Reads harmonic constants from XLSX files and metadata from an ODS file.
Output: /home/oliver/harmonics/harmonics_puertos_spain.txt
"""

import os
import re
import sys
import math
import unicodedata
import pandas as pd

# Paths
SPAIN_DIR = '/home/oliver/harmonics/help/Spain/'
ODS_FILE = os.path.join(SPAIN_DIR, 'tide_stations_spain.ods')
TEMPLATE_FILE = '/home/oliver/harmonics/utide/harmonics_template.txt'
OUTPUT_FILE = '/home/oliver/harmonics/ihm/harmonics_puertos_spain.txt'


def strip_accents(s):
    """Remove accents from a string for case-insensitive matching."""
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def read_template_header(template_path):
    """Read the template header up to and including the line after the second
    'MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.' line."""
    lines = []
    count = 0
    skip_lines = [
        '# Output of restore_tide_db.',
        '# This file was converted from',
        '# at 2025-07-21',
    ]
    with open(template_path, 'r', encoding='iso-8859-1') as f:
        for line in f:
            stripped = line.rstrip('\n')
            # Skip restore_tide_db output lines
            if any(stripped.startswith(s) for s in skip_lines):
                continue
            lines.append(stripped)
            if 'MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.' in line:
                count += 1
                if count == 2:
                    break
    return lines


def read_constituent_order(template_path):
    """Read the 175 constituent names in order from the template file."""
    constituents = []
    in_speeds = False
    with open(template_path, 'r', encoding='iso-8859-1') as f:
        for line in f:
            line = line.strip()
            if line == '# Constituent speeds':
                in_speeds = True
                continue
            if in_speeds and line == '175':
                # Skip the count line and format comment lines
                continue
            if in_speeds and line.startswith('#'):
                # Skip comment lines within the speeds section
                if '# Starting year' in line:
                    break
                continue
            if in_speeds:
                # Parse constituent name (first whitespace-separated token)
                parts = line.split()
                if len(parts) >= 2:
                    constituents.append(parts[0])
                if len(constituents) == 175:
                    break
    return constituents


def read_xlsx_harmonics(xlsx_path):
    """Read harmonic constants from an XLSX file.
    Returns dict: constituent_name -> (amplitude_meters, phase_degrees)
    and z0_meters."""
    df = pd.read_excel(xlsx_path, header=None)
    harmonics = {}
    z0_meters = 0.0

    for i in range(2, len(df)):
        name = str(df.iloc[i, 0]).strip()
        amplitude_cm = float(df.iloc[i, 2])
        phase = float(df.iloc[i, 3])
        amplitude_m = amplitude_cm / 100.0

        if name == 'Z0':
            z0_meters = amplitude_m
        else:
            harmonics[name] = (amplitude_m, phase)

    return harmonics, z0_meters


def extract_station_name_from_filename(filename):
    """Extract station name from XLSX filename."""
    m = re.search(r'Mare[oó]grafo_de_(.+?)-Armonicos', filename)
    if m:
        return m.group(1).replace('_', ' ')
    return None


def get_timezone(station_num, longitude):
    """Determine timezone based on station number and longitude."""
    station_num = int(station_num)
    if 3450 <= station_num <= 3471 or longitude < -13:
        return '+00:00', 'Atlantic/Canary'
    elif station_num == 3510:
        return '+01:00', 'Africa/Ceuta'
    else:
        return '+01:00', 'Europe/Madrid'


def format_value(val):
    """Format a metadata value, return None if empty/NaN."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    s = str(val).strip()
    if s == '' or s.lower() == 'nan':
        return None
    return s


def build_station_block(row, harmonics, z0_meters, constituent_order):
    """Build the text block for one station."""
    lines = []

    station_num = int(row['#'])
    official_name = str(row['official name in files']).strip()
    harmonics_name = str(row['harmonics name']).strip()
    latitude = str(row['latitude']).strip()
    longitude = str(row['longitude']).strip()
    lon_float = float(longitude)

    # Comment block
    lines.append('# Station data from Puertos del Estado (Spain)')
    lines.append(f'# Station number: {station_num}')
    lines.append(f'# Official name: {official_name}')

    # Optional metadata fields
    meta_fields = [
        ('Cota bajo clavo de referencia', 'Cota bajo clavo de referencia'),
        ('cero geodésico nacional (IGN)', 'Cero geodésico nacional (IGN)'),
        ('cero hidrográfico', 'Cero hidrográfico'),
        ('Para referir al elipsoide (WGS84)', 'Para referir al elipsoide (WGS84)'),
    ]
    for col_name, label in meta_fields:
        val = format_value(row.get(col_name))
        if val is not None:
            lines.append(f'# {label}: {val} m')

    lines.append('# source: Puertos del Estado, Spain')
    lines.append('# date_imported: 20260317')

    # HOT COMMENTS
    lines.append('# BEGIN HOT COMMENTS')
    lines.append('# country: Spain')
    lines.append('# source: Puertos del Estado harmonic analysis')
    lines.append('# restriction: Non-commercial use only')
    lines.append('# station_id_context: Puertos del Estado')
    lines.append('# datum: Cero Hidrográfico')
    lines.append('# confidence: 8')
    lines.append('# !units: meters')
    lines.append(f'# !longitude: {longitude}')
    lines.append(f'# !latitude: {latitude}')

    # Station name line
    lines.append(harmonics_name)

    # Timezone
    utc_offset, tz_name = get_timezone(station_num, lon_float)
    lines.append(f'{utc_offset} :{tz_name}')

    # Z0 / datum line
    lines.append(f'{z0_meters:.4f} meters')

    # Constituent lines - must match template order exactly
    # Build a mapping that handles aliases
    # Template aliases: ETA2/KJ2 (pos 109), EPS2/MNS2 (pos 117)
    for const_name in constituent_order:
        if const_name in harmonics:
            amp, phase = harmonics[const_name]
            lines.append(f'{const_name} {amp:.4f} {phase}')
        else:
            # Check aliases - only for constituents that share the same
            # frequency and are true aliases in the template
            aliases = {
                'KJ2': 'ETA2',
                'ETA2': 'KJ2',
                'MNS2': 'EPS2',
                'EPS2': 'MNS2',
            }
            alias = aliases.get(const_name)
            if alias and alias in harmonics:
                amp, phase = harmonics[alias]
                lines.append(f'{const_name} {amp:.4f} {phase}')
            else:
                lines.append(f'x 0 0')

    return '\n'.join(lines)


def main():
    # Read constituent order from template
    constituent_order = read_constituent_order(TEMPLATE_FILE)
    if len(constituent_order) != 175:
        print(f'ERROR: Expected 175 constituents, got {len(constituent_order)}')
        sys.exit(1)
    print(f'Read {len(constituent_order)} constituents from template')

    # Read template header
    header_lines = read_template_header(TEMPLATE_FILE)
    print(f'Read {len(header_lines)} header lines from template')

    # Read ODS metadata
    ods_df = pd.read_excel(ODS_FILE, engine='odf', header=0)
    print(f'Read {len(ods_df)} stations from ODS file')

    # Build lookup: normalized name -> row index
    ods_lookup = {}
    for i, row in ods_df.iterrows():
        name = str(row['official name in files']).strip()
        normalized = strip_accents(name).lower()
        ods_lookup[normalized] = i

    # Find all XLSX files
    xlsx_files = [f for f in os.listdir(SPAIN_DIR) if f.endswith('.xlsx')]
    print(f'Found {len(xlsx_files)} XLSX files')

    # Process each XLSX file
    station_blocks = []
    matched = 0
    unmatched_xlsx = []
    processed_ods_indices = set()

    for xlsx_file in sorted(xlsx_files):
        xlsx_path = os.path.join(SPAIN_DIR, xlsx_file)
        station_name = extract_station_name_from_filename(xlsx_file)
        if station_name is None:
            print(f'  WARNING: Could not extract station name from {xlsx_file}')
            unmatched_xlsx.append(xlsx_file)
            continue

        # Normalize for matching
        normalized = strip_accents(station_name).lower()

        # Find in ODS
        if normalized not in ods_lookup:
            print(f'  WARNING: No ODS match for "{station_name}" (normalized: "{normalized}")')
            unmatched_xlsx.append(xlsx_file)
            continue

        ods_idx = ods_lookup[normalized]
        row = ods_df.iloc[ods_idx]
        processed_ods_indices.add(ods_idx)

        # Read XLSX harmonics
        try:
            harmonics, z0_meters = read_xlsx_harmonics(xlsx_path)
        except Exception as e:
            print(f'  ERROR reading {xlsx_file}: {e}')
            unmatched_xlsx.append(xlsx_file)
            continue

        # Build station block
        block = build_station_block(row, harmonics, z0_meters, constituent_order)
        station_blocks.append(block)
        matched += 1

    # Write output file
    with open(OUTPUT_FILE, 'w', encoding='iso-8859-1') as f:
        # Write header (ends with "# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.")
        for line in header_lines:
            f.write(line + '\n')
        # build_tide_db expects a lone "#" line after the header
        f.write('#\n')

        # Write station blocks — no extra blank lines between them!
        # Each block ends with its last constituent line.
        # The next block starts with a # comment line.
        for block in station_blocks:
            f.write(block + '\n')

    # Summary
    print(f'\n=== Summary ===')
    print(f'Stations processed successfully: {matched}')
    print(f'XLSX files that failed to match: {len(unmatched_xlsx)}')
    for f in unmatched_xlsx:
        print(f'  - {f}')

    # ODS stations without XLSX
    unmatched_ods = []
    for i, row in ods_df.iterrows():
        if i not in processed_ods_indices:
            unmatched_ods.append(str(row['official name in files']).strip())
    if unmatched_ods:
        print(f'ODS stations without XLSX data ({len(unmatched_ods)}):')
        for name in unmatched_ods:
            print(f'  - {name}')

    print(f'\nOutput written to: {OUTPUT_FILE}')


if __name__ == '__main__':
    main()
