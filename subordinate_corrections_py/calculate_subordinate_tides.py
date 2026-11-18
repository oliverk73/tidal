#!/usr/bin/env python3
"""
Calculate tide predictions for subordinate stations using xtide.
Applies corrections (hmin, hmpy, hoff, lmin, lmpy, loff) to reference station tides.
"""

import csv
import subprocess
import re
from datetime import datetime, timedelta
from collections import defaultdict

# Reference station name mappings (old name -> harmonics name)
REF_STATION_MAPPING = {
    'Galveston (Galveston Channel), Texas': 'Galveston Pier 21, Galveston Channel, Texas',
    'Hampton Roads, Virginia': 'Sewells Point, Hampton Roads, Virginia',
    'Harrington Harbour, Québec': 'Harrington Harbour, Québec, Canada',
    'Key West (Naval Base), Florida': 'Key West, Florida',
    'Kwajalein Atoll, Marshall Islands': 'Kwajalein, Marshall Islands',
    'Pictou, Nova Scotia': 'Pictou, Nova Scotia, Canada',
    'Sandy Hook, New Jersey': 'Sandy Hook, Fort Hancock, New Jersey',
}

def get_harmonics_name(ref_name):
    """Map old reference name to harmonics name."""
    return REF_STATION_MAPPING.get(ref_name, ref_name)

def parse_tide_output(output):
    """Parse tide command output and extract high/low tide events."""
    events = []
    for line in output.split('\n'):
        match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+([+-]\d+)\s+([\d.]+)\s+(\w+)\s+(High|Low)\s+Tide', line)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            tz_offset = match.group(3)
            height = float(match.group(4))
            unit = match.group(5)
            tide_type = match.group(6)

            # Parse datetime
            dt_str = f"{date_str} {time_str}"
            dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")

            events.append({
                'datetime': dt,
                'height': height,
                'unit': unit,
                'type': tide_type,
                'tz_offset': tz_offset
            })
    return events

