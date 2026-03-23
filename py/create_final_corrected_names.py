#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re
import unicodedata

def remove_non_latin_scripts(text: str) -> str:
    """
    Entfernt nur nicht-lateinische Schriften (Inuktitut, CJK, Cyrillic, etc.).
    BEHÄLT lateinische Buchstaben mit Diakritika (é, ó, á, ñ, ç, ô, etc.).

    Einfache Methode: Behalte nur Zeichen, die in ISO-8859-1 encodierbar sind.
    """
    result_chars = []

    for char in text:
        try:
            # Versuche zu encodieren als ISO-8859-1
            char.encode('iso-8859-1')
            result_chars.append(char)
        except UnicodeEncodeError:
            # Nicht ISO-8859-1: Überspringe oder konvertiere
            # Versuche NFD-Normalisierung für erweiterte lateinische Zeichen
            nfd = unicodedata.normalize('NFD', char)
            base_char = nfd[0] if nfd else ''

            # Wenn Base-Character ISO-8859-1 ist, nimm ihn
            try:
                base_char.encode('iso-8859-1')
                if base_char.isprintable() or base_char.isspace():
                    result_chars.append(base_char)
            except:
                # Komplett nicht-lateinisch, skip
                pass

    # Join und bereinige Leerzeichen
    result = ''.join(result_chars)
    result = re.sub(r'\s+', ' ', result)

    return result.strip()

def needs_correction(original_city: str) -> bool:
    """
    Prüft, ob der Stadt-Name korrigiert werden muss.

    Korrekturbedarf bei:
    - KOMPLETT UPPERCASE (z.B. "ABA" statt "Abamachi")
    - Überwiegend UPPERCASE (>50% Großbuchstaben außer Anfangsbuchstaben)
    - Enthält nicht-lateinische Zeichen (muss bereinigt werden)

    KEIN Korrekturbedarf bei:
    - Normal geschriebenen Namen (z.B. "Abbapoola Creek entrance")
    - Namen mit korrekten Akzenten (z.B. "Acapulco")
    """
    if not original_city:
        return False

    # Prüfe auf nicht-lateinische Zeichen
    cleaned = remove_non_latin_scripts(original_city)
    if cleaned != original_city:
        return True  # Enthält nicht-lateinische Zeichen

    # Prüfe auf UPPERCASE
    # Zähle Buchstaben (ohne erste Buchstaben nach Komma/Leerzeichen)
    letters = [c for c in original_city if c.isalpha()]
    if not letters:
        return False

    # Wenn alle Buchstaben uppercase sind -> korrigieren
    uppercase_count = sum(1 for c in letters if c.isupper())

    # Alle uppercase (z.B. "ABA, NAGASAKI")
    if uppercase_count == len(letters):
        return True

    # Überwiegend uppercase (aber nicht normal Title Case)
    # Bei Title Case sind nur erste Buchstaben uppercase
    words = original_city.replace(',', ' ').split()
    expected_uppercase = len(words)  # Anzahl Wörter = Anzahl erwartete Großbuchstaben

    # Wenn deutlich mehr uppercase als erwartet -> korrigieren
    if uppercase_count > expected_uppercase * 1.5:
        return True

    return False

def parse_original_name(original_name: str) -> tuple:
    """
    Parst Original-Namen im Format: "Stadt, Region, Land" oder "Stadt, Land"

    Returns: (city, region, country)
    """
    parts = [p.strip() for p in original_name.split(',')]

    if len(parts) >= 3:
        # "Stadt, Region, Land" oder "Stadt, Region, Land (suffix)"
        city = parts[0]
        region = parts[1]
        country = ', '.join(parts[2:])  # Rest ist Land (kann Suffix haben)
        return (city, region, country)
    elif len(parts) == 2:
        # "Stadt, Land"
        return (parts[0], '', parts[1])
    else:
        # Nur ein Teil
        return (parts[0], '', '')

