#!/usr/bin/env python3
"""
Extrahiert Tidenstationen aus beiden Harmonics-Dateien und findet Matches.
Schreibt Ergebnisse in eine CSV-Datei.
"""

import re
import csv
from math import radians, sin, cos, sqrt, atan2
from difflib import SequenceMatcher

def haversine_distance(lat1, lon1, lat2, lon2):
    """Berechnet die Distanz zwischen zwei Punkten in km."""
    if None in (lat1, lon1, lat2, lon2):
        return float('inf')
    R = 6371  # Erdradius in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def parse_harmonics_file(filepath):
    """
    Parst eine Harmonics-Datei und gibt eine Liste von Stationen zurück.
    Jede Station ist ein Dict mit name, timezone, longitude, latitude, harmonic_count.
    """
    stations = []

    with open(filepath, 'r', encoding='latin-1') as f:
        content = f.read()

    # Finde alle Stationsblöcke
    # Ein Block beginnt mit "# BEGIN HOT COMMENTS" und endet vor dem nächsten "# BEGIN HOT COMMENTS" oder Ende
    blocks = re.split(r'# BEGIN HOT COMMENTS\n', content)

    for block in blocks[1:]:  # Erster Block ist der Header
        station = {
            'name': None,
            'timezone': None,
            'longitude': None,
            'latitude': None,
            'harmonic_count': 0
        }

        lines = block.split('\n')

        # Parse Metadaten aus Kommentaren
        i = 0
        while i < len(lines) and lines[i].startswith('#'):
            line = lines[i]
            if '!longitude:' in line:
                match = re.search(r'!longitude:\s*([-\d.]+)', line)
                if match:
                    station['longitude'] = float(match.group(1))
            elif '!latitude:' in line:
                match = re.search(r'!latitude:\s*([-\d.]+)', line)
                if match:
                    station['latitude'] = float(match.group(1))
            i += 1

        # Nächste Zeile sollte der Stationsname sein
        if i < len(lines) and lines[i].strip():
            station['name'] = lines[i].strip()
            i += 1

        # Nächste Zeile ist die Zeitzone
        if i < len(lines) and lines[i].strip():
            station['timezone'] = lines[i].strip()
            i += 1

        # Überspringe die Einheiten-Zeile (z.B. "6.71 meters")
        if i < len(lines) and ('meters' in lines[i] or 'feet' in lines[i] or 'knots' in lines[i]):
            i += 1

        # Zähle harmonic constants (nicht "x 0 0")
        harmonic_count = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('#'):
                # Nächster Block oder Ende
                if '# BEGIN HOT COMMENTS' in line or line == '':
                    break
                i += 1
                continue

            # Eine harmonic constant Zeile
            if line and not line.startswith('x '):
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        amp = float(parts[1])
                        if amp != 0:
                            harmonic_count += 1
                    except ValueError:
                        pass
            i += 1

        station['harmonic_count'] = harmonic_count

        if station['name']:
            stations.append(station)

    return stations

def normalize_name(name):
    """Normalisiert einen Stationsnamen für den Vergleich."""
    if not name:
        return ""
    # Entferne Sonderzeichen und konvertiere zu lowercase
    normalized = name.lower()
    # Entferne Kommas und Klammern
    normalized = re.sub(r'[,\(\)\[\]]', ' ', normalized)
    # Normalisiere Leerzeichen
    normalized = ' '.join(normalized.split())
    return normalized

