#!/usr/bin/env python3
"""
Apply corrections for truncated accent characters.
"""

# Corrections: (old_name, new_name)
CORRECTIONS = [
    ('Baha Buen Suceso, Argentina', 'Bahía Buen Suceso, Argentina'),
    ('Baha Crossley, Argentina', 'Bahía Crossley, Argentina'),
    ('Baha Magdalena, Baja California Sur, Mexico', 'Bahía Magdalena, Baja California Sur, México'),
    ('Baha San Juanico, Baja California Sur, Mexico', 'Bahía San Juanico, Baja California Sur, México'),
    ('Baha San Julian (Punta Pena), Argentina', 'Bahía San Julián (Punta Peña), Argentina'),
    ('Baha San Sebastian, Argentina', 'Bahía San Sebastián, Argentina'),
    ('Baha Thetis, Argentina', 'Bahía Thetis, Argentina'),
    ('Baha de Ballenas, Baja California Sur, Mexico', 'Bahía de Ballenas, Baja California Sur, México'),
    ('Baha de los ngeles, Baja California Norte, Mexico', 'Bahía de los Ángeles, Baja California Norte, México'),
    ('Caleta la Misin, Argentina', 'Caleta la Misión, Argentina'),
    ('La Unin, El Salvador (2)', 'La Unión, El Salvador (2)'),
    ('Lazaro Cardenas, Michoacan, Mexico', 'Lázaro Cárdenas, Michoacán, México'),
    ('Malecon, Venezuela', 'Malecón, Venezuela'),
    ('Puerto de Baha Caraquez, Ecuador', 'Puerto de Bahía Caráquez, Ecuador'),
    ('Quequen, Argentina', 'Quequén, Argentina'),
    ('San Romn, Argentina', 'San Román, Argentina'),
]

def main():
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'

    # Read file as Latin-1
    with open(input_file, 'r', encoding='latin-1') as f:
        content = f.read()

    applied = 0
    not_found = []

    for old_name, new_name in CORRECTIONS:
        # Check if Latin-1 compatible
        try:
            new_name.encode('latin-1')
        except UnicodeEncodeError as e:
            print(f"WARNUNG: Nicht Latin-1 kompatibel: {new_name}")
            print(f"  Fehler: {e}")
            continue

        if old_name in content:
            content = content.replace(old_name, new_name, 1)
            applied += 1
            print(f"Korrigiert: {old_name}")
            print(f"       ->   {new_name}")
        else:
            not_found.append(old_name)

    # Write back as Latin-1
    with open(input_file, 'w', encoding='latin-1') as f:
        f.write(content)

    print(f"\n{'='*60}")
    print(f"Angewendete Korrekturen: {applied}")

    if not_found:
        print(f"\nNicht gefunden ({len(not_found)}):")
        for name in not_found:
            print(f"  {name}")

    # Create CSV file with all corrections
    csv_file = '/home/oliver/harmonics_working/alle_korrekturen.csv'
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write("Existierender Name;Korrigierter Name;Kategorie\n")
        for old_name, new_name in CORRECTIONS:
            f.write(f"{old_name};{new_name};Abgeschnittene Akzentzeichen\n")

    print(f"\nCSV-Datei erstellt: {csv_file}")

if __name__ == '__main__':
    main()
