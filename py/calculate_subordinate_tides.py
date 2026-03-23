#!/usr/bin/env python3
"""
Calculate tides for subordinate stations based on reference station tides
and correction values for 14.12.2025.
"""

import re
import csv
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict

INPUT_FILE = "subordinate_stations.csv"
OUTPUT_FILE = "subordinate_stations_with_tides.csv"
TARGET_DATE = "2025-12-14"

def get_reference_tides(station_name):
    """Get tide predictions for a reference station using the tide command."""
    try:
        # Run tide command for the specific date
        cmd = [
            "tide",
            "-l", station_name,
            "-b", f"{TARGET_DATE} 00:00",
            "-e", f"{TARGET_DATE} 23:59",
            "-m", "p"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return None

        output = result.stdout

        # Parse the output to find High Tide and Low Tide entries
        tides = {
            'high': [],  # List of (time, level) tuples
            'low': []    # List of (time, level) tuples
        }

        for line in output.split('\n'):
            line = line.strip()

            # Match patterns like:
            # 2025-12-14  9:18 PM CET   3.40 meters  High Tide
            # 2025-12-14  2:11 AM CET   0.52 meters  Low Tide

            high_match = re.search(
                r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+\w+\s+(-?\d+\.?\d*)\s+meters?\s+High\s+Tide',
                line, re.IGNORECASE
            )

            low_match = re.search(
                r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+\w+\s+(-?\d+\.?\d*)\s+meters?\s+Low\s+Tide',
                line, re.IGNORECASE
            )

            if high_match:
                date_str = high_match.group(1)
                time_str = high_match.group(2)
                level = float(high_match.group(3))

                # Parse time
                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
                tides['high'].append((dt, level))

            elif low_match:
                date_str = low_match.group(1)
                time_str = low_match.group(2)
                level = float(low_match.group(3))

                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
                tides['low'].append((dt, level))

        return tides

    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"Error getting tides for {station_name}: {e}")
        return None

def calculate_subordinate_tides(ref_tides, hmin, hmpy, hoff, lmin, lmpy, loff):
    """Calculate subordinate station tides based on reference tides and corrections."""
    if not ref_tides:
        return None

    result = {
        'high': [],
        'low': []
    }

    # Convert correction values from German format (comma) to float
    def to_float(val):
        if isinstance(val, str):
            return float(val.replace(',', '.'))
        return float(val)

    hmin_val = to_float(hmin)
    hmpy_val = to_float(hmpy)
    hoff_val = to_float(hoff)
    lmin_val = to_float(lmin)
    lmpy_val = to_float(lmpy)
    loff_val = to_float(loff)

    # Calculate high tides
    for dt, level in ref_tides.get('high', []):
        new_dt = dt + timedelta(minutes=hmin_val)
        new_level = (level * hmpy_val) + hoff_val
        result['high'].append((new_dt, new_level))

    # Calculate low tides
    for dt, level in ref_tides.get('low', []):
        new_dt = dt + timedelta(minutes=lmin_val)
        new_level = (level * lmpy_val) + loff_val
        result['low'].append((new_dt, new_level))

    return result

def format_time(dt):
    """Format datetime as HH:MM"""
    if dt:
        return dt.strftime("%H:%M")
    return ""

def format_level(level):
    """Format level with comma as decimal separator"""
    if level is not None:
        return f"{level:.2f}".replace('.', ',')
    return ""

def main():
    # Read the CSV file
    stations = []
    reference_stations = set()

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            stations.append(row)
            reference_stations.add(row['Reference Station'])

    print(f"Geladene Stationen: {len(stations)}")
    print(f"Einzigartige Reference Stations: {len(reference_stations)}")

    # Get tides for all reference stations
    print("\nRufe Tiden für Reference Stations ab...")
    ref_tides_cache = {}

    for i, ref_name in enumerate(sorted(reference_stations)):
        print(f"  [{i+1}/{len(reference_stations)}] {ref_name}...", end=" ", flush=True)
        tides = get_reference_tides(ref_name)

        if tides and (tides['high'] or tides['low']):
            ref_tides_cache[ref_name] = tides
            high_count = len(tides['high'])
            low_count = len(tides['low'])
            print(f"OK ({high_count} HW, {low_count} NW)")
        else:
            print("NICHT GEFUNDEN")

    print(f"\nGefundene Reference Stations: {len(ref_tides_cache)}")

    # Calculate tides for all subordinate stations
    print("\nBerechne Tiden für subordinate Stations...")

    results = []
    success_count = 0

    for station in stations:
        ref_name = station['Reference Station']
        ref_tides = ref_tides_cache.get(ref_name)

        if ref_tides:
            sub_tides = calculate_subordinate_tides(
                ref_tides,
                station['Hmin (High Tide Time Add)'],
                station['Hmpy (High Tide Level Multiply)'],
                station['Hoff (High Tide Level Add)'],
                station['Lmin (Low Tide Time Add)'],
                station['Lmpy (Low Tide Level Multiply)'],
                station['Loff (Low Tide Level Add)']
            )

            if sub_tides:
                success_count += 1

                # Get first and second high/low tides for the day
                high1_time = format_time(sub_tides['high'][0][0]) if len(sub_tides['high']) > 0 else ""
                high1_level = format_level(sub_tides['high'][0][1]) if len(sub_tides['high']) > 0 else ""
                high2_time = format_time(sub_tides['high'][1][0]) if len(sub_tides['high']) > 1 else ""
                high2_level = format_level(sub_tides['high'][1][1]) if len(sub_tides['high']) > 1 else ""

                low1_time = format_time(sub_tides['low'][0][0]) if len(sub_tides['low']) > 0 else ""
                low1_level = format_level(sub_tides['low'][0][1]) if len(sub_tides['low']) > 0 else ""
                low2_time = format_time(sub_tides['low'][1][0]) if len(sub_tides['low']) > 1 else ""
                low2_level = format_level(sub_tides['low'][1][1]) if len(sub_tides['low']) > 1 else ""
            else:
                high1_time = high1_level = high2_time = high2_level = ""
                low1_time = low1_level = low2_time = low2_level = ""
        else:
            high1_time = high1_level = high2_time = high2_level = ""
            low1_time = low1_level = low2_time = low2_level = ""

        results.append({
            **station,
            'HW1_Zeit': high1_time,
            'HW1_Stand': high1_level,
            'HW2_Zeit': high2_time,
            'HW2_Stand': high2_level,
            'NW1_Zeit': low1_time,
            'NW1_Stand': low1_level,
            'NW2_Zeit': low2_time,
            'NW2_Stand': low2_level
        })

    # Write output CSV
    print(f"\nSchreibe Ausgabedatei...")

    fieldnames = [
        'Station Name', 'Reference Station', 'Longitude', 'Latitude', 'Timezone',
        'Hmin (High Tide Time Add)', 'Hmpy (High Tide Level Multiply)', 'Hoff (High Tide Level Add)',
        'Lmin (Low Tide Time Add)', 'Lmpy (Low Tide Level Multiply)', 'Loff (Low Tide Level Add)',
        'HW1_Zeit', 'HW1_Stand', 'HW2_Zeit', 'HW2_Stand',
        'NW1_Zeit', 'NW1_Stand', 'NW2_Zeit', 'NW2_Stand'
    ]

    with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(results)

    print(f"\nFertig!")
    print(f"Stationen mit berechneten Tiden: {success_count}")
    print(f"Ausgabedatei: {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
