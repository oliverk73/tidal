#!/usr/bin/env python3
"""
Vergleicht Tidenstationen aus zwei Harmonics-Dateien und findet mögliche Matches
basierend auf Name, Zeitzone, Geokoordinaten (3 km Umkreis) und Anzahl der Konstanten.
"""

import re
import csv
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass(frozen=True)
class TideStation:
    name: str
    timezone: str
    latitude: float
    longitude: float
    num_constants: int
    line_number: int


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Berechnet die Entfernung zwischen zwei Punkten auf der Erdoberfläche in km.
    """
    R = 6371  # Erdradius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def parse_harmonics_file(filepath: str) -> List[TideStation]:
    """
    Parst eine Harmonics-Datei und extrahiert alle Stationen.
    """
    stations = []

    with open(filepath, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Suche nach BEGIN HOT COMMENTS
        if line == '# BEGIN HOT COMMENTS':
            latitude = None
            longitude = None

            # Parse die HOT COMMENTS
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('# !latitude:') and \
                  not lines[i].strip().startswith('# !longitude:') and \
                  not (lines[i].strip() and not lines[i].strip().startswith('#')):
                comment_line = lines[i].strip()
                if comment_line.startswith('# !latitude:'):
                    try:
                        latitude = float(comment_line.split(':')[1].strip())
                    except:
                        pass
                elif comment_line.startswith('# !longitude:'):
                    try:
                        longitude = float(comment_line.split(':')[1].strip())
                    except:
                        pass
                i += 1

            # Weiter parsen für latitude/longitude
            while i < len(lines):
                comment_line = lines[i].strip()
                if comment_line.startswith('# !latitude:'):
                    try:
                        latitude = float(comment_line.split(':')[1].strip())
                    except:
                        pass
                elif comment_line.startswith('# !longitude:'):
                    try:
                        longitude = float(comment_line.split(':')[1].strip())
                    except:
                        pass
                elif comment_line and not comment_line.startswith('#'):
                    # Das ist der Stationsname
                    break
                i += 1

            if i >= len(lines):
                break

            # Stationsname
            station_name = lines[i].strip()
            station_line = i + 1  # 1-indexed
            i += 1

            if i >= len(lines):
                break

            # Zeitzone
            timezone_line = lines[i].strip()
            # Format: "0:00 :Europe/London" oder "+00:00 :Europe/London"
            timezone = timezone_line
            i += 1

            if i >= len(lines):
                break

            # Datum-Zeile (überspringen)
            i += 1

            # Zähle harmonische Konstanten (nicht "x 0 0")
            num_constants = 0
            while i < len(lines):
                const_line = lines[i].strip()
                # Ende wenn nächste Station oder Kommentar oder leer
                if const_line.startswith('# BEGIN HOT COMMENTS') or \
                   const_line.startswith('# country:') or \
                   (const_line.startswith('#') and 'HOT COMMENTS' in const_line):
                    break
                if const_line.startswith('#'):
                    i += 1
                    continue
                if not const_line:
                    i += 1
                    continue
                # Prüfe ob es eine Konstanten-Zeile ist
                parts = const_line.split()
                if len(parts) >= 3:
                    if parts[0] != 'x' and parts[1] != '0':
                        num_constants += 1
                elif len(parts) == 2:
                    # Manche haben nur 2 Felder
                    pass
                i += 1

                # Wenn wir auf einen neuen HOT COMMENTS Block stoßen, brechen wir ab
                if i < len(lines) and '# BEGIN HOT COMMENTS' in lines[i]:
                    break

            if latitude is not None and longitude is not None:
                # Strömungsstationen ausschließen (enthalten "Current" im Namen)
                if ', Current' not in station_name and station_name.endswith(', Current') == False:
                    stations.append(TideStation(
                        name=station_name,
                        timezone=timezone,
                        latitude=latitude,
                        longitude=longitude,
                        num_constants=num_constants,
                        line_number=station_line
                    ))
        else:
            i += 1

    return stations


def normalize_name(name: str) -> str:
    """Normalisiert einen Stationsnamen für den Vergleich."""
    # Kleinbuchstaben und Sonderzeichen entfernen
    name = name.lower()
    name = re.sub(r'[,\(\)\[\]\'\".-]', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def names_similar(name1: str, name2: str) -> bool:
    """Prüft ob zwei Namen ähnlich sind."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    # Exakte Übereinstimmung nach Normalisierung
    if n1 == n2:
        return True

    # Einer ist Teil des anderen
    if n1 in n2 or n2 in n1:
        return True

    # Erste Wörter stimmen überein
    words1 = n1.split()
    words2 = n2.split()
    if words1 and words2 and words1[0] == words2[0]:
        return True

    return False


