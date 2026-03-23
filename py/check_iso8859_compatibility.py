#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re

def check_iso8859_1_compatibility(text):
    """Prüft, ob ein Text in ISO-8859-1 kodiert werden kann"""
    try:
        text.encode('iso-8859-1')
        return True, None
    except UnicodeEncodeError as e:
        return False, e.object[e.start:e.end]


def transliterate_to_latin(text):
    """Versucht, nicht-lateinische Zeichen in lateinische umzuwandeln"""
    # Mapping für spezielle Zeichen, die nicht in ISO-8859-1 sind
    replacements = {
        'ō': 'o',  # Macron
        'ū': 'u',
        'Ō': 'O',
        'Ū': 'U',
        'ʻ': "'",  # Okina (hawaiianisch)
        'ʻ': "'",
        ''': "'",
        ''': "'",
        '中国': 'China',  # Chinesische Zeichen
        '日本': 'Japan',  # Japanische Zeichen
        '울산광역시': 'Ulsan',  # Koreanische Zeichen
        '塘凹': 'Tangao',
        # Vietnamesische Zeichen
        'Đồ': 'Do',
        'đ': 'd',
        'Đ': 'D',
        'ạ': 'a',
        'ị': 'i',
        'ũ': 'u',
        'ọ': 'o',
        'ư': 'u',
        'ơ': 'o',
        'ă': 'a',
        'ê': 'e',
        # Griechisch
        'Ḩ': 'H',
        'ḩ': 'h',
        'Ḑ': 'D',
        'ḑ': 'd',
        'ţ': 't',
        'Ţ': 'T',
        'ş': 's',
        'Ş': 'S',
        # Arabisch/Persisch
        'ḩ': 'h',
        'ţ': 't',
        'ī': 'i',
        'ā': 'a',
        'ū': 'u',
        # Maori/Polynesisch
        'ō': 'o',
        'ā': 'a',
    }
    
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    
    return result


def main():
    input_file = '/home/oliver/harmonics_working/station_name_corrections_updated.csv'
    output_file = '/home/oliver/harmonics_working/station_name_corrections_final.csv'

    print("🔍 Prüfe ISO-8859-1 Kompatibilität...")
    
    incompatible_entries = []
    rows = []

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row_num, row in enumerate(reader, start=2):
            full_name = row.get('Full_Corrected_Name', '')
            compatible, problem_char = check_iso8859_1_compatibility(full_name)
            
            if not compatible:
                incompatible_entries.append({
                    'row': row_num,
                    'original_name': row['Original_Name'],
                    'full_name': full_name,
                    'problem_char': problem_char
                })
                
                # Versuche zu transliterieren
                transliterated = transliterate_to_latin(full_name)
                compatible_after, _ = check_iso8859_1_compatibility(transliterated)
                
                if compatible_after:
                    print(f"⚠️  Zeile {row_num}: {row['Original_Name']}")
                    print(f"   Original: {full_name}")
                    print(f"   Transliteriert: {transliterated}")
                    row['Full_Corrected_Name'] = transliterated
                else:
                    print(f"❌ Zeile {row_num}: {row['Original_Name']}")
                    print(f"   NICHT transliterierbar: {full_name}")
            
            rows.append(row)

    print(f"\n💾 Schreibe finale CSV-Datei nach {output_file}...")

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "="*80)
    print("📊 Ergebnis:")
    print(f"   Gesamt: {len(rows)} Stationen")
    print(f"   Nicht-ISO-8859-1 kompatibel: {len(incompatible_entries)}")
    print("="*80)

    # Test: Versuche die finale Datei in ISO-8859-1 zu schreiben
    print("\n🧪 Test: Schreibe Test-Datei in ISO-8859-1...")
    test_file = '/home/oliver/harmonics_working/station_name_corrections_iso8859.csv'
    
    try:
        with open(test_file, 'w', encoding='iso-8859-1', newline='', errors='strict') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerows(rows)
        print(f"✓ ISO-8859-1 Test erfolgreich! Datei: {test_file}")
    except UnicodeEncodeError as e:
        print(f"❌ ISO-8859-1 Kodierung fehlgeschlagen!")
        print(f"   Problem bei Zeichen: '{e.object[e.start:e.end]}'")


if __name__ == '__main__':
    main()
