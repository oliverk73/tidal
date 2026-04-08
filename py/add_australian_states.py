#!/usr/bin/env python3
"""
Add Australian state/territory names to station names in harmonics files.
E.g., "Southport, Australia" → "Southport, Queensland, Australia"

Skips stations that already have a state name.
"""
import re
import sys

# Known Australian states/territories that might already appear in names
KNOWN_STATES = [
    'Tasmania', 'Victoria', 'South Australia', 'Queensland',
    'New South Wales', 'Western Australia', 'Northern Territory',
    'Cocos Islands', 'Christmas Island', 'Norfolk Island',
    'Lord Howe Island', 'Macquarie Island', 'Tasman Sea',
]

# Explicit overrides for tricky/well-known stations
# Format: "station name as in file (before , Australia)" → "State"
EXPLICIT_STATE = {
    # Christmas Island / Cocos
    'Christmas Island': 'Christmas Island',
    'Bantam, Cocos Islands': 'Cocos Islands',
    'Port Refuge, Cocos Islands': 'Cocos Islands',
    # Norfolk / Lord Howe / Macquarie
    'Norfolk Island': 'Norfolk Island',
    'Lord Howe Island': 'New South Wales',
    'Lord Howe Island, Tasman Sea': 'New South Wales',
    'Macquarie Island': 'Tasmania',
    # Davis Station (Antarctica, Australian territory)
    'Davis': 'Australian Antarctic Territory',
    # Well-known cities to avoid ambiguity
    'Fort Denison': 'New South Wales',
    'Fort Dension': 'New South Wales',  # typo in TICON4
    'Brisbane': 'Queensland',
    'Brisbane Port Off.': 'Queensland',
    'Gold Coast Seaway': 'Queensland',
    'Nerang River (Bundall)': 'Queensland',
    'Runaway Bay': 'Queensland',
    'Tangalooma Point': 'Queensland',
    'Southport': 'Queensland',
    'Mooloolaba': 'Queensland',
    'Noosa Head': 'Queensland',
    'Caloundra Head': 'Queensland',
    'Bribie Island, Bongaree': 'Queensland',
    'Boonlye Point': 'Queensland',
    'Waddy Point': 'Queensland',
    'Cairns': 'Queensland',
    'Townsville': 'Queensland',
    'Mackay': 'Queensland',
    'Bowen': 'Queensland',
    'Cardwell': 'Queensland',
    'Cooktown': 'Queensland',
    'Karumba': 'Queensland',
    'Mourilyan': 'Queensland',
    'Urangan': 'Queensland',
    'Weipa': 'Queensland',
    'Rosslyn Bay': 'Queensland',
    'Bundaberg': 'Queensland',
    'Gladstone': 'Queensland',
    'Lucinda': 'Queensland',
    'Lucinda Offshore': 'Queensland',
    'Cape Ferguson': 'Queensland',
    'Booby Island': 'Queensland',
    'Melbourne (Williamstown)': 'Victoria',
    'Geelong (Corio Bay)': 'Victoria',
    'Hovell Pile (Port Phillip Bay)': 'Victoria',
    'Point Lonsdale (Port Phillip Heads)': 'Victoria',
    'Point Richards (Portarlington)': 'Victoria',
    'Queenscliff': 'Victoria',
    'Queenscliff, ': 'Victoria',  # with trailing space+comma
    'West Channel': 'Victoria',
    'Stony Point (Westernport)': 'Victoria',
    'Lorne': 'Victoria',
    'Lorne (Louttit Bay)': 'Victoria',
    'Portland': 'Victoria',
    'Port Welshpool': 'Victoria',
    'Lakes Entrance': 'Victoria',
    'Mornington Island H074011A': 'Queensland',
    'Fishermans Landing H052003B': 'Queensland',
    'Half Tide Tug Harbour H060010A': 'Queensland',
    'South Trees H052026A': 'Queensland',
    'Mackay Outer Harbour': 'Queensland',
    'Mourilyan Harbour': 'Queensland',
    'Perth': 'Western Australia',
    'Fremantle': 'Western Australia',
    'Geraldton': 'Western Australia',
    'Albany': 'Western Australia',
    'Bunbury': 'Western Australia',
    'Busselton': 'Western Australia',
    'Mandurah': 'Western Australia',
    'Broome': 'Western Australia',
    'Derby': 'Western Australia',
    'Exmouth': 'Western Australia',
    'Onslow': 'Western Australia',
    'Port Hedland': 'Western Australia',
    'Carnarvon': 'Western Australia',
    'Esperance': 'Western Australia',
    'Wyndham': 'Western Australia',
    'Hillarys': 'Western Australia',
    'Dampier': 'Western Australia',
    'Darwin': 'Northern Territory',
    'Groote Eylandt': 'Northern Territory',
    'Gove Harbour': 'Northern Territory',
    'Thevenard': 'South Australia',
    'Port Kembla': 'New South Wales',
    'Sydney': 'New South Wales',
    'Newcastle': 'New South Wales',
    'Eden': 'New South Wales',
    'Coffs Harbour': 'New South Wales',
    'Port Macquarie': 'New South Wales',
    'Botany Bay': 'New South Wales',
    'Yamba': 'New South Wales',
    'Camp Cove': 'New South Wales',
    'Captains Point (Jervis Bay)': 'New South Wales',
    'Crookhaven': 'New South Wales',
    'Forster': 'New South Wales',
    'Iluka': 'New South Wales',
    'Little Patonga': 'New South Wales',
    'Ulladulla Harbour': 'New South Wales',
    'Batemans Bay': 'New South Wales',
    'Bermagui': 'New South Wales',
    'Brunswick': 'New South Wales',
    'Kingscliff': 'New South Wales',
    # NSW stations near QLD border (border at ~28.16°S at coast)
    'Ballina': 'New South Wales',
    'Brunswick Heads': 'New South Wales',
    'Tweed River': 'New South Wales',
    'Point Danger': 'New South Wales',
    # SA station near VIC border (border at 141°E)
    'Port Macdonnell': 'South Australia',
    # Nathan/Peart Reef — no coords but Queensland (Brisbane timezone)
    'Nathan Reef': 'Queensland',
    'Peart Reef': 'Queensland',
    'Burnie': 'Tasmania',
    'Hobart': 'Tasmania',
    'Devonport': 'Tasmania',
    'Spring Bay': 'Tasmania',
    'Low': 'Tasmania',
    'Port Lincoln': 'South Australia',
    'Whyalla': 'South Australia',
    'Port Pirie': 'South Australia',
    'Wallaroo': 'South Australia',
    'Wool Bay': 'South Australia',
    'Port': 'South Australia',  # Port Adelaide shortened?
    'Clump': 'South Australia',
    'Ince': 'South Australia',
    'Harvey Dvhar': 'Western Australia',
    'Cape Bouvard Dvbvd': 'Western Australia',
    'Peel Inlet Plpee': 'Western Australia',
    'Bremer Bay Bbbre': 'Western Australia',
    'Jurien Bay': 'Western Australia',
    'Shute Harbour': 'Queensland',
    'Port Douglas': 'Queensland',
    'Hay Point': 'Queensland',
    'Warrnambool': 'Victoria',
    'Apollo Bay': 'Victoria',
    'Port Campbell': 'Victoria',
    'Walkerville (Waratah Bay)': 'Victoria',
}


