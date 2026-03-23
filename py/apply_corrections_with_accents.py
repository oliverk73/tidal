#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re

def normalize_apostrophes(text):
    """Normalize all apostrophe variants to simple apostrophe"""
    return text.replace("'", "'").replace("`", "'").replace("´", "'").replace("'", "'").replace("'", "'").replace("′", "'").replace("ʻ", "'")

def main():
    csv_file = '/home/oliver/harmonics_working/station_name_corrections_final.csv'
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3_man.txt'

    print("📖 Lese Korrekturen aus station_name_corrections_final.csv (MIT Akzenten)...")

    # Build correction mapping
    corrections = {}
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            original = row['Original_Name'].strip()
            full_corrected = row['Full_Corrected_Name'].strip()

            if full_corrected:
                # Normalize apostrophes for matching
                original_normalized = normalize_apostrophes(original)
                corrections[original_normalized] = full_corrected

    print(f"✓ {len(corrections)} Korrekturen geladen")

    # Special encoding fixes for stations with name mismatches
    # Map from harmonics file name → CSV lookup name (before apostrophe normalization)
    encoding_fixes = {
        # Harmonics file has missing characters
        'Fcamp, France': 'Fecamp, France',
        'Gijn, Spain': 'Gijon, Spain',
        'Avils, Spain': 'Aviles, Spain',
        'Faro-Olho, Portugal': 'Faro-Olhao, Portugal',
        'Florianpolis, Brazil': 'Florianopolis, Brazil',
        'So Lus, Brazil': 'So Lus, Brazil',
        'So Sebastio, Brazil': 'So Sebastio, Brazil',
        'Banda Harbour (Naira), Indonesia': 'Banda Harbour (Naira), Indonesia###',

        # Harmonics file has accents, CSV Original_Name doesn't
        'Bahía Aguirre, Argentina': 'Bahia Aguirre, Argentina',
        'Vilagarcía de Arousa, Spain': 'Vilagarcia de Arousa, Spain',
    }

    print("\n📝 Verarbeite harmonics-Datei...")

    replaced_count = 0
    not_found = []
    last_was_latitude = False

    # Read as UTF-8 (source has mixed encoding), write as ISO-8859-1
    with open(input_file, 'r', encoding='utf-8', errors='replace') as f_in:
        with open(output_file, 'w', encoding='iso-8859-1', errors='replace') as f_out:
            for line in f_in:
                if line.startswith('# !latitude:'):
                    last_was_latitude = True
                    f_out.write(line)
                elif last_was_latitude and not line.startswith('#') and line.strip():
                    last_was_latitude = False
                    station_name = line.strip()

                    # First check encoding fixes
                    if station_name in encoding_fixes:
                        station_name = encoding_fixes[station_name]

                    # Normalize apostrophes for lookup
                    station_normalized = normalize_apostrophes(station_name)

                    if station_normalized in corrections:
                        new_name = corrections[station_normalized]

                        # Verify ISO-8859-1 compatibility
                        try:
                            new_name.encode('iso-8859-1')
                            f_out.write(new_name + '\n')
                            replaced_count += 1

                            # Show first few with accents
                            if replaced_count <= 10 and (
                                'ó' in new_name or 'á' in new_name or 'é' in new_name or
                                'í' in new_name or 'ú' in new_name or 'ñ' in new_name or
                                'ç' in new_name or 'ã' in new_name
                            ):
                                print(f"  ✓ {station_name[:40]} → {new_name[:60]}")
                        except UnicodeEncodeError as e:
                            print(f"  ❌ ENCODING ERROR: {new_name}")
                            print(f"     Problem character: {e.object[e.start:e.end]} (U+{ord(e.object[e.start]):04X})")
                            f_out.write(station_name + '\n')  # Keep original
                    else:
                        not_found.append(station_name)
                        f_out.write(station_name + '\n')  # Keep original
                else:
                    last_was_latitude = False
                    f_out.write(line)

    print(f"\n{'='*80}")
    print("📊 ERGEBNIS:")
    print(f"   Ersetzt: {replaced_count} / {len(corrections)} Stationen")

    if not_found:
        print(f"\n⚠️  Nicht gefunden ({len(not_found)}):")
        for name in not_found[:10]:
            print(f"   - {name}")
        if len(not_found) > 10:
            print(f"   ... und {len(not_found) - 10} weitere")
    else:
        print("   ✓ Alle Stationen erfolgreich ersetzt!")

    print(f"\n✅ Finale Datei geschrieben: {output_file}")
    print("="*80)

    # Final verification
    print("\n🧪 Verifiziere Akzente in der finalen Datei...")
    with open(output_file, 'r', encoding='iso-8859-1') as f:
        content = f.read()

        # Check for specific accented characters
        accents_found = {
            'ó': content.count('ó'),
            'á': content.count('á'),
            'é': content.count('é'),
            'í': content.count('í'),
            'ú': content.count('ú'),
            'ñ': content.count('ñ'),
            'ç': content.count('ç'),
            'ã': content.count('ã'),
        }

        total_accents = sum(accents_found.values())
        if total_accents > 0:
            print(f"✅ Akzente erfolgreich erhalten! Gesamt: {total_accents}")
            for char, count in accents_found.items():
                if count > 0:
                    print(f"   {char}: {count}x")
        else:
            print("❌ FEHLER: Keine Akzente in der finalen Datei gefunden!")

if __name__ == '__main__':
    main()
