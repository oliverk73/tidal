#!/usr/bin/env python3
"""
Create a mapping between missing reference station names and
their corresponding names in the harmonics file.
"""

import re
from difflib import SequenceMatcher

MISSING_FILE = '/home/oliver/subordinate_corrections/missing_ref_stations.txt'
HARMONICS_FILE = '/home/oliver/subordinate_corrections/harmonics_stations.txt'
OUTPUT_FILE = '/home/oliver/subordinate_corrections/ref_station_mapping.csv'

def load_stations(filename):
    """Load station names from file."""
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        return [line.strip() for line in f if line.strip()]

def normalize_name(name):
    """Normalize station name for comparison."""
    # Remove common variations
    name = name.lower()
    name = re.sub(r'\s*\(.*?\)\s*', ' ', name)  # Remove parenthetical content
    name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
    name = name.strip()
    return name

def extract_key_parts(name):
    """Extract key parts of the name for matching."""
    # Split by comma and take first part
    parts = name.split(',')
    return parts[0].strip().lower() if parts else name.lower()

def find_matches(missing_name, harmonics_stations, threshold=0.6):
    """Find potential matches for a missing station."""
    matches = []

    missing_norm = normalize_name(missing_name)
    missing_key = extract_key_parts(missing_name)

    for harm_name in harmonics_stations:
        # Skip current stations for tide predictions
        if 'Current' in harm_name:
            continue

        harm_norm = normalize_name(harm_name)
        harm_key = extract_key_parts(harm_name)

        # Check for exact key match
        if missing_key == harm_key:
            matches.append((harm_name, 1.0, 'exact_key'))
            continue

        # Check if key is contained
        if missing_key in harm_norm or harm_key in missing_norm:
            ratio = SequenceMatcher(None, missing_norm, harm_norm).ratio()
            if ratio > threshold:
                matches.append((harm_name, ratio, 'partial'))
                continue

        # Check similarity
        ratio = SequenceMatcher(None, missing_norm, harm_norm).ratio()
        if ratio > threshold:
            matches.append((harm_name, ratio, 'similar'))

    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:5]  # Return top 5 matches

def main():
    print("Loading station lists...")
    missing_stations = load_stations(MISSING_FILE)
    harmonics_stations = load_stations(HARMONICS_FILE)

    # Filter out Current stations from harmonics
    tide_stations = [s for s in harmonics_stations if 'Current' not in s]

    print(f"Missing reference stations: {len(missing_stations)}")
    print(f"Harmonics tide stations: {len(tide_stations)}")
    print()

    results = []

    for missing in missing_stations:
        matches = find_matches(missing, tide_stations)

        if matches:
            best_match = matches[0]
            result = {
                'missing': missing,
                'match': best_match[0],
                'score': best_match[1],
                'type': best_match[2],
                'alternatives': '; '.join([m[0] for m in matches[1:3]])
            }
        else:
            result = {
                'missing': missing,
                'match': '',
                'score': 0,
                'type': 'not_found',
                'alternatives': ''
            }

        results.append(result)

        # Print progress
        status = "FOUND" if result['match'] else "NOT FOUND"
        print(f"{status}: {missing}")
        if result['match']:
            print(f"       -> {result['match']} ({result['score']:.2f})")

    # Write results
    print(f"\nWriting results to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("missing_name;matched_name;score;match_type;alternatives\n")
        for r in results:
            f.write(f"{r['missing']};{r['match']};{r['score']:.2f};{r['type']};{r['alternatives']}\n")

    # Summary
    found = sum(1 for r in results if r['match'])
    print(f"\nSummary: {found}/{len(results)} stations matched")

    # Show not found
    not_found = [r['missing'] for r in results if not r['match']]
    if not_found:
        print(f"\nNot found ({len(not_found)}):")
        for nf in not_found:
            print(f"  - {nf}")

if __name__ == '__main__':
    main()
