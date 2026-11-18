#!/usr/bin/env python3
"""
Apply reference station name mappings to idx file.
Replaces old reference station names with correct harmonics names.
"""

import csv

def apply_mappings(input_file, output_file, mapping_file):
    # Read mapping file
    mappings = {}
    with open(mapping_file, 'r', encoding='latin-1') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            ref_idx = row['ref_name_idx'].strip()
            harmonics_name = row['harmonics_name'].strip()
            status = row['status'].strip()

            # Only map if names are different and harmonics_name is not empty
            if ref_idx and harmonics_name and ref_idx != harmonics_name:
                mappings[ref_idx] = harmonics_name
                print(f"Mapping: '{ref_idx}' -> '{harmonics_name}'")

    print(f"\nTotal mappings to apply: {len(mappings)}")

    # Read idx file
    with open(input_file, 'rb') as f:
        data = f.read()

    # Decode as Latin-1
    text = data.decode('latin-1')

    # Apply mappings
    total_replacements = 0
    for old_name, new_name in mappings.items():
        # Count occurrences before replacement
        count = text.count(old_name)
        if count > 0:
            text = text.replace(old_name, new_name)
            print(f"  Replaced '{old_name}' -> '{new_name}' ({count}x)")
            total_replacements += count

    print(f"\nTotal replacements made: {total_replacements}")

    # Write output file
    with open(output_file, 'wb') as f:
        f.write(text.encode('latin-1'))

    print(f"\nOutput written to: {output_file}")

    # Verify some replacements
    print("\nVerification:")
    if "Sewells Point, Hampton Roads, Virginia" in text:
        print("  - Hampton Roads -> Sewells Point: OK")
    if "Kwajalein, Marshall Islands" in text:
        print("  - Kwajalein Atoll -> Kwajalein: OK")
    if "Key West, Florida" in text and "Key West (Naval Base)" not in text:
        print("  - Key West (Naval Base) -> Key West: OK")
    if "Pictou, Nova Scotia, Canada" in text:
        print("  - Pictou -> Pictou, Canada: OK")
    if "Sandy Hook, Fort Hancock, New Jersey" in text:
        print("  - Sandy Hook -> Sandy Hook, Fort Hancock: OK")
    if "Galveston Pier 21, Galveston Channel, Texas" in text:
        print("  - Galveston -> Galveston Pier 21: OK")
    if "Harrington Harbour, Qu" in text:
        # Check for the Canada suffix
        if "Harrington Harbour, Qu" in text:
            idx = text.find("Harrington Harbour, Qu")
            snippet = text[idx:idx+50]
            if "Canada" in snippet:
                print("  - Harrington Harbour -> Harrington Harbour, Canada: OK")

if __name__ == '__main__':
    input_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes9.idx'
    output_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes9_ref_mapped.idx'
    mapping_file = '/home/oliver/subordinate_corrections/reference_station_mapping_final.csv'

    apply_mappings(input_file, output_file, mapping_file)
