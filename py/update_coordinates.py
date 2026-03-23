#!/usr/bin/env python3
import csv
import re
import os
from pathlib import Path

# Read the CSV file with corrections
csv_file = '/home/oliver/harmonics_working/Geokoordinaten-Korrektur.csv'
harmonics_dir = '/home/oliver/harmonics_working'

# Read corrections - try different encodings
corrections = []
encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
for encoding in encodings:
    try:
        with open(csv_file, 'r', encoding=encoding) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Tidenstation']:  # Skip empty rows
                    station_name = row['Tidenstation'].strip()
                    lat = row['Breitengrad'].replace(',', '.')
                    lon = row['Längengrad'].replace(',', '.')
                    corrections.append({
                        'name': station_name,
                        'lat': lat,
                        'lon': lon
                    })
        print(f"Successfully read CSV with {encoding} encoding")
        break
    except (UnicodeDecodeError, KeyError) as e:
        corrections = []
        continue

print(f"Loaded {len(corrections)} coordinate corrections")

# Get all harmonics text files
harmonics_files = [
    'harmonics-dwf-20241229-free.txt',
    'harmonics-dwf-20070318_no_us_no_dupes.txt',
    'harmonics-2004-06-14_no_us_no_dupes2.txt',
    'harmonics_pierre_lavergne_v10_no_dupes4.txt',
    'harmonics_pierre_lavergne_v9_europe_no_us_no_dupes5.txt',
    'harmonics-dwf-20100529-nonfree.txt',
    'harmonics_old_no_us_no_dupes3.txt'
]

# Track results
found_matches = []
multiple_matches = []
no_matches = []

# For each correction
for correction in corrections:
    station_name = correction['name']
    new_lat = correction['lat']
    new_lon = correction['lon']

    # Search for this station in all files
    matches = []

    for harmonics_file in harmonics_files:
        file_path = os.path.join(harmonics_dir, harmonics_file)
        if not os.path.exists(file_path):
            continue

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                # Check if this line contains the station name
                # Station names are on their own line, not starting with #
                if not line.startswith('#') and not line.startswith('x ') and station_name in line:
                    # Check if this looks like a station name line
                    # (not timezone, not unit, not constituent)
                    stripped = line.strip()
                    if stripped and not stripped.startswith('+') and not stripped.startswith('-') and 'meters' not in stripped and 'feet' not in stripped and 'knots' not in stripped:
                        # Look for coordinates in previous lines
                        lat_line = None
                        lon_line = None
                        for j in range(max(0, i-5), i):
                            if lines[j].startswith('# !latitude:'):
                                lat_line = j
                            if lines[j].startswith('# !longitude:'):
                                lon_line = j

                        if lat_line is not None and lon_line is not None:
                            matches.append({
                                'file': harmonics_file,
                                'station_line': i,
                                'station_text': stripped,
                                'lat_line': lat_line,
                                'lon_line': lon_line,
                                'old_lat': lines[lat_line].strip(),
                                'old_lon': lines[lon_line].strip()
                            })
        except Exception as e:
            print(f"Error reading {harmonics_file}: {e}")
            continue

    if len(matches) == 0:
        no_matches.append({
            'name': station_name,
            'new_lat': new_lat,
            'new_lon': new_lon
        })
    elif len(matches) == 1:
        found_matches.append({
            'name': station_name,
            'new_lat': new_lat,
            'new_lon': new_lon,
            'match': matches[0]
        })
    else:
        multiple_matches.append({
            'name': station_name,
            'new_lat': new_lat,
            'new_lon': new_lon,
            'matches': matches
        })

# Print summary
print(f"\n=== SUMMARY ===")
print(f"Unique matches found: {len(found_matches)}")
print(f"Multiple matches found: {len(multiple_matches)}")
print(f"No matches found: {len(no_matches)}")

# Print details
if no_matches:
    print(f"\n=== NO MATCHES ({len(no_matches)}) ===")
    for item in no_matches:
        print(f"  - {item['name']}")

if multiple_matches:
    print(f"\n=== MULTIPLE MATCHES ({len(multiple_matches)}) ===")
    for item in multiple_matches:
        print(f"  - {item['name']}: {len(item['matches'])} matches")
        for match in item['matches']:
            print(f"      {match['file']}: {match['station_text']}")

# Save results for review
with open('/home/oliver/coordinate_update_plan.txt', 'w', encoding='utf-8') as f:
    f.write("=== COORDINATE UPDATE PLAN ===\n\n")

    f.write(f"Unique matches to update: {len(found_matches)}\n")
    f.write(f"Multiple matches (need review): {len(multiple_matches)}\n")
    f.write(f"No matches found: {len(no_matches)}\n\n")

    f.write("=== UNIQUE MATCHES ===\n")
    for item in found_matches:
        match = item['match']
        f.write(f"\nStation: {item['name']}\n")
        f.write(f"File: {match['file']}\n")
        f.write(f"Line {match['station_line']}: {match['station_text']}\n")
        f.write(f"Old: {match['old_lat']} / {match['old_lon']}\n")
        f.write(f"New: # !latitude: {item['new_lat']} / # !longitude: {item['new_lon']}\n")

    f.write("\n\n=== MULTIPLE MATCHES (NEED REVIEW) ===\n")
    for item in multiple_matches:
        f.write(f"\nStation: {item['name']}\n")
        f.write(f"New coordinates: {item['new_lat']}, {item['new_lon']}\n")
        f.write(f"Found {len(item['matches'])} matches:\n")
        for idx, match in enumerate(item['matches'], 1):
            f.write(f"  {idx}. {match['file']}: {match['station_text']}\n")
            f.write(f"     {match['old_lat']} / {match['old_lon']}\n")

    f.write("\n\n=== NO MATCHES FOUND ===\n")
    for item in no_matches:
        f.write(f"  - {item['name']} (new: {item['new_lat']}, {item['new_lon']})\n")

print(f"\nDetailed plan saved to: /home/oliver/coordinate_update_plan.txt")