def get_reference_tides(ref_name, date_str="2026-01-15"):
    """Get tide predictions for a reference station from xtide."""
    harmonics_name = get_harmonics_name(ref_name)

    # Query 3 days to ensure we have enough events
    start_date = "2026-01-14 00:00"
    end_date = "2026-01-17 00:00"

    try:
        result = subprocess.run(
            ['tide', '-l', harmonics_name, '-b', start_date, '-e', end_date, '-m', 'p'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0 or 'High Tide' not in result.stdout + result.stderr:
            # Try without mapping
            result = subprocess.run(
                ['tide', '-l', ref_name, '-b', start_date, '-e', end_date, '-m', 'p'],
                capture_output=True,
                text=True,
                timeout=30
            )

        output = result.stdout + result.stderr
        events = parse_tide_output(output)

        # Extract unit from output
        unit = 'feet'
        if events:
            unit = events[0].get('unit', 'feet')

        return events, unit

    except Exception as e:
        print(f"Error getting tides for {ref_name}: {e}")
        return [], 'feet'

def apply_corrections(ref_events, hmin, hmpy, hoff, lmin, lmpy, loff, target_date):
    """Apply subordinate station corrections to reference station events."""
    corrected = []

    for event in ref_events:
        new_event = event.copy()

        if event['type'] == 'High':
            # Apply high tide corrections
            new_event['datetime'] = event['datetime'] + timedelta(minutes=hmin)
            new_event['height'] = event['height'] * hmpy + hoff
        else:
            # Apply low tide corrections
            new_event['datetime'] = event['datetime'] + timedelta(minutes=lmin)
            new_event['height'] = event['height'] * lmpy + loff

        corrected.append(new_event)

    return corrected

def select_events_for_date(events, target_date):
    """Select 4 tide events for the target date (2 high, 2 low)."""
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    target_start = target_dt
    target_end = target_dt + timedelta(days=1)

    # Filter events on target date
    day_events = [e for e in events if target_start <= e['datetime'] < target_end]

    # Sort by time
    day_events.sort(key=lambda x: x['datetime'])

    # If we have exactly 4 events, return them
    if len(day_events) == 4:
        return day_events

    # If we have 3 events, find the nearest event from adjacent days
    if len(day_events) == 3:
        # Determine what type we're missing (need 2 high and 2 low)
        high_count = sum(1 for e in day_events if e['type'] == 'High')
        low_count = sum(1 for e in day_events if e['type'] == 'Low')

        if high_count < 2:
            needed_type = 'High'
        else:
            needed_type = 'Low'

        # Find nearest event of needed type from adjacent days
        adjacent_events = [e for e in events
                         if e['type'] == needed_type
                         and (e['datetime'] < target_start or e['datetime'] >= target_end)]

        if adjacent_events:
            # Find closest to target date boundaries
            first_event_time = day_events[0]['datetime']
            last_event_time = day_events[-1]['datetime']

            # Check if we need one before or after
            if day_events[0]['type'] != needed_type:
                # Need one before
                before_events = [e for e in adjacent_events if e['datetime'] < target_start]
                if before_events:
                    nearest = max(before_events, key=lambda x: x['datetime'])
                    day_events.insert(0, nearest)
            else:
                # Need one after
                after_events = [e for e in adjacent_events if e['datetime'] >= target_end]
                if after_events:
                    nearest = min(after_events, key=lambda x: x['datetime'])
                    day_events.append(nearest)

        day_events.sort(key=lambda x: x['datetime'])

    # If we have more than 4, take the 4 closest to midday
    if len(day_events) > 4:
        midday = target_dt + timedelta(hours=12)
        day_events.sort(key=lambda x: abs((x['datetime'] - midday).total_seconds()))
        day_events = day_events[:4]
        day_events.sort(key=lambda x: x['datetime'])

    # If we have fewer than 4, pad with empty events
    while len(day_events) < 4:
        day_events.append({'datetime': None, 'height': None, 'type': None})

    return day_events[:4]

def main():
    input_file = '/home/oliver/subordinate_corrections/subordinate_stations.csv'
    output_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction.csv'
    target_date = "2026-01-15"

    # Read subordinate stations
    stations = []
    with open(input_file, 'r', encoding='latin-1') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            stations.append(row)

    print(f"Loaded {len(stations)} subordinate stations")

    # Get unique reference stations
    ref_stations = set(s['ref_name'] for s in stations)
    print(f"Found {len(ref_stations)} unique reference stations")

    # Cache for reference station tides
    ref_cache = {}

    # Process reference stations
    print("\nFetching reference station tides...")
    for i, ref_name in enumerate(sorted(ref_stations)):
        if ref_name not in ref_cache:
            events, unit = get_reference_tides(ref_name)
            ref_cache[ref_name] = {'events': events, 'unit': unit}

            if events:
                print(f"  [{i+1}/{len(ref_stations)}] {ref_name}: {len(events)} events")
            else:
                print(f"  [{i+1}/{len(ref_stations)}] {ref_name}: NO DATA")

    # Process subordinate stations
    print(f"\nCalculating subordinate station tides for {target_date}...")

    results = []
    errors = 0

    for i, station in enumerate(stations):
        ref_name = station['ref_name']
        ref_data = ref_cache.get(ref_name, {'events': [], 'unit': 'feet'})

        if not ref_data['events']:
            errors += 1
            # Still add to results with empty tide data
            result = station.copy()
            result['water_level_unit'] = ref_data['unit']
            result['time_1'] = ''
            result['water_level_1'] = ''
            result['time_2'] = ''
            result['water_level_2'] = ''
            result['time_3'] = ''
            result['water_level_3'] = ''
            result['time_4'] = ''
            result['water_level_4'] = ''
            results.append(result)
            continue

        # Parse corrections
        try:
            hmin = float(station['hmin'].replace(',', '.')) if station['hmin'] else 0
            hmpy = float(station['hmpy'].replace(',', '.')) if station['hmpy'] else 1
            hoff = float(station['hoff'].replace(',', '.')) if station['hoff'] else 0
            lmin = float(station['lmin'].replace(',', '.')) if station['lmin'] else 0
            lmpy = float(station['lmpy'].replace(',', '.')) if station['lmpy'] else 1
            loff = float(station['loff'].replace(',', '.')) if station['loff'] else 0
        except ValueError as e:
            print(f"  Error parsing corrections for {station['station_name']}: {e}")
            errors += 1
            continue

        # Apply corrections
        corrected_events = apply_corrections(
            ref_data['events'], hmin, hmpy, hoff, lmin, lmpy, loff, target_date
        )

        # Select 4 events for target date
        selected_events = select_events_for_date(corrected_events, target_date)

        # Build result row
        result = station.copy()
        result['water_level_unit'] = ref_data['unit']

        for j, event in enumerate(selected_events, 1):
            if event['datetime']:
                result[f'time_{j}'] = event['datetime'].strftime("%Y-%m-%d %H:%M")
                result[f'water_level_{j}'] = f"{event['height']:.2f}"
            else:
                result[f'time_{j}'] = ''
                result[f'water_level_{j}'] = ''

        results.append(result)

        if (i + 1) % 500 == 0:
            print(f"  Processed {i + 1}/{len(stations)} stations...")

    # Write output
    print(f"\nWriting {len(results)} results to {output_file}...")

    fieldnames = [
        'land', 'region', 'latitude', 'longitude', 'station_name', 'timezone',
        'hmin', 'hmpy', 'hoff', 'lmin', 'lmpy', 'loff',
        'sta_id', 'tzname', 'ref_file_num', 'ref_name', 'water_level_unit',
        'time_1', 'water_level_1', 'time_2', 'water_level_2',
        'time_3', 'water_level_3', 'time_4', 'water_level_4'
    ]

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone! {len(results)} stations processed, {errors} errors")

    # Show sample output
    print("\nSample output (first 3 stations):")
    for r in results[:3]:
        print(f"  {r['station_name']}: {r['time_1']} ({r['water_level_1']}), {r['time_2']} ({r['water_level_2']}), {r['time_3']} ({r['water_level_3']}), {r['time_4']} ({r['water_level_4']})")

if __name__ == '__main__':
    main()
