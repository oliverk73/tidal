#!/usr/bin/env python3
"""
Extract US subordinate tide/current stations (including territories)
from harmonic_subordinate_corrections.idx and save to a separate file.

US territories included:
- US mainland (region = US)
- Puerto Rico (region = PR)
- Virgin Islands (region = Virgn)
- Northern Mariana Islands (region = Mari)
- Guam (referenced in timezone Pacific/Guam or in station name)
- American Samoa (region = Sam with American Samoa in name)
- Wake Island, Midway, Johnston Atoll, etc.
"""

import re

def is_us_station(line1, line2):
    """Check if a station pair belongs to the US or its territories."""

    # Parse region from line1
    # Format: tZone:Region:Subregion: ...
    match = re.match(r'^[tc]([^:]+):([^:]*):([^:]*):(.*)$', line1)
    if not match:
        return False

    zone = match.group(1)
    region = match.group(2)
    subregion = match.group(3)
    rest = match.group(4).strip()

    # US mainland
    if region == 'US':
        return True

    # Puerto Rico
    if region == 'PR':
        return True

    # Virgin Islands (US)
    if region == 'Virgn':
        return True

    # Northern Mariana Islands (US Commonwealth)
    if region == 'Mari':
        return True

    # Check for Guam (US territory)
    if 'Guam' in rest:
        return True

    # Check for American Samoa
    if 'American Samoa' in rest:
        return True

    # Check for other US Pacific territories
    us_pacific_keywords = [
        'Wake Island',
        'Midway',
        'Johnston Atoll',
        'Palmyra',
        'Howland',
        'Baker Island',
        'Jarvis Island'
    ]
    for keyword in us_pacific_keywords:
        if keyword in rest:
            return True

    # Check timezone for US-specific timezones
    if line2:
        us_timezones = [
            'America/New_York',
            'America/Chicago',
            'America/Denver',
            'America/Los_Angeles',
            'America/Anchorage',
            'America/Juneau',
            'America/Sitka',
            'America/Yakutat',
            'America/Nome',
            'America/Adak',
            'America/Metlakatla',
            'America/Atka',
            'America/Phoenix',
            'America/Boise',
            'America/Indiana',
            'America/Puerto_Rico',
            'America/St_Thomas',
            'Pacific/Honolulu',
            'Pacific/Guam',
            'Pacific/Pago_Pago',
            'Pacific/Wake',
            'Pacific/Midway',
            'Pacific/Johnston'
        ]
        for tz in us_timezones:
            if tz in line2 and region == 'US':
                return True

    return False


def extract_us_stations(input_file, output_file):
    """Extract all US stations from the idx file."""

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    us_stations = []
    other_stations = []

    i = 0
    while i < len(lines):
        line1 = lines[i].strip()

        # Check if this is a station line (starts with 't' for tide or 'c' for current)
        if line1 and (line1.startswith('t') or line1.startswith('c')):
            # Get the correction line
            line2 = ''
            if i + 1 < len(lines) and lines[i + 1].strip().startswith('&'):
                line2 = lines[i + 1].strip()

            if is_us_station(line1, line2):
                us_stations.append(lines[i])
                if line2:
                    us_stations.append(lines[i + 1])
                i += 2 if line2 else 1
            else:
                other_stations.append(lines[i])
                if line2:
                    other_stations.append(lines[i + 1])
                i += 2 if line2 else 1
        else:
            i += 1

    # Write US stations
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(us_stations)

    us_count = len([l for l in us_stations if l.strip() and (l.strip().startswith('t') or l.strip().startswith('c'))])
    other_count = len([l for l in other_stations if l.strip() and (l.strip().startswith('t') or l.strip().startswith('c'))])

    print(f"US stations (including territories): {us_count}")
    print(f"Non-US stations: {other_count}")
    print(f"Total: {us_count + other_count}")
    print(f"US stations saved to: {output_file}")

    return us_count


if __name__ == '__main__':
    input_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections.idx'
    output_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_us.idx'

    extract_us_stations(input_file, output_file)
