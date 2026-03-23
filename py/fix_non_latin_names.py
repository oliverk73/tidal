#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re
import unicodedata

def remove_non_latin_scripts(text: str) -> str:
    """
    Entfernt nur nicht-lateinische Schriften (Inuktitut, CJK, Cyrillic, etc.).
    BEHÄLT lateinische Buchstaben mit Diakritika (é, ó, á, ñ, ç, ô, etc.).

    Beispiele:
    "ᕿᑭᖅᑖᓗᒃ Qikiqtaaluk Region" → "Qikiqtaaluk Region"
    "Québec" → "Québec" (behält é!)
    "São Paulo" → "São Paulo" (behält ã!)
    "Ōsaki" → "Osaki" (konvertiert ō → o, da nicht in ISO-8859-1)
    """
    # Schritt 1: Konvertiere erweiterte lateinische Zeichen zu ISO-8859-1
    # Macrons (ō) und andere extended Unicode → Basic equivalents
    # Aber NUR für Zeichen AUSSERHALB von ISO-8859-1
    nfd = unicodedata.normalize('NFD', text)

    result_chars = []
    for char in nfd:
        cat = unicodedata.category(char)

        # Überspringe combining marks (diacritics)
        if cat == 'Mn':
            # Behalte nur ISO-8859-1 compatible combining marks
            try:
                char.encode('iso-8859-1')
                result_chars.append(char)
            except UnicodeEncodeError:
                # Combining mark ist nicht ISO-8859-1, skip it
                pass
        else:
            result_chars.append(char)

    intermediate = ''.join(result_chars)

    # Schritt 2: Behalte nur Latin-1 Zeichen (ISO-8859-1)
    # Das inkludiert: A-Z, a-z, À-ÿ (mit Akzenten!), 0-9, Satzzeichen
    latin_pattern = r'[A-Za-zÀ-ÿ0-9\s\-\',\.()&]'

    # Extrahiere alle Latin-1 Zeichen
    latin_chars = ''.join(re.findall(latin_pattern, intermediate))

    # Bereinige mehrfache Leerzeichen
    cleaned = re.sub(r'\s+', ' ', latin_chars)

    return cleaned.strip()

def main():
    input_file = '/home/oliver/harmonics_working/stations_verification_complete.csv'
    output_file = '/home/oliver/harmonics_working/stations_verification_complete.csv'

    print("📖 Lese CSV-Datei...")

    rows = []
    fixed_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row in reader:
            # Prüfe und korrigiere GeoNames_Name
            if row['GeoNames_Name']:
                original = row['GeoNames_Name']
                fixed = remove_non_latin_scripts(original)
                if fixed != original:
                    fixed_count += 1
                    if fixed_count <= 10:
                        print(f"  ✓ {original[:50]} → {fixed}")
                    row['GeoNames_Name'] = fixed

            # Prüfe und korrigiere GeoNames_Region
            if row['GeoNames_Region']:
                original = row['GeoNames_Region']
                fixed = remove_non_latin_scripts(original)
                if fixed != original:
                    row['GeoNames_Region'] = fixed

            # Prüfe und korrigiere GeoNames_Country
            if row['GeoNames_Country']:
                original = row['GeoNames_Country']
                fixed = remove_non_latin_scripts(original)
                if fixed != original:
                    row['GeoNames_Country'] = fixed

            # Prüfe und korrigiere Corrected_Name
            if row['Corrected_Name']:
                original = row['Corrected_Name']
                fixed = remove_non_latin_scripts(original)
                if fixed != original:
                    row['Corrected_Name'] = fixed

            # Prüfe und korrigiere Corrected_Region
            if row['Corrected_Region']:
                original = row['Corrected_Region']
                fixed = remove_non_latin_scripts(original)
                if fixed != original:
                    row['Corrected_Region'] = fixed

            # Prüfe und korrigiere Corrected_Country
            if row['Corrected_Country']:
                original = row['Corrected_Country']
                fixed = remove_non_latin_scripts(original)
                if fixed != original:
                    row['Corrected_Country'] = fixed

            rows.append(row)

    if fixed_count > 10:
        print(f"  ... und {fixed_count - 10} weitere Korrekturen")

    print(f"\n💾 Schreibe korrigierte CSV...")

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ {fixed_count} Namen korrigiert (nicht-lateinische Zeichen entfernt)")
    print(f"✅ Datei aktualisiert: {output_file}")

if __name__ == '__main__':
    main()
