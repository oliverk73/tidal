#!/usr/bin/env python3
"""
Vergleicht harmonics-dwf-20100529-nonfree.txt mit harmonics_pierre_lavergne_v10.txt
und entfernt Duplikate aus letzterer.
"""

import re
import os

def parse_stations(filename):
    """
    Parst eine Harmonics-Datei und gibt ein Dictionary zurück mit:
    - station_names: Set aller Stationsnamen
    - header: Header der Datei (vor den Stationen)
    - stations: Liste von Tupeln (name, full_block) für jede Station
    """
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    lines = content.split('\n')

    # Finde den Header (alles vor dem ersten "# BEGIN HOT COMMENTS" oder Station)
    # Der Header enthält die Constituent-Definitionen
    header_end = 0
    in_header = True

    # Suche nach dem Ende des Headers - Constituents-Datenblock gefolgt von erstem Stationsblock
    # Der Header endet nach den Equilibrium arguments und Node factors

    # Finde das erste Auftreten von "# BEGIN HOT COMMENTS" oder Stationsmetadaten
    for i, line in enumerate(lines):
        if line.strip().startswith('# BEGIN HOT COMMENTS'):
            header_end = i
            break
        # Alternative: Finde den Kommentarblock der ersten Station
        if line.strip().startswith('# country:') or line.strip().startswith('#country:'):
            # Gehe zurück zum Anfang des Kommentarblocks
            j = i
            while j > 0 and (lines[j-1].strip().startswith('#') or lines[j-1].strip() == ''):
                j -= 1
            header_end = j
            break

    # Wenn kein expliziter Marker gefunden wurde, suche nach dem ersten Stationsnamen
    # Stationsnamen sind Zeilen, die nicht mit # beginnen und nach den Equilibrium/Node-Daten kommen
    if header_end == 0:
        # Suche nach dem Muster, wo Stationen beginnen
        for i, line in enumerate(lines):
            # Nach den Node factors kommen die Stationen
            # Stationen haben typischerweise einen Namen, dann Zeitzone, dann "meters"
            if i > 200 and not line.startswith('#') and not line.startswith('x ') and line.strip():
                # Prüfe ob dies ein Stationsname sein könnte
                if 'meters' not in line and not re.match(r'^[A-Z0-9]+\s+[\d.]+', line):
                    # Könnte ein Stationsname sein, gehe zurück zum Kommentarblock
                    j = i - 1
                    while j > 0 and (lines[j].strip().startswith('#') or lines[j].strip() == ''):
                        j -= 1
                    header_end = j + 1
                    break

    header = '\n'.join(lines[:header_end])

    # Parse Stationen
    stations = []
    station_names = set()

    i = header_end
    while i < len(lines):
        # Suche nach dem Beginn eines Stationsblocks (Kommentare)
        block_start = None

        # Überspringe leere Zeilen
        while i < len(lines) and lines[i].strip() == '':
            i += 1

        if i >= len(lines):
            break

        # Sammle den Kommentarblock
        block_lines = []

        # Wenn Zeile mit # beginnt, ist es ein Kommentar
        if lines[i].strip().startswith('#'):
            while i < len(lines) and lines[i].strip().startswith('#'):
                block_lines.append(lines[i])
                i += 1

        # Überspringe leere Zeilen zwischen Kommentaren und Name
        while i < len(lines) and lines[i].strip() == '':
            block_lines.append(lines[i])
            i += 1

        if i >= len(lines):
            break

        # Jetzt sollte der Stationsname kommen
        # Der Name ist eine Zeile, die nicht mit # beginnt
        if not lines[i].strip().startswith('#') and lines[i].strip():
            station_name = lines[i].strip()
            block_lines.append(lines[i])
            i += 1

            # Zeitzone
            if i < len(lines):
                block_lines.append(lines[i])
                i += 1

            # Reference Level (meters)
            if i < len(lines):
                block_lines.append(lines[i])
                i += 1

            # Constituents (bis zum nächsten # oder Ende)
            while i < len(lines):
                line = lines[i]
                # Ende des Stationsblocks, wenn neuer Kommentarblock beginnt
                if line.strip().startswith('# ') and not line.strip().startswith('# country') and len(block_lines) > 10:
                    # Prüfe ob es ein neuer Stationsblock ist
                    if 'BEGIN HOT COMMENTS' in line or 'country:' in lines[i+1] if i+1 < len(lines) else False:
                        break
                if line.strip().startswith('#') and 'BEGIN HOT COMMENTS' in line:
                    break
                if line.strip().startswith('# country:'):
                    break

                block_lines.append(lines[i])
                i += 1

            if station_name and not station_name.startswith('#'):
                stations.append((station_name, '\n'.join(block_lines)))
                station_names.add(station_name)
        else:
            i += 1

    return {
        'station_names': station_names,
        'header': header,
        'stations': stations
    }


