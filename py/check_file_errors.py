#!/usr/bin/env python3
"""
Comprehensive check for errors in the harmonics file.
"""

import re
from collections import Counter

def extract_stations(input_file):
    """Extract all station data from the harmonics file."""
    with open(input_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    stations = []
    current_info = {}

    for i, line in enumerate(lines):
        if line.startswith('# !longitude:'):
            current_info['longitude'] = line.split(':')[1].strip()
        elif line.startswith('# !latitude:'):
            current_info['latitude'] = line.split(':')[1].strip()
        elif (i > 0 and
              lines[i-1].startswith('# !latitude:') and
              line.strip() and
              not line.startswith('#') and
              not line.startswith('x ') and
              not line.startswith('+') and
              not line.startswith('-') and
              len(line) > 0 and line[0].isalpha()):

            station_name = line.strip()
            timezone = lines[i + 1].strip() if i + 1 < len(lines) else ''

            stations.append({
                'line': i + 1,
                'name': station_name,
                'timezone': timezone,
                'latitude': current_info.get('latitude'),
                'longitude': current_info.get('longitude'),
            })

    return stations

def check_encoding_issues(stations):
    """Check for remaining encoding issues."""
    issues = []
    suspicious_patterns = [
        (r'Ã', 'UTF-8 als Latin-1 gelesen'),
        (r'Â', 'UTF-8 als Latin-1 gelesen'),
        (r'ï¿', 'BOM oder Encoding-Fehler'),
        (r'\?', 'Fragezeichen im Namen'),
        (r'[^\x00-\xff]', 'Nicht-Latin-1 Zeichen'),
    ]

    for station in stations:
        name = station['name']
        for pattern, description in suspicious_patterns:
            if re.search(pattern, name):
                issues.append({
                    'type': 'encoding',
                    'line': station['line'],
                    'name': name,
                    'problem': description,
                })
                break

    return issues

def check_truncated_names(stations):
    """Check for names that appear truncated (missing accents)."""
    issues = []

    # Patterns that suggest truncated characters
    truncated_patterns = [
        # Portuguese: São -> So, ão -> o, etc.
        (r'\bSo\b(?! )', 'Moeglicherweise "São" gemeint'),
        (r'\bao\b', 'Moeglicherweise "ão" gemeint'),
        # Missing common accents at word boundaries
        (r'polis\b', 'Moeglicherweise "polis" mit Akzent'),
        (r'uba\b', 'Moeglicherweise mit Akzent'),
    ]

    for station in stations:
        name = station['name']
        for pattern, description in truncated_patterns:
            if re.search(pattern, name):
                # Exclude already correct names
                if 'São' not in name and 'ão' not in name:
                    issues.append({
                        'type': 'truncated',
                        'line': station['line'],
                        'name': name,
                        'problem': description,
                    })
                    break

    return issues

def check_country_consistency(stations):
    """Check for inconsistent country names."""
    issues = []

    # Get all country names (last part after comma)
    countries = []
    for station in stations:
        parts = station['name'].split(', ')
        if len(parts) > 1:
            country = parts[-1].strip()
            # Remove parenthetical suffixes
            country = re.sub(r'\s*\([^)]*\)\s*$', '', country)
            countries.append(country)

    country_counts = Counter(countries)

    # Find similar country names that might be inconsistent
    country_list = list(country_counts.keys())
    for i, c1 in enumerate(country_list):
        for c2 in country_list[i+1:]:
            # Check for similar names
            if c1.lower() == c2.lower() and c1 != c2:
                issues.append({
                    'type': 'consistency',
                    'problem': f'Inkonsistente Schreibweise: "{c1}" ({country_counts[c1]}x) vs "{c2}" ({country_counts[c2]}x)',
                })

    return issues

def check_coordinates(stations):
    """Check for invalid or suspicious coordinates."""
    issues = []

    for station in stations:
        try:
            lat = float(station['latitude']) if station['latitude'] else None
            lon = float(station['longitude']) if station['longitude'] else None

            if lat is not None and (lat < -90 or lat > 90):
                issues.append({
                    'type': 'coordinates',
                    'line': station['line'],
                    'name': station['name'],
                    'problem': f'Ungueltige Breite: {lat}',
                })

            if lon is not None and (lon < -180 or lon > 180):
                issues.append({
                    'type': 'coordinates',
                    'line': station['line'],
                    'name': station['name'],
                    'problem': f'Ungueltige Laenge: {lon}',
                })

        except (ValueError, TypeError):
            issues.append({
                'type': 'coordinates',
                'line': station['line'],
                'name': station['name'],
                'problem': f'Koordinaten nicht lesbar: {station["latitude"]}, {station["longitude"]}',
            })

    return issues

def check_duplicates(stations):
    """Check for duplicate station names."""
    issues = []
    name_counts = Counter(s['name'] for s in stations)

    for name, count in name_counts.items():
        if count > 1 and '(2)' not in name and '(3)' not in name:
            issues.append({
                'type': 'duplicate',
                'problem': f'Doppelter Name: "{name}" ({count}x)',
            })

    return issues

def check_special_characters(stations):
    """Check for unusual special characters."""
    issues = []

    for station in stations:
        name = station['name']

        # Check for unusual characters
        unusual = re.findall(r'[^\w\s,.\'-áéíóúàèìòùâêîôûãõñçäöüßøåæœÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÑÇÄÖÜØÅÆŒ()´`]', name)
        if unusual:
            issues.append({
                'type': 'special_char',
                'line': station['line'],
                'name': name,
                'problem': f'Ungewoehnliche Zeichen: {unusual}',
            })

    return issues

def check_empty_or_short_names(stations):
    """Check for empty or suspiciously short names."""
    issues = []

    for station in stations:
        name = station['name']
        if len(name) < 3:
            issues.append({
                'type': 'short_name',
                'line': station['line'],
                'name': name,
                'problem': 'Name sehr kurz',
            })

    return issues

def main():
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'

    print("Lade Stationen...")
    stations = extract_stations(input_file)
    print(f"Gefunden: {len(stations)} Stationen\n")

    all_issues = []

    # Run all checks
    print("Pruefe auf Encoding-Fehler...")
    all_issues.extend(check_encoding_issues(stations))

    print("Pruefe auf abgeschnittene Namen...")
    all_issues.extend(check_truncated_names(stations))

    print("Pruefe Laendernamen-Konsistenz...")
    all_issues.extend(check_country_consistency(stations))

    print("Pruefe Koordinaten...")
    all_issues.extend(check_coordinates(stations))

    print("Pruefe auf Duplikate...")
    all_issues.extend(check_duplicates(stations))

    print("Pruefe auf ungewoehnliche Zeichen...")
    all_issues.extend(check_special_characters(stations))

    print("Pruefe auf kurze Namen...")
    all_issues.extend(check_empty_or_short_names(stations))

    # Print results
    print("\n" + "="*70)
    print(f"ERGEBNIS: {len(all_issues)} moegliche Probleme gefunden")
    print("="*70)

    if all_issues:
        # Group by type
        by_type = {}
        for issue in all_issues:
            t = issue['type']
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(issue)

        for issue_type, issues in by_type.items():
            print(f"\n### {issue_type.upper()} ({len(issues)} Probleme) ###")
            for issue in issues[:20]:  # Limit output
                if 'line' in issue:
                    print(f"  Zeile {issue['line']}: {issue.get('name', '')[:50]}")
                    print(f"    -> {issue['problem']}")
                else:
                    print(f"  {issue['problem']}")

            if len(issues) > 20:
                print(f"  ... und {len(issues) - 20} weitere")

    else:
        print("\nKeine Probleme gefunden!")

if __name__ == '__main__':
    main()
