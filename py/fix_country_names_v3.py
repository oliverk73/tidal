#!/usr/bin/env python3
"""
Convert European country names to their native language forms (Latin script).
Countries with non-Latin original scripts keep their latinized form.
"""

import re

# Countries found in file that need conversion
# English -> Native language (Latin script only)
CONVERSIONS = [
    # European countries
    ('Italy', 'Italia'),               # Italian
    ('Netherlands', 'Nederland'),       # Dutch
    ('Belgium', 'Belgie'),              # Dutch (could also be Belgique in French)
    ('Croatia', 'Hrvatska'),            # Croatian
    ('Slovenia', 'Slovenija'),          # Slovenian
    ('Iceland', 'Island'),              # Icelandic

    # African countries with French/Portuguese as official language
    ('Cameroon', 'Cameroun'),           # French
    ('Mozambique', 'Mocambique'),       # Portuguese

    # Asian countries with Latin-script based languages
    ('Philippines', 'Pilipinas'),       # Filipino/Tagalog
    ('Vietnam', 'Viet Nam'),            # Vietnamese

    # Countries that stay the same (Latin script, same spelling):
    # France, Portugal (same in native language)

    # Countries that keep English form (non-Latin original script):
    # United Kingdom (English is native)
    # Japan, China, etc. (non-Latin scripts)
]

def process_file(input_file, output_file):
    """Process the harmonics file and convert country names."""
    with open(input_file, 'r', encoding='latin-1') as f:
        content = f.read()

    modifications = []

    for english, native in CONVERSIONS:
        if english != native:
            # Match at end of line
            pattern = f', {re.escape(english)}$'
            replacement = f', {native}'

            # Count occurrences before replacement
            matches = re.findall(pattern, content, re.MULTILINE)
            if matches:
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
                modifications.append((english, native, len(matches)))

    # Write output
    with open(output_file, 'w', encoding='latin-1') as f:
        f.write(content)

    # Print summary
    print("Modifications made:")
    print("="*60)
    total = 0
    for english, native, count in modifications:
        print(f"  {english} -> {native}: {count} occurrences")
        total += count
    print("="*60)
    print(f"Total modifications: {total}")

    return modifications

if __name__ == '__main__':
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'

    print("Converting European country names to native language forms...")
    print()
    process_file(input_file, output_file)
    print(f"\nFile updated: {output_file}")
