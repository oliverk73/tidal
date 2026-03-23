#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import unicodedata

def remove_accents(text):
    """
    Entfernt alle Akzente aus einem String für das Matching.
    'Vilagarcía' -> 'Vilagarcia'
    'São' -> 'Sao'
    """
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')

def normalize_apostrophes(text):
    """Normalize all apostrophe variants to simple apostrophe"""
    return text.replace("'", "'").replace("`", "'").replace("´", "'").replace("'", "'").replace("'", "'").replace("′", "'").replace("ʻ", "'")

def normalize_for_matching(text):
    """
    Normalisiert einen String für das Matching:
    - Entfernt Akzente
    - Normalisiert Apostrophe
    - Trimmt Whitespace
    """
    text = text.strip()
    text = normalize_apostrophes(text)
    text = remove_accents(text)
    return text

def main():
    csv_file = '/home/oliver/harmonics_working/station_name_corrections_final.csv'
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3_man.txt'

    print("📖 Lese Korrekturen aus station_name_corrections_final.csv...")

    # Build correction mapping: normalized original -> full corrected name (with accents!)
    corrections = {}
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            original = row['Original_Name'].strip()
            full_corrected = row['Full_Corrected_Name'].strip()

            if full_corrected:
                # Normalize original for matching (without accents)
                original_normalized = normalize_for_matching(original)
                # Store the FULL CORRECTED name WITH accents
                corrections[original_normalized] = full_corrected

    print(f"✓ {len(corrections)} Korrekturen geladen")

    # Special cases: harmonics file has MISSING characters (not just missing accents)
    special_cases = {
        'Fcamp, France': 'Fecamp, France',
        'Gijn, Spain': 'Gijon, Spain',
        'Avils, Spain': 'Aviles, Spain',
        'Faro-Olho, Portugal': 'Faro-Olhao, Portugal',
        'Florianpolis, Brazil': 'Florianopolis, Brazil',
        'So Lus, Brazil': 'So Lus, Brazil',
        'So Sebastio, Brazil': 'So Sebastio, Brazil',
        'Banda Harbour (Naira), Indonesia': 'Banda Harbour (Naira), Indonesia###',
    }

    print("\n📝 Verarbeite harmonics-Datei...")
    print("   Matching: Akzente werden ignoriert")
    print("   Ausgabe: Mit korrekten Akzenten aus CSV\n")

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

                    # First check special cases (missing characters)
                    lookup_name = special_cases.get(station_name, station_name)

                    # Normalize for lookup (remove accents)
                    station_normalized = normalize_for_matching(lookup_name)

                    if station_normalized in corrections:
                        new_name = corrections[station_normalized]

                        # Verify ISO-8859-1 compatibility
                        try:
                            new_name.encode('iso-8859-1')
                            f_out.write(new_name + '\n')
                            replaced_count += 1

                            # Show first few replacements
                            if replaced_count <= 15:
                                print(f"  ✓ {station_name[:45]:45s} → {new_name[:55]}")
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
