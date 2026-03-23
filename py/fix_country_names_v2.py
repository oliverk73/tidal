#!/usr/bin/env python3
"""
Fix station names - restore native language country names and add missing ones.
Country names should be in Latin script but in the local language.
"""

import re

# Corrections: restore native language names that were wrongly anglicized
# and add country names only where truly missing
FIXES = [
    # Restore native language names that were wrongly changed to English
    (r', Norway$', ', Norge', True),  # Restore Norwegian
    (r', Spain$', ', Espana', True),  # Restore Spanish
    (r', Brazil$', ', Brasil', True),  # Restore Portuguese
    (r', Sao Tome and Principe$', ', Sao Tome e Principe', True),  # Restore Portuguese
    (r', Democratic Republic of the Congo$', ', Republique Democratique du Congo', True),  # Restore French
    (r', Republic of the Congo$', ', Republique du Congo', True),  # Use French

    # U.A.E. - Arabic script isn't Latin, so use English transliteration
    # Already changed to "United Arab Emirates" - this is acceptable for non-Latin script countries

    # Scotland - English is the local language, so "United Kingdom" is correct
    # These changes were correct

    # Curacao was a typo fix (Curaao -> Curacao), that's correct

    # Gibraltar - was "Gibraltar (U.K.) (2)" -> "Gibraltar, United Kingdom"
    # Should probably be just "Gibraltar" as it's a British Overseas Territory
    # But adding UK is acceptable since English is spoken there
]

def fix_station_name(name):
    """Apply fixes to a station name."""
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
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'

    print("Restoring native language country names...")
    modifications = process_file(input_file, output_file)
    print(f"\nFile updated: {output_file}")
