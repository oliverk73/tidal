#!/usr/bin/env python3
"""
Compare coordinates between leaflet_markers.js and harmonics-1997-05-25_mod.txt
for stations sourced from harmonics-1997-05-25_mod.tcd.
"""

import re
from collections import defaultdict

MARKERS_FILE = '/home/oliver/static/js/leaflet_markers.js'
TXT_FILE = '/home/oliver/harmonics/classic/harmonics-1997-05-25_mod.txt'
TCD_NAME = 'harmonics-1997-05-25_mod.tcd'
THRESHOLD = 0.001

def parse_markers(path):
    """Parse leaflet_markers.js. Return dict: station_name -> list of (lat, lon) tuples."""
    coords = defaultdict(list)  # name -> [(lat, lon), ...]
    sources = {}  # name -> source tcd

    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Find all stationCoords entries
    coord_pattern = re.compile(r"stationCoords\['(.+?)'\]\s*=\s*\[([^\]]+)\];")
    source_pattern = re.compile(r"stationSources\['(.+?)'\]\s*=\s*'(.+?)';")

    for m in source_pattern.finditer(text):
        sources[m.group(1)] = m.group(2)

    for m in coord_pattern.finditer(text):
        name = m.group(1)
        vals = m.group(2).split(',')
        lat = float(vals[0].strip())
        lon = float(vals[1].strip())
        if sources.get(name) == TCD_NAME:
            coords[name].append((lat, lon))

    return coords


def parse_txt(path):
    """Parse harmonics TXT file. Return dict: station_name -> (lat, lon)."""
    stations = {}

    with open(path, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    lat = None
    lon = None
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n').rstrip('\r')
        if line.startswith('# !latitude:'):
            lat = float(line.split(':',1)[1].strip())
            # Next non-comment line is the station name
            i += 1
            while i < len(lines) and lines[i].strip().startswith('#'):
                i += 1
            if i < len(lines):
                name = lines[i].rstrip('\n').rstrip('\r').strip()
                if lat is not None and lon is not None:
                    stations[name] = (lat, lon)
            lat = None
            lon = None
        elif line.startswith('# !longitude:'):
            lon = float(line.split(':',1)[1].strip())
            i += 1
        else:
            i += 1

    return stations


def main():
    marker_coords = parse_markers(MARKERS_FILE)
    txt_coords = parse_txt(TXT_FILE)

    marker_names = set(marker_coords.keys())
    txt_names = set(txt_coords.keys())

    both = marker_names & txt_names
    only_markers = marker_names - txt_names
    only_txt = txt_names - marker_names

    # Find mismatches
    mismatches = []
    for name in sorted(both):
        txt_lat, txt_lon = txt_coords[name]
        variants = marker_coords[name]
        # Check if ANY variant differs
        has_diff = False
        for (mlat, mlon) in variants:
            if abs(mlat - txt_lat) > THRESHOLD or abs(mlon - txt_lon) > THRESHOLD:
                has_diff = True
                break
        if has_diff:
            mismatches.append(name)

    print(f"=== Coordinate Comparison: markers vs TXT ===")
    print(f"Source TCD: {TCD_NAME}")
    print(f"Stations in markers: {len(marker_names)}")
    print(f"Stations in TXT:     {len(txt_names)}")
    print(f"Stations in both:    {len(both)}")
    print(f"Mismatches (>{THRESHOLD} deg): {len(mismatches)}")
    print()

    if mismatches:
        print(f"{'Station':<55} {'TXT (lat, lon)':<25} {'Marker variants'}")
        print("-" * 140)
        for name in mismatches:
            txt_lat, txt_lon = txt_coords[name]
            variants = marker_coords[name]
            txt_str = f"({txt_lat:.4f}, {txt_lon:.4f})"
            var_strs = []
            for (mlat, mlon) in variants:
                match = abs(mlat - txt_lat) <= THRESHOLD and abs(mlon - txt_lon) <= THRESHOLD
                tag = " [=TXT]" if match else " [DIFF]"
                var_strs.append(f"({mlat:.4f}, {mlon:.4f}){tag}")
            print(f"{name:<55} {txt_str:<25} {' | '.join(var_strs)}")
        print()

    if only_markers:
        print(f"\n=== Stations ONLY in markers (not in TXT): {len(only_markers)} ===")
        for name in sorted(only_markers):
            variants = marker_coords[name]
            var_str = ', '.join(f"({lat:.4f}, {lon:.4f})" for lat, lon in variants)
            print(f"  {name}: {var_str}")

    if only_txt:
        print(f"\n=== Stations ONLY in TXT (not in markers): {len(only_txt)} ===")
        for name in sorted(only_txt):
            lat, lon = txt_coords[name]
            print(f"  {name}: ({lat:.4f}, {lon:.4f})")

    if not mismatches and not only_markers and not only_txt:
        print("All coordinates match perfectly!")


if __name__ == '__main__':
    main()
