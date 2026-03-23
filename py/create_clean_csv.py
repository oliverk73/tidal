#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re
import unicodedata

def remove_non_latin_scripts(text: str) -> str:
    """Entfernt nicht-ISO-8859-1 Zeichen"""
    result_chars = []
    for char in text:
        try:
            char.encode('iso-8859-1')
            result_chars.append(char)
        except UnicodeEncodeError:
            nfd = unicodedata.normalize('NFD', char)
            base_char = nfd[0] if nfd else ''
            try:
                base_char.encode('iso-8859-1')
                if base_char.isprintable() or base_char.isspace():
                    result_chars.append(base_char)
            except:
                pass
    result = ''.join(result_chars)
    return re.sub(r'\s+', ' ', result).strip()

def main():
    input_file = '/home/oliver/harmonics_working/stations_final_corrected.csv'
    output_file = '/home/oliver/harmonics_working/stations_clean.csv'

    print("📖 Erstelle bereinigte CSV (nur lateinische Zeichen)...\n")

    clean_rows = []

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')

        for row in reader:
            clean_row = {
                'Original_Name': row['Original_Name'],
                'Original_Lat': row['Original_Lat'],
                'Original_Lon': row['Original_Lon'],
                'Original_Timezone': row['Original_Timezone'],
                'Verified_Name': remove_non_latin_scripts(row.get('GeoNames_Name', '')),
                'Verified_Region': remove_non_latin_scripts(row.get('GeoNames_Region', '')),
                'Verified_Country': remove_non_latin_scripts(row.get('GeoNames_Country', '')),
                'Final_Corrected_Name': row.get('Final_Corrected_Name', row['Original_Name']),
                'Status': row['Status'],
            }
            clean_rows.append(clean_row)

    fieldnames = ['Original_Name', 'Original_Lat', 'Original_Lon', 'Original_Timezone',
                  'Verified_Name', 'Verified_Region', 'Verified_Country',
                  'Final_Corrected_Name', 'Status']

    # Schreibe als ISO-8859-1 (wie harmonics-Datei)
    with open(output_file, 'w', encoding='iso-8859-1', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(clean_rows)

    print(f"✅ Bereinigte CSV erstellt: {output_file}")
    print(f"   {len(clean_rows)} Stationen")
    print(f"   Encoding: ISO-8859-1")
    print(f"   Alle Spalten sind ISO-8859-1 kompatibel")

    # Verifikation
    print("\n🧪 Verifiziere ISO-8859-1 Kompatibilität...")
    failed = []
    for i, row in enumerate(clean_rows, 2):
        for key, value in row.items():
            try:
                value.encode('iso-8859-1')
            except:
                failed.append((i, key, value))

    if failed:
        print(f"❌ {len(failed)} Felder sind NICHT ISO-8859-1 kompatibel")
        for i, key, val in failed[:10]:
            print(f"   Zeile {i}, {key}: {val[:50]}")
    else:
        print("✅ Alle Felder sind ISO-8859-1 kompatibel!")

if __name__ == '__main__':
    main()