def main():
    input_file = '/home/oliver/harmonics_working/stations_verification_complete.csv'
    output_file = '/home/oliver/harmonics_working/stations_final_corrected.csv'

    print("📖 Erstelle finale korrigierte Namen...")
    print("   Strategie:")
    print("   - Stadt: GeoNames wenn Original fehlerhaft, sonst Original (mit Akzenten!)")
    print("   - Region: IMMER GeoNames (administrative Region mit korrekten Akzenten)")
    print("   - Land: IMMER GeoNames (vollständige Namen)")
    print("   - Format: Stadt, Region, Land (alle Teile wenn vorhanden)\n")

    rows = []
    corrected_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = list(reader.fieldnames) + ['Final_Corrected_Name']

        for row in reader:
            original_name = row['Original_Name']

            # Parse Original-Name
            orig_city, orig_region, orig_country = parse_original_name(original_name)

            # Strategie für finalen Namen
            if row['Status'] in ['verified', 'verified_nominatim']:
                # SCHRITT 1: Stadt-Name bestimmen
                # Verwende GeoNames wenn Original fehlerhaft ist oder GeoNames Akzente hat
                city = orig_city
                if row['GeoNames_Name']:
                    geonames_city = remove_non_latin_scripts(row['GeoNames_Name'])
                    if geonames_city:  # Nur wenn nicht leer nach Bereinigung
                        if needs_correction(orig_city):
                            # Original ist fehlerhaft -> GeoNames verwenden
                            city = geonames_city
                        else:
                            # Vergleiche normalisiert (ohne Akzente) ob es der gleiche Name ist
                            def normalize_for_comparison(s):
                                # Entferne Akzente für Vergleich
                                nfd = unicodedata.normalize('NFD', s)
                                return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn').lower().replace(' ', '').replace('-', '')

                            if normalize_for_comparison(geonames_city) == normalize_for_comparison(orig_city):
                                # Gleicher Name, aber GeoNames hat Akzente -> verwenden!
                                city = geonames_city

                # SCHRITT 2: Region bestimmen (IMMER aus GeoNames für bessere Daten)
                region = ''
                if row['GeoNames_Region']:
                    region = remove_non_latin_scripts(row['GeoNames_Region'])
                    # Fallback wenn GeoNames nur nicht-lateinische Zeichen hatte
                    if not region.strip() and orig_region:
                        region_fixed = orig_region.replace('Qubec', 'Québec')
                        region = remove_non_latin_scripts(region_fixed)
                elif orig_region:
                    # Korrigiere bekannte Encoding-Fehler
                    region_fixed = orig_region.replace('Qubec', 'Québec')
                    region = remove_non_latin_scripts(region_fixed)

                # SCHRITT 3: Land bestimmen (IMMER aus GeoNames)
                country = ''
                if row['GeoNames_Country']:
                    country = remove_non_latin_scripts(row['GeoNames_Country'])
                    # Fallback wenn GeoNames nur nicht-lateinische Zeichen hatte
                    if not country.strip() and orig_country:
                        country_fixed = orig_country.replace('Qubec', 'Québec')
                        country = remove_non_latin_scripts(country_fixed)
                elif orig_country:
                    # Korrigiere bekannte Encoding-Fehler
                    country_fixed = orig_country.replace('Qubec', 'Québec')
                    country = remove_non_latin_scripts(country_fixed)

                # SCHRITT 4: Suffix extrahieren
                suffix_match = re.search(r'\((\d+)\)\s*$', original_name)
                suffix = f' ({suffix_match.group(1)})' if suffix_match else ''

                # Entferne Suffix aus country falls vorhanden
                if country:
                    country = re.sub(r'\s*\(\d+\)\s*$', '', country).strip()

                # SCHRITT 5: Finalen Namen konstruieren
                # Format: "Stadt, Region, Land" (alle Teile wenn vorhanden)
                parts = []
                if city.strip():
                    parts.append(city.strip())
                if region.strip():
                    parts.append(region.strip())
                if country.strip():
                    parts.append(country.strip())

                if parts:
                    final_name = ', '.join(parts) + suffix
                else:
                    # Fallback: Wenn alles leer, behalte Original
                    final_name = remove_non_latin_scripts(original_name)

                # Prüfe ob korrigiert wurde
                if final_name != remove_non_latin_scripts(original_name):
                    corrected_count += 1
                    if corrected_count <= 15:
                        print(f"  ✓ {original_name[:45]:45s} → {final_name}")

                row['Final_Corrected_Name'] = final_name
            else:
                # Failed stations: behalte Original
                row['Final_Corrected_Name'] = original_name

            rows.append(row)

    print(f"\n💾 Schreibe finale CSV...")

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ {corrected_count} Namen korrigiert")
    print(f"✅ Datei erstellt: {output_file}")
    print(f"\n📊 STATISTIK:")
    print(f"   Gesamt:      {len(rows)} Stationen")
    print(f"   Korrigiert:  {corrected_count}")
    print(f"   Unverändert: {len(rows) - corrected_count}")

if __name__ == '__main__':
    main()
