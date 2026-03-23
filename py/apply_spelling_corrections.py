#!/usr/bin/env python3
"""
Apply spelling corrections from CSV to the harmonics file.
Ensures all characters are ISO 8859-1 (Latin-1) compatible.
"""

import csv

def check_latin1_compatible(text):
    """Check if text can be encoded as Latin-1."""
    try:
        text.encode('latin-1')
        return True, None
    except UnicodeEncodeError as e:
        return False, str(e)

def load_corrections(csv_file):
    """Load corrections from CSV file."""
    corrections = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)  # Skip header
        for row in reader:
            if len(row) >= 3:
                line_num = int(row[0])
                old_name = row[1]
                new_name = row[2]

                # Skip entries marked as PRUEFEN
                if new_name.startswith('PRUEFEN:'):
                    print(f"Ueberspringe (manuell pruefen): {old_name}")
                    continue

                # Check Latin-1 compatibility
                is_ok, error = check_latin1_compatible(new_name)
                if not is_ok:
                    print(f"WARNUNG: Nicht Latin-1 kompatibel: {new_name}")
                    print(f"  Fehler: {error}")
                    continue

                corrections.append((line_num, old_name, new_name))

    return corrections

def apply_corrections(input_file, output_file, corrections):
    """Apply corrections to the harmonics file."""
    # Read file as bytes to preserve encoding
    with open(input_file, 'rb') as f:
        content = f.read()

    # Decode as Latin-1
    text = content.decode('latin-1')

    applied = 0
    not_found = []

    for line_num, old_name, new_name in corrections:
        # The old name might contain UTF-8 sequences read as Latin-1
        # We need to find it in the text
        if old_name in text:
            text = text.replace(old_name, new_name, 1)
            applied += 1
            print(f"Korrigiert: {old_name[:50]}...")
            print(f"       ->   {new_name[:50]}...")
        else:
            not_found.append((line_num, old_name))

    # Encode back to Latin-1
    try:
        output_bytes = text.encode('latin-1')
    except UnicodeEncodeError as e:
        print(f"FEHLER beim Kodieren: {e}")
        return 0

    # Write output
    with open(output_file, 'wb') as f:
        f.write(output_bytes)

    print(f"\n{'='*60}")
    print(f"Angewendete Korrekturen: {applied}")

    if not_found:
        print(f"\nNicht gefunden ({len(not_found)}):")
        for line_num, name in not_found:
            print(f"  Zeile {line_num}: {name[:60]}...")

    return applied

def main():
    csv_file = '/home/oliver/harmonics_working/station_spelling_corrections.csv'
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'

    print("Lade Korrekturen aus CSV...")
    corrections = load_corrections(csv_file)
    print(f"Geladene Korrekturen: {len(corrections)}")

    print(f"\nWende Korrekturen an...")
    print("="*60)

    applied = apply_corrections(input_file, output_file, corrections)

    print(f"\nDatei aktualisiert: {output_file}")

if __name__ == '__main__':
    main()