def determine_state(name_before_australia, lat, lon):
    """Determine Australian state from station name and coordinates."""

    # Check explicit overrides first
    key = name_before_australia.strip().rstrip(',').strip()
    if key in EXPLICIT_STATE:
        return EXPLICIT_STATE[key]

    # Check if already has a state
    for state in KNOWN_STATES:
        if state in name_before_australia:
            return None  # already has state

    # Coordinate-based determination for remaining stations
    # External territories
    if lat > -15 and lon < 100:
        return 'Cocos Islands'
    if lat > -12 and 105 < lon < 106:
        return 'Christmas Island'
    if -30 < lat < -28 and 167 < lon < 169:
        return 'Norfolk Island'
    if -33 < lat < -31 and 158 < lon < 160:
        return 'New South Wales'  # Lord Howe Island
    if lat < -50:
        return 'Tasmania'  # Macquarie Island

    # Tasmania
    if lat < -39.5 and 143 < lon < 149:
        return 'Tasmania'

    # Victoria
    if lat < -37.0 and 140.5 < lon < 150.5:
        return 'Victoria'

    # South Australia (complex - Gulf St Vincent, Spencer Gulf, etc.)
    if 132 < lon < 141 and lat < -30:
        return 'South Australia'
    if 129 < lon < 132 and lat < -26:
        return 'South Australia'

    # Western Australia
    if lon < 129:
        return 'Western Australia'

    # Northern Territory
    if 129 <= lon <= 138 and lat > -20:
        return 'Northern Territory'
    if 129 <= lon <= 137 and lat > -26:
        return 'Northern Territory'

    # Queensland (east coast + Gulf)
    if lat > -29 and lon > 138:
        return 'Queensland'
    # QLD Gulf of Carpentaria stations
    if lat > -20 and 137 < lon < 142:
        return 'Queensland'

    # New South Wales (east coast)
    if -37.5 < lat < -28 and lon > 149:
        return 'New South Wales'

    # Fallback
    print(f"  WARNING: Cannot determine state for '{name_before_australia}' at ({lat}, {lon})")
    return None


