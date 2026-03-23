#!/usr/bin/env python3
"""
Find potential spelling errors in tide station names.
Outputs corrections to a CSV file.
"""

import re
import csv

def extract_stations(input_file):
    """Extract all station names from the harmonics file."""
    # Read as bytes first to handle mixed encoding
    with open(input_file, 'rb') as f:
        content = f.read()

    # Decode as latin-1 (preserves all bytes)
    text = content.decode('latin-1')
    lines = text.split('\n')

    stations = []
    for i, line in enumerate(lines):
        if (i > 0 and
            lines[i-1].startswith('# !latitude:') and
            line.strip() and
            not line.startswith('#') and
            not line.startswith('x ') and
            not line.startswith('+') and
            not line.startswith('-') and
            len(line) > 0 and line[0].isalpha()):
            stations.append((i + 1, line.strip()))

    return stations

# UTF-8 byte sequences as they appear when read as Latin-1
# These are UTF-8 characters incorrectly stored/read as Latin-1
UTF8_TO_LATIN1 = {
    '\xc3\xa1': 'á',   # á
    '\xc3\xa9': 'é',   # é
    '\xc3\xad': 'í',   # í
    '\xc3\xb3': 'ó',   # ó
    '\xc3\xba': 'ú',   # ú
    '\xc3\xb1': 'ñ',   # ñ
    '\xc3\x8e': 'Î',   # Î
    '\xc3\x89': 'É',   # É
    '\xc3\x81': 'Á',   # Á
    '\xc3\x93': 'Ó',   # Ó
    '\xc3\x9a': 'Ú',   # Ú
    '\xc3\x91': 'Ñ',   # Ñ
    '\xc3\xa7': 'ç',   # ç
    '\xc3\xaa': 'ê',   # ê
    '\xc3\xa8': 'è',   # è
    '\xc3\xb4': 'ô',   # ô
    '\xc3\xa2': 'â',   # â
    '\xc3\xbc': 'ü',   # ü
    '\xc3\xb6': 'ö',   # ö
    '\xc3\xa4': 'ä',   # ä
    '\xc3\xb8': 'ø',   # ø
    '\xc3\x98': 'Ø',   # Ø
    '\xc3\xa5': 'å',   # å
    '\xc3\x85': 'Å',   # Å
    '\xc3\xa3': 'ã',   # ã
    '\xc3\xb5': 'õ',   # õ
}

# Known spelling corrections for truncated names
TRUNCATED_NAMES = {
    'Avils': 'Avilés',
    'Belm, Par': 'Belém, Pará',
    'Bod': 'Bodø',
    'Florianpolis': 'Florianópolis',
    'Gijn': 'Gijón',
    'Ilha Guaba': 'Ilha Guaíba',
    'Itaja': 'Itajaí',
    'Macei': 'Maceió',
    'Marn': 'Marín',
    'Paranagu': 'Paranaguá',
    'Rrvik': 'Rørvik',
    'Salinpolis': 'Salinópolis',
    'So Francisco do Sul': 'São Francisco do Sul',
    'So Lus': 'São Luís',
    'So Sebastio': 'São Sebastião',
    'Troms': 'Tromsø',
    'Tubaro': 'Tubarão',
    'Vitria': 'Vitória',
    'Burnt Church?': 'Burnt Church',
}

def fix_utf8_as_latin1(text):
    """Fix UTF-8 bytes that were read as Latin-1."""
    result = text
    for utf8_seq, correct_char in UTF8_TO_LATIN1.items():
        result = result.replace(utf8_seq, correct_char)
    return result

def find_corrections(stations):
    """Find stations that need corrections."""
    corrections = []

    for line_num, station_name in stations:
        original = station_name
        corrected = station_name
        needs_correction = False

        # Fix UTF-8 encoding issues
        corrected = fix_utf8_as_latin1(corrected)
        if corrected != original:
            needs_correction = True

        # Apply truncated name corrections
        for wrong, correct in TRUNCATED_NAMES.items():
            if wrong in corrected:
                corrected = corrected.replace(wrong, correct)
                needs_correction = True

        # Check for remaining encoding issues
        if '\xc3' in corrected:
            needs_correction = True
            corrected = f"PRUEFEN: {corrected}"

        # Check for question marks
        if '?' in original and '?' not in corrected:
            pass  # Already fixed
        elif '?' in original:
            needs_correction = True

        if needs_correction:
            corrections.append((line_num, original, corrected))

    return corrections

def write_csv(corrections, output_file):
    """Write corrections to CSV file."""
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['Zeilennummer', 'Existierender Name', 'Korrigierter Name'])
        for line_num, original, corrected in corrections:
            writer.writerow([line_num, original, corrected])

def main():
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/station_spelling_corrections.csv'

    print("Extrahiere Stationsnamen...")
    stations = extract_stations(input_file)
    print(f"Gefunden: {len(stations)} Stationen")

    print("\nSuche nach Rechtschreibfehlern...")
    corrections = find_corrections(stations)

    print(f"\nGefunden: {len(corrections)} moegliche Korrekturen")

    print(f"\nSchreibe CSV-Datei: {output_file}")
    write_csv(corrections, output_file)

    print("\n" + "="*70)
    print("Gefundene Korrekturen:")
    print("="*70)
    for line_num, original, corrected in corrections:
        print(f"Zeile {line_num}:")
        print(f"  Alt: {original}")
        print(f"  Neu: {corrected}")
        print()

if __name__ == '__main__':
    main()