def timezones_match(tz1: str, tz2: str) -> bool:
    """Prüft ob zwei Zeitzonen übereinstimmen."""
    # Extrahiere die Zeitzone (z.B. :Europe/London)
    def extract_tz(tz):
        if ':' in tz:
            parts = tz.split(':')
            for p in parts:
                if '/' in p:
                    return p.strip()
        return tz.strip()

    tz1_clean = extract_tz(tz1)
    tz2_clean = extract_tz(tz2)

    if tz1_clean == tz2_clean:
        return True

    # Auch den Offset vergleichen
    def extract_offset(tz):
        match = re.search(r'([+-]?\d{1,2}):?(\d{2})?', tz)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2)) if match.group(2) else 0
            return hours * 60 + minutes
        return None

    offset1 = extract_offset(tz1)
    offset2 = extract_offset(tz2)

    if offset1 is not None and offset2 is not None:
        return offset1 == offset2

    return False


def find_matches(stations1: List[TideStation], stations2: List[TideStation],
                 max_distance_km: float = 4.0) -> dict:
    """
    Findet Matches zwischen zwei Stationslisten.
    Gibt ein Dictionary zurück: station1 -> [(station2, distance, name_match, tz_match, constants_match), ...]
    """
    matches = {}

    for s1 in stations1:
        station_matches = []
        for s2 in stations2:
            distance = haversine_distance(s1.latitude, s1.longitude, s2.latitude, s2.longitude)

            # Nur Stationen im Umkreis von max_distance_km betrachten
            if distance <= max_distance_km:
                name_match = names_similar(s1.name, s2.name)
                tz_match = timezones_match(s1.timezone, s2.timezone)
                constants_match = abs(s1.num_constants - s2.num_constants) <= 5  # Toleranz von 5

                station_matches.append((s2, distance, name_match, tz_match, constants_match))

        if station_matches:
            # Sortiere nach Entfernung
            station_matches.sort(key=lambda x: x[1])
            matches[s1] = station_matches

    return matches


def main():
    file1 = 'harmonics/classic/harmonics_pierre_lavergne_v10_no_dupes4.txt'
    file2 = 'harmonics/classic/harmonics_old_no_us_no_dupes3.txt'
    output_csv = 'harmonics_station_matches_pierre_lavergne_v10_harmonics_old.csv'

    print(f"Parsing {file1}...")
    stations1 = parse_harmonics_file(file1)
    print(f"  Gefunden: {len(stations1)} Stationen")

    print(f"Parsing {file2}...")
    stations2 = parse_harmonics_file(file2)
    print(f"  Gefunden: {len(stations2)} Stationen")

    print(f"\nSuche Matches (max. 4 km Entfernung)...")
    matches = find_matches(stations1, stations2, max_distance_km=4.0)
    print(f"  Gefunden: {len(matches)} Stationen mit Matches")

    # Zähle Gesamtzahl der Matches
    total_matches = sum(len(m) for m in matches.values())
    print(f"  Gesamt: {total_matches} einzelne Matches")

    # Finde maximale Anzahl Matches pro Station für Header
    max_matches = max(len(m) for m in matches.values()) if matches else 0

    # Schreibe CSV
    print(f"\nSchreibe {output_csv}...")
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header erstellen
        header = ['Name_PLV', 'Timezone_PLV', 'Lat_PLV', 'Lon_PLV', 'Constants_PLV']
        for i in range(1, max_matches + 1):
            header.extend([
                f'Name_OLD_{i}', f'Timezone_OLD_{i}', f'Lat_OLD_{i}', f'Lon_OLD_{i}',
                f'Constants_OLD_{i}', f'Distance_km_{i}'
            ])
        writer.writerow(header)

        # Sortiere nach Name der PLV-Station
        sorted_stations = sorted(matches.keys(), key=lambda s: s.name)

        for s1 in sorted_stations:
            row = [s1.name, s1.timezone, s1.latitude, s1.longitude, s1.num_constants]

            for s2, distance, name_match, tz_match, const_match in matches[s1]:
                row.extend([
                    s2.name, s2.timezone, s2.latitude, s2.longitude, s2.num_constants,
                    f"{distance:.3f}".replace('.', ',')
                ])

            writer.writerow(row)

    print(f"Fertig! {len(matches)} Stationen mit Matches in {output_csv} geschrieben.")

    # Zeige einige Beispiele
    print("\nErste 10 Stationen mit Matches:")
    for i, s1 in enumerate(sorted_stations[:10]):
        match_names = [m[0].name[:30] for m in matches[s1]]
        print(f"  {s1.name[:40]:40} -> {len(matches[s1])} Match(es): {', '.join(match_names)}")


if __name__ == '__main__':
    main()