def process_file(filepath, dry_run=False):
    """Process one harmonics file, adding state names to Australian stations."""
    with open(filepath, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    changes = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Match station name lines ending with ", Australia\n"
        m = re.match(r'^(.+),\s*Australia\s*$', line)
        if m:
            name_part = m.group(1).strip()

            # Check if already has a state
            already_has_state = False
            for state in KNOWN_STATES:
                if state in name_part:
                    already_has_state = True
                    break

            if not already_has_state:
                # Find coordinates by looking backwards for !longitude and !latitude
                lat = lon = None
                for j in range(i-1, max(i-20, 0), -1):
                    lm = re.match(r'#\s*!latitude:\s*([-\d.]+)', lines[j])
                    if lm:
                        lat = float(lm.group(1))
                    lm = re.match(r'#\s*!longitude:\s*([-\d.]+)', lines[j])
                    if lm:
                        lon = float(lm.group(1))

                if lat is not None and lon is not None:
                    state = determine_state(name_part, lat, lon)
                    if state:
                        old_line = line.rstrip('\n')
                        new_line = f"{name_part}, {state}, Australia"
                        lines[i] = new_line + '\n'
                        changes.append((i+1, old_line, new_line))
                else:
                    print(f"  WARNING: No coordinates found for '{name_part}' at line {i+1}")

        i += 1

    if changes:
        if not dry_run:
            with open(filepath, 'w', encoding='iso-8859-1') as f:
                f.writelines(lines)

        for lineno, old, new in changes:
            print(f"  L{lineno}: {old}")
            print(f"      → {new}")

    return changes


def main():
    dry_run = '--dry-run' in sys.argv

    files = [
        '/home/oliver/harmonics/utide/harmonics_utide_australia.txt',
        '/home/oliver/harmonics/utide/harmonics_utide_australia_qld.txt',
        '/home/oliver/harmonics/utide/harmonics_utide_australia_uhslc.txt',
        '/home/oliver/harmonics/classic/harmonics-2004-06-14_mod.txt',
        '/home/oliver/harmonics/classic/harmonics-1997-05-25_mod.txt',
        '/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt',
    ]

    if dry_run:
        print("=== DRY RUN — keine Änderungen ===\n")

    total_changes = 0
    for filepath in files:
        print(f"\n{'='*70}")
        print(f"Datei: {filepath.split('/')[-1]}")
        print(f"{'='*70}")
        changes = process_file(filepath, dry_run=dry_run)
        n = len(changes)
        total_changes += n
        print(f"\n  → {n} Stationen geändert")

    print(f"\n\n{'='*70}")
    print(f"GESAMT: {total_changes} Stationen geändert")
    if dry_run:
        print("(DRY RUN — keine Dateien geschrieben)")


if __name__ == '__main__':
    main()
