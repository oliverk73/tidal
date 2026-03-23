#!/usr/bin/env python3
"""
Fix country names to include proper diacritics/special characters.
File is encoded in Latin-1 (ISO-8859-1).
"""

import re

# Country names with correct diacritics (Latin-1 compatible)
DIACRITIC_FIXES = [
    ('Espana', 'España'),           # Spanish ñ
    ('Mocambique', 'Moçambique'),   # Portuguese ç
    ('Belgie', 'België'),           # Dutch ë
    ('Island', 'Ísland'),           # Icelandic Í
    ('Turkiye', 'Türkiye'),         # Turkish ü
    ('Oesterreich', 'Österreich'),  # German Ö
    ('Cesko', 'Česko'),             # Czech - but č is not in Latin-1!
]

# Check Latin-1 compatibility
def is_latin1_compatible(s):
    try:
        s.encode('latin-1')
        return True
    except UnicodeEncodeError:
        return False

def process_file(input_file, output_file):
    """Process the harmonics file and add diacritics to country names."""
    with open(input_file, 'r', encoding='latin-1') as f:
        content = f.read()

    modifications = []
    skipped = []

    for old_name, new_name in DIACRITIC_FIXES:
        if not is_latin1_compatible(new_name):
            skipped.append((old_name, new_name, "not Latin-1 compatible"))
            continue

        # Match at end of line
        pattern = f', {re.escape(old_name)}$'
        replacement = f', {new_name}'

        # Count occurrences before replacement
        matches = re.findall(pattern, content, re.MULTILINE)
        if matches:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            modifications.append((old_name, new_name, len(matches)))

    # Write output
    with open(output_file, 'w', encoding='latin-1') as f:
        f.write(content)

    # Print summary
    print("Modifications made:")
    print("="*60)
    total = 0
    for old_name, new_name, count in modifications:
        print(f"  {old_name} -> {new_name}: {count} occurrences")
        total += count
    print("="*60)
    print(f"Total modifications: {total}")

    if skipped:
        print("\nSkipped (not Latin-1 compatible):")
        for old_name, new_name, reason in skipped:
            print(f"  {old_name} -> {new_name}: {reason}")

    return modifications

if __name__ == '__main__':
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'

    print("Adding diacritics to country names...")
    print()
    process_file(input_file, output_file)
    print(f"\nFile updated: {output_file}")