def parse_stations_v2(filename):
    """
    Verbesserte Version: Parst die Datei basierend auf dem "# BEGIN HOT COMMENTS" Marker.
    """
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Teile die Datei an "# BEGIN HOT COMMENTS"
    parts = content.split('# BEGIN HOT COMMENTS')

    # Header behalten wie er ist (inklusive trailing newlines)
    header = parts[0]

    stations = []
    station_names = set()

    for i, part in enumerate(parts[1:], 1):
        # Rekonstruiere den Block mit dem Marker
        block = '# BEGIN HOT COMMENTS' + part

        # Finde den Stationsnamen - erste Zeile nach den Kommentaren, die nicht mit # beginnt
        lines = block.split('\n')
        station_name = None

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                station_name = stripped
                break

        if station_name:
            # Entferne trailing Leerzeilen vom Block
            block = block.rstrip('\n')
            stations.append((station_name, block))
            station_names.add(station_name)

    return {
        'station_names': station_names,
        'header': header,
        'stations': stations
    }


def normalize_station_name(name):
    """
    Normalisiert einen Stationsnamen für den Vergleich:
    - Entfernt " - READ flaterco.com/pol.html" und ähnliche Suffixe
    - Konvertiert zu Kleinbuchstaben
    - Entfernt überflüssige Leerzeichen
    """
    # Entferne bekannte Suffixe
    suffixes_to_remove = [
        ' - READ flaterco.com/pol.html',
        ' (Port of Bristol)',
        ' - England',
        ' - Wales',
        ' - Scotland',
        ' - Northern Ireland',
    ]
    normalized = name
    for suffix in suffixes_to_remove:
        normalized = normalized.replace(suffix, '')

    # Konvertiere zu Kleinbuchstaben und entferne extra Leerzeichen
    normalized = normalized.lower().strip()
    normalized = ' '.join(normalized.split())

    return normalized


def main():
    dwf_file = '/home/oliver/harmonics/harmonics-dwf-20100529-nonfree.txt'
    pierre_file = '/home/oliver/harmonics/harmonics_pierre_lavergne_v10.txt'
    output_file = '/home/oliver/harmonics/harmonics_pierre_lavergne_v10_no_dupes1.txt'
    deleted_csv = '/home/oliver/harmonics/deleted_stations_pierre_v10.csv'

    print("Parsing DWF file...")
    dwf_data = parse_stations_v2(dwf_file)
    print(f"  Found {len(dwf_data['stations'])} stations in DWF file")

    print("\nParsing Pierre Lavergne file...")
    pierre_data = parse_stations_v2(pierre_file)
    print(f"  Found {len(pierre_data['stations'])} stations in Pierre file")

    # Erstelle normalisierte Name-Mappings
    dwf_normalized = {normalize_station_name(name): name for name in dwf_data['station_names']}
    pierre_normalized = {normalize_station_name(name): name for name in pierre_data['station_names']}

    # Finde Duplikate basierend auf normalisierten Namen
    duplicate_normalized = set(dwf_normalized.keys()) & set(pierre_normalized.keys())
    duplicates = {pierre_normalized[norm_name] for norm_name in duplicate_normalized}

    print(f"\nFound {len(duplicates)} duplicate stations (normalized comparison)")

    # Filtere Stationen
    kept_stations = []
    deleted_stations = []

    for name, block in pierre_data['stations']:
        if name in duplicates:
            deleted_stations.append(name)
        else:
            kept_stations.append((name, block))

    print(f"Keeping {len(kept_stations)} stations")
    print(f"Removing {len(deleted_stations)} stations")

    # Schreibe die bereinigte Datei
    print(f"\nWriting cleaned file to {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        # Header schreiben (endet bereits mit Zeilenumbruch)
        f.write(pierre_data['header'])
        # Stationsblöcke direkt anhängen (jeder Block beginnt mit "# BEGIN HOT COMMENTS")
        for name, block in kept_stations:
            f.write(block)
            # Nur Zeilenumbruch am Ende wenn Block nicht damit endet
            if not block.endswith('\n'):
                f.write('\n')

    # Schreibe CSV der gelöschten Stationen mit DWF-Gegenstück
    print(f"Writing deleted stations to {deleted_csv}")
    with open(deleted_csv, 'w', encoding='utf-8') as f:
        f.write("Pierre Lavergne Station;DWF Station\n")
        for name in sorted(deleted_stations):
            norm_name = normalize_station_name(name)
            dwf_name = dwf_normalized.get(norm_name, '')
            f.write(f'"{name}";"{dwf_name}"\n')

    print("\nDone!")

    # Zeige alle Duplikate mit ihren Gegenstücken
    print("\nAll duplicates found:")
    for name in sorted(deleted_stations):
        norm_name = normalize_station_name(name)
        dwf_name = dwf_normalized.get(norm_name, '')
        print(f"  Pierre: {name}")
        print(f"  DWF:    {dwf_name}")
        print()


if __name__ == '__main__':
    main()
