#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv

def fix_apostrophes(text):
    """Replace all fancy apostrophes with simple ones"""
    replacements = {
        ''': "'",  # RIGHT SINGLE QUOTATION MARK
        ''': "'",  # LEFT SINGLE QUOTATION MARK
        '′': "'",  # PRIME
        '`': "'",  # GRAVE ACCENT
        'ʻ': "'",  # MODIFIER LETTER TURNED COMMA (Hawaiian okina)
        '´': "'",  # ACUTE ACCENT
    }
    
    result = text
    for fancy, simple in replacements.items():
        result = result.replace(fancy, simple)
    
    return result


def main():
    input_file = '/home/oliver/harmonics_working/station_name_corrections_final.csv'
    output_file = '/home/oliver/harmonics_working/station_name_corrections_final.csv'

    print("🔧 Behebe Apostroph-Probleme...")
    
    rows = []
    fixed_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row in reader:
            full_name = row.get('Full_Corrected_Name', '')
            
            if full_name:
                fixed = fix_apostrophes(full_name)
                if fixed != full_name:
                    fixed_count += 1
                    print(f"✓ {row['Original_Name'][:50]}")
                    row['Full_Corrected_Name'] = fixed
            
            rows.append(row)

    print(f"\n💾 Schreibe finale CSV-Datei...")

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    print("\n🧪 Final-Test: ISO-8859-1 Konvertierung...")
    test_file = '/home/oliver/harmonics_working/station_name_corrections_iso8859.csv'
    
    failed = []
    for i, row in enumerate(rows, start=2):
        full_name = row.get('Full_Corrected_Name', '')
        if full_name:
            try:
                full_name.encode('iso-8859-1')
            except UnicodeEncodeError as e:
                failed.append((i, row['Original_Name'], full_name, e.object[e.start:e.end]))
    
    if failed:
        print(f"❌ {len(failed)} Einträge können IMMER NOCH nicht konvertiert werden:")
        for i, orig, full, char in failed:
            print(f"   Zeile {i}: {orig[:40]}")
            print(f"      Problem-Zeichen: '{char}' (Unicode: U+{ord(char):04X})")
    else:
        with open(test_file, 'w', encoding='iso-8859-1', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"✅ ERFOLG! Alle Stationen sind ISO-8859-1 kompatibel!")
        print(f"✅ UTF-8 Datei: {output_file}")
        print(f"✅ ISO-8859-1 Datei: {test_file}")

    print("\n" + "="*80)
    print("📊 Finale Statistik:")
    print(f"   Gesamt: {len(rows)} Stationen")
    print(f"   Apostrophe behoben: {fixed_count}")
    print(f"   Nicht konvertierbar: {len(failed)}")
    print("="*80)


if __name__ == '__main__':
    main()