def name_similarity(name1, name2):
    """Berechnet die Ähnlichkeit zweier Namen (0-1)."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    return SequenceMatcher(None, norm1, norm2).ratio()

def find_matches(source_station, target_stations, max_distance_km=2, min_name_similarity=0.4):
    """
    Findet mögliche Matches für eine Quellstation in der Ziel-Liste.
    BEIDE Kriterien müssen erfüllt sein: Namensähnlichkeit UND Distanz <= 2km.
    Stationen mit "Current" im Namen (Strömungsstationen) werden ausgeschlossen.
    Gibt eine Liste von (score, station, distance) Tupeln zurück, sortiert nach Score (absteigend).
    """
    matches = []

    # Überspringe Strömungsstationen (Current am Ende des Namens)
    if source_station['name'] and source_station['name'].rstrip().endswith('Current'):
        return matches

    for target in target_stations:
        # Überspringe Strömungsstationen (Current am Ende des Namens)
        if target['name'] and target['name'].rstrip().endswith('Current'):
            continue
        # Prüfe zuerst die geographische Nähe (MUSS erfüllt sein)
        if not (source_station['longitude'] and source_station['latitude'] and
                target['longitude'] and target['latitude']):
            continue

        distance = haversine_distance(
            source_station['latitude'], source_station['longitude'],
            target['latitude'], target['longitude']
        )

        # Strenge Distanz-Prüfung: maximal 2 km
        if distance > max_distance_km:
            continue

        # Namensähnlichkeit prüfen (MUSS auch erfüllt sein)
        name_sim = name_similarity(source_station['name'], target['name'])
        if name_sim < min_name_similarity:
            continue

        # Score berechnen für Ranking
        score = name_sim * 50 + (1 - distance / max_distance_km) * 30

        # Bonus für Zeitzone-Übereinstimmung
        if source_station['timezone'] and target['timezone']:
            src_tz = source_station['timezone'].split(':')[0] if source_station['timezone'] else ""
            tgt_tz = target['timezone'].split(':')[0] if target['timezone'] else ""
            if src_tz == tgt_tz:
                score += 10

        # Bonus für ähnliche Anzahl harmonischer Konstanten
        if source_station['harmonic_count'] > 0 and target['harmonic_count'] > 0:
            hc_diff = abs(source_station['harmonic_count'] - target['harmonic_count'])
            if hc_diff <= 10:
                score += 10 * (1 - hc_diff / 10)

        matches.append((score, target, distance))

    # Sortiere nach Score (absteigend)
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[:3]  # Maximal 3 beste Matches

def main():
    pierre_file = '/home/oliver/harmonics_working/harmonics_pierre_lavergne_v10_no_dupes4.txt'
    dwf_file = '/home/oliver/harmonics_working/harmonics-dwf-20070318_no_us_no_dupes.txt'
    output_csv = '/home/oliver/station_matches.csv'

    print(f"Lese {pierre_file}...")
    pierre_stations = parse_harmonics_file(pierre_file)
    print(f"  -> {len(pierre_stations)} Stationen gefunden")

    print(f"Lese {dwf_file}...")
    dwf_stations = parse_harmonics_file(dwf_file)
    print(f"  -> {len(dwf_stations)} Stationen gefunden")

    print(f"\nSuche Matches und schreibe nach {output_csv}...")

    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')

        # Header
        header = [
            'Pierre_Name', 'Pierre_Timezone', 'Pierre_Longitude', 'Pierre_Latitude', 'Pierre_HarmonicCount',
            'Match1_Score', 'Match1_Distance_km', 'Match1_Name', 'Match1_Timezone', 'Match1_Longitude', 'Match1_Latitude', 'Match1_HarmonicCount',
            'Match2_Score', 'Match2_Distance_km', 'Match2_Name', 'Match2_Timezone', 'Match2_Longitude', 'Match2_Latitude', 'Match2_HarmonicCount',
            'Match3_Score', 'Match3_Distance_km', 'Match3_Name', 'Match3_Timezone', 'Match3_Longitude', 'Match3_Latitude', 'Match3_HarmonicCount'
        ]
        writer.writerow(header)

        match_count = 0
        for station in pierre_stations:
            matches = find_matches(station, dwf_stations)

            row = [
                station['name'],
                station['timezone'],
                station['longitude'],
                station['latitude'],
                station['harmonic_count']
            ]

            if matches:
                match_count += 1

            for i in range(3):
                if i < len(matches):
                    score, match, distance = matches[i]
                    row.extend([
                        f"{score:.1f}",
                        f"{distance:.2f}",
                        match['name'],
                        match['timezone'],
                        match['longitude'],
                        match['latitude'],
                        match['harmonic_count']
                    ])
                else:
                    row.extend(['', '', '', '', '', '', ''])

            writer.writerow(row)

    print(f"\nFertig! {match_count} von {len(pierre_stations)} Stationen haben mindestens einen Match.")
    print(f"Ergebnis gespeichert in: {output_csv}")

if __name__ == '__main__':
    main()
