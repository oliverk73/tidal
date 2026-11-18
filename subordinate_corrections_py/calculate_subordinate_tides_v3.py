#!/usr/bin/env python3
"""
Calculate tide predictions for subordinate stations using xtide.
"""

import csv
import subprocess
import re
from datetime import datetime, timedelta

def parse_tide_output(output):
    """Parse tide command output and extract high/low tide events."""
    events = []
    for line in output.split('\n'):
        # Match formats:
        # 2026-01-15  5:43 AM NZDT   2.65 meters  High Tide
        # 2026-01-15  3:52 AM +03   1.92 meters  High Tide
        match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(\S+)\s+([\d.]+)\s+(\w+)\s+(High|Low)\s+Tide', line)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            tz = match.group(3)
            height = float(match.group(4))
            unit = match.group(5)
            tide_type = match.group(6)

            dt_str = f"{date_str} {time_str}"
            dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")

            events.append({
                'datetime': dt,
                'height': height,
                'unit': unit,
                'type': tide_type,
                'tz': tz
            })
    return events

def get_reference_tides(ref_name):
    """Get tide predictions for a reference station from xtide."""
    start_date = "2026-01-14 00:00"
    end_date = "2026-01-17 00:00"

    try:
        result = subprocess.run(
            ['tide', '-l', ref_name, '-b', start_date, '-e', end_date, '-m', 'p'],
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout + result.stderr
        events = parse_tide_output(output)

        unit = 'feet'
        if events:
            unit = events[0].get('unit', 'feet')

        return events, unit

    except Exception as e:
        return [], 'feet'

def apply_corrections(ref_events, hmin, hmpy, hoff, lmin, lmpy, loff):
    """Apply subordinate station corrections."""
    corrected = []
    for event in ref_events:
        new_event = event.copy()
        if event['type'] == 'High':
            new_event['datetime'] = event['datetime'] + timedelta(minutes=hmin)
            new_event['height'] = event['height'] * hmpy + hoff
        else:
            new_event['datetime'] = event['datetime'] + timedelta(minutes=lmin)
            new_event['height'] = event['height'] * lmpy + loff
        corrected.append(new_event)
    return corrected

def select_events_for_date(events, target_date):
    """Select 4 tide events for the target date."""
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    target_start = target_dt
    target_end = target_dt + timedelta(days=1)

    day_events = [e for e in events if target_start <= e['datetime'] < target_end]
    day_events.sort(key=lambda x: x['datetime'])

    if len(day_events) >= 4:
        return day_events[:4]

    if len(day_events) == 3:
        high_count = sum(1 for e in day_events if e['type'] == 'High')
        needed_type = 'High' if high_count < 2 else 'Low'

        adjacent = [e for e in events if e['type'] == needed_type and
                   (e['datetime'] < target_start or e['datetime'] >= target_end)]

        if adjacent:
            if day_events[0]['type'] != needed_type:
                before = [e for e in adjacent if e['datetime'] < target_start]
                if before:
                    day_events.insert(0, max(before, key=lambda x: x['datetime']))
            else:
                after = [e for e in adjacent if e['datetime'] >= target_end]
                if after:
                    day_events.append(min(after, key=lambda x: x['datetime']))

        day_events.sort(key=lambda x: x['datetime'])

    while len(day_events) < 4:
        day_events.append({'datetime': None, 'height': None, 'type': None, 'unit': 'feet'})

    return day_events[:4]

def main():
    input_file = '/home/oliver/subordinate_corrections/subordinate_stations_mapped.csv'
    output_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction.csv'
    target_date = "2026-01-15"

    stations = []
    with open(input_file, 'r', encoding='latin-1') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            stations.append(row)

    print(f"Loaded {len(stations)} subordinate stations")

    ref_stations = set(s['ref_name'] for s in stations if s.get('ref_name'))
    print(f"Found {len(ref_stations)} unique reference stations")

    ref_cache = {}
    print("\nFetching reference station tides...")

    for i, ref_name in enumerate(sorted(ref_stations)):
        if not ref_name:
            continue
        events, unit = get_reference_tides(ref_name)
        ref_cache[ref_name] = {'events': events, 'unit': unit}

        status = f"{len(events)} events" if events else "NO DATA"
        print(f"  [{i+1}/{len(ref_stations)}] {ref_name}: {status}")

    print(f"\nCalculating subordinate station tides for {target_date}...")

    results = []
    success = 0
    errors = 0

    for i, station in enumerate(stations):
        ref_name = station.get('ref_name', '')
        ref_data = ref_cache.get(ref_name, {'events': [], 'unit': 'feet'})

        result = station.copy()
        result['water_level_unit'] = ref_data['unit']

        if not ref_data['events']:
            errors += 1
            for j in range(1, 5):
                result[f'time_{j}'] = ''
                result[f'water_level_{j}'] = ''
            results.append(result)
            continue

        try:
            hmin = float(station.get('hmin', '0').replace(',', '.'))
            hmpy = float(station.get('hmpy', '1').replace(',', '.'))
            hoff = float(station.get('hoff', '0').replace(',', '.'))
            lmin = float(station.get('lmin', '0').replace(',', '.'))
            lmpy = float(station.get('lmpy', '1').replace(',', '.'))
            loff = float(station.get('loff', '0').replace(',', '.'))
        except ValueError:
            errors += 1
            for j in range(1, 5):
                result[f'time_{j}'] = ''
                result[f'water_level_{j}'] = ''
            results.append(result)
            continue

        corrected = apply_corrections(ref_data['events'], hmin, hmpy, hoff, lmin, lmpy, loff)
        selected = select_events_for_date(corrected, target_date)

        for j, event in enumerate(selected, 1):
            if event['datetime']:
                result[f'time_{j}'] = event['datetime'].strftime("%Y-%m-%d %H:%M")
                result[f'water_level_{j}'] = f"{event['height']:.2f}"
            else:
                result[f'time_{j}'] = ''
                result[f'water_level_{j}'] = ''

        results.append(result)
        success += 1

        if (i + 1) % 500 == 0:
            print(f"  Processed {i + 1}/{len(stations)} stations...")

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

    print(f"\nDone! {success} success, {errors} errors")
    print(f"Output: {output_file}")

if __name__ == '__main__':
    main()
