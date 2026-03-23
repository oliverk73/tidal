#!/usr/bin/env python3
"""
Fix station names by adding proper country names at the end.
"""

import re

# Mapping of station name endings or patterns to the correct country to add
# Format: (pattern_to_match, country_to_add, is_replacement)
# If is_replacement is True, the pattern is replaced. If False, country is appended.
FIXES = [
    # U.A.E. abbreviation -> add United Arab Emirates
    (r', U\.A\.E\.$', ', United Arab Emirates', True),

    # Scotland -> add United Kingdom
    (r', Scotland$', ', Scotland, United Kingdom', True),
    (r', Scotland \(2\)$', ', Scotland, United Kingdom', True),

    # Gibraltar already has (U.K.), keep as Gibraltar, United Kingdom
    (r'Gibraltar \(U\.K\.\) \(2\)$', 'Gibraltar, United Kingdom', True),

    # Caribisch Nederland -> add Netherlands
    (r', Caribisch Nederland$', ', Caribisch Nederland, Netherlands', True),

    # Norge -> Norway (replace with proper English name)
    (r', Norge$', ', Norway', True),

    # F.S.M. -> Federated States of Micronesia
    (r', F\.S\.M\.$', ', Micronesia', True),

    # Congo (alone, from context Brazzaville) -> Republic of the Congo
    (r', Congo$', ', Republic of the Congo', True),

    # St. Lucia -> Saint Lucia
    (r', St\. Lucia$', ', Saint Lucia', True),

    # Trinidad (2) -> Trinidad and Tobago
    (r', Trinidad \(2\)$', ', Trinidad and Tobago', True),

    # Cabo Verde -> Cape Verde
    (r', Cabo Verde$', ', Cape Verde', True),

    # Espana -> Spain
    (r', Espana$', ', Spain', True),

    # Austral Islands -> French Polynesia
    (r', Austral Islands$', ', Austral Islands, French Polynesia', True),

    # Sao Tome e Principe -> Sao Tome and Principe
    (r', Sao Tome e Principe$', ', Sao Tome and Principe', True),

    # Republique Democratique du Congo -> Democratic Republic of the Congo
    (r', Republique Democratique du Congo$', ', Democratic Republic of the Congo', True),

    # Brasil -> Brazil
    (r', Brasil$', ', Brazil', True),

    # Curaao (typo for Curacao) -> Curacao
    (r', Curaao$', ', Curacao', True),

    # les Wallis -> Wallis and Futuna (also fix capitalization)
    (r'^les Wallis$', 'Ile Wallis, Wallis and Futuna', True),

    # Singapore (Victoria Dock) (2) - Singapore is a country, add clarification
    (r'Singapore \(Victoria Dock\) \(2\)$', 'Singapore (Victoria Dock), Singapore', True),
]

def fix_station_name(name):
    """Apply fixes to a station name."""
    original_name = name
    for pattern, replacement, is_replacement in FIXES:
        if is_replacement:
            new_name = re.sub(pattern, replacement, name)
            if new_name != name:
                return new_name, True
    return name, False

def process_file(input_file, output_file):
    """Process the harmonics file and fix station names."""
    with open(input_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    modified_lines = []
    modifications = []

    for i, line in enumerate(lines):
        # Check if this is a station name line
        # Station names come after # !latitude: and before timezone line
        if (i > 0 and
            lines[i-1].startswith('# !latitude:') and
            line.strip() and
            not line.startswith('#') and
            not line.startswith('x ') and
            not line.startswith('+') and
            not line.startswith('-') and
            line[0].isalpha()):

            station_name = line.strip()
            fixed_name, was_modified = fix_station_name(station_name)

            if was_modified:
                modifications.append((i + 1, station_name, fixed_name))
                modified_lines.append(fixed_name + '\n')
            else:
                modified_lines.append(line)
        else:
            modified_lines.append(line)

    # Write output
    with open(output_file, 'w', encoding='latin-1') as f:
        f.writelines(modified_lines)

    # Print summary
    print(f"Total modifications: {len(modifications)}")
    print("\nModifications made:")
    print("="*80)
    for line_num, original, fixed in modifications:
        print(f"Line {line_num}:")
        print(f"   Original: {original}")
        print(f"   Fixed:    {fixed}")
        print()

    return modifications

if __name__ == '__main__':
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'  # Overwrite original

    print("Processing harmonics file...")
    modifications = process_file(input_file, output_file)
    print(f"\nFile updated: {output_file}")
