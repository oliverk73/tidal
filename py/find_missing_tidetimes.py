#!/usr/bin/env python3
"""
Find tidetimes.co.uk stations that we don't already have in our harmonics.
Extracts tt.locations JS array from homepage (726 stations with coords),
then checks against existing tide stations.
"""
import re
import json
import subprocess
import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
}


def get_tidetimes_stations():
    """Extract all stations from tt.locations JavaScript array."""
    r = requests.get('https://www.tidetimes.co.uk', headers=HEADERS, timeout=30)
    r.raise_for_status()

    m = re.search(r'tt\.locations\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
    if not m:
        raise RuntimeError("tt.locations not found on page")

    data = json.loads(m.group(1))
    stations = []
    for s in data:
        stations.append({
            'slug': s['slug'],
            'name': s['name'],
            'lat': float(s['lat']),
            'lon': float(s['lng']),
        })
    return stations


def get_existing_stations():
    """Get all existing station names and coordinates from tide -m l."""
    result = subprocess.run(['tide', '-m', 'l'], capture_output=True, text=True)
    output = result.stdout + result.stderr

    stations = []
    for line in output.splitlines():
        m = re.match(r'^(.+?)\s{2,}(Ref|Sub)\s+(\d+\.\d+).*([NS]),\s*(\d+\.\d+).*([EW])', line)
        if m:
            name = m.group(1).strip()
            lat = float(m.group(3)) * (1 if m.group(4) == 'N' else -1)
            lon = float(m.group(5)) * (1 if m.group(6) == 'E' else -1)
            stations.append((name, lat, lon))

    return stations


def normalize(name):
    """Normalize station name for comparison."""
    name = name.lower().strip()
    name = re.sub(r"[''`\.]", '', name)
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def names_match(tt_name, existing_name):
    """Check if a tidetimes name matches an existing station name."""
    tt_n = normalize(tt_name)
    ex_n = normalize(existing_name)

    # Exact match
    if tt_n == ex_n:
        return True

    # Base name match (before first comma)
    ex_base = normalize(existing_name.split(',')[0])
    if tt_n == ex_base:
        return True

    # Without parenthetical
    tt_no_paren = normalize(re.sub(r'\s*\([^)]*\)', '', tt_name))
    ex_no_paren = normalize(re.sub(r'\s*\([^)]*\)', '', existing_name.split(',')[0]))
    if tt_no_paren == ex_no_paren and tt_no_paren:
        return True

    # Special cases: "Penzance (Newlyn)" should match "Newlyn"
    # Check if parenthetical content matches
    paren_match = re.search(r'\(([^)]+)\)', tt_name)
    if paren_match:
        paren_content = normalize(paren_match.group(1))
        if paren_content == ex_base or paren_content == ex_no_paren:
            return True

    # And vice versa
    paren_match = re.search(r'\(([^)]+)\)', existing_name.split(',')[0])
    if paren_match:
        paren_content = normalize(paren_match.group(1))
        if paren_content == tt_n or paren_content == tt_no_paren:
            return True

    return False


def coords_match(lat1, lon1, lat2, lon2, threshold_km=5):
    """Check if two coordinate pairs are within threshold_km."""
    import math
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    km = 6371 * c
    return km < threshold_km


def main():
    print("Lade tidetimes.co.uk Stationen...")
    tt_stations = get_tidetimes_stations()
    print(f"  {len(tt_stations)} Stationen gefunden")

    print("Lade bestehende Stationen...")
    existing = get_existing_stations()
    print(f"  {len(existing)} bestehende Stationen")

    # Filter to UK/Ireland/Channel Islands area only
    existing_uk = [(n, la, lo) for n, la, lo in existing
                   if (49.0 < la < 62.0 and -11.0 < lo < 3.0) or
                   'United Kingdom' in n or 'Ireland' in n or
                   'Channel Islands' in n or 'Isle of Man' in n]
    print(f"  {len(existing_uk)} davon in UK/Irland-Region")

    missing = []
    found = []
    for st in tt_stations:
        matched = False
        matched_by = None

        # 1. Name matching
        for ex_name, ex_lat, ex_lon in existing_uk:
            if names_match(st['name'], ex_name):
                matched = True
                matched_by = ex_name
                break

        # 2. Coordinate matching (within 3km) as fallback
        if not matched:
            for ex_name, ex_lat, ex_lon in existing_uk:
                if coords_match(st['lat'], st['lon'], ex_lat, ex_lon, threshold_km=3):
                    matched = True
                    matched_by = f"{ex_name} (coord match)"
                    break

        if matched:
            found.append((st, matched_by))
        else:
            missing.append(st)

    print(f"\n{'='*70}")
    print(f"Bereits vorhanden: {len(found)}")
    print(f"FEHLEND: {len(missing)}")
    print(f"{'='*70}")

    print(f"\nGefundene Matches:")
    for st, by in sorted(found, key=lambda x: x[0]['name']):
        print(f"  {st['name']:40s} -> {by}")

    print(f"\nFehlende Stationen:")
    for st in missing:
        print(f"  {st['name']:45s}  {st['lat']:8.4f} {st['lon']:9.4f}  {st['slug']}")

    # Save missing stations to JSON for the download script
    out_path = '/home/oliver/water_levels/UK_tidetimes/missing_stations.json'
    with open(out_path, 'w') as f:
        json.dump(missing, f, indent=2)
    print(f"\n{len(missing)} fehlende Stationen gespeichert: {out_path}")


if __name__ == '__main__':
    main()
