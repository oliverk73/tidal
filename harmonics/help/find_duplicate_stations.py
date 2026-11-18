#!/usr/bin/env python3
"""
Findet Duplikate zwischen TCD-Dateien: gleicher Stationsname oder gleiche Koordinaten.
Gibt einen Report aus, welche Stationen in mehreren Dateien vorkommen.

Nutzung: python3 find_duplicate_stations.py
"""
import re
import os
import glob
import subprocess
from collections import defaultdict

TCD_DIR = "/usr/share/xtide"


def get_stations_from_tcd(tcd_path):
    """Parse station list from a single TCD file via tide command."""
    env = os.environ.copy()
    env["HFILE_PATH"] = tcd_path
    result = subprocess.run(
        ["tide", "-m", "l", "-tw", "200"],
        capture_output=True, text=True, env=env
    )
    output = result.stdout or result.stderr
    stations = []
    pattern = re.compile(
        r'^(.+?)\s{2,}(Ref|Sub)\s+([\d.]+)°\s*([NS]),\s*([\d.]+)°\s*([EW])$'
    )
    for line in output.splitlines():
        if line.startswith("Indexing ") or line.startswith("Location list") or not line.strip():
            continue
        m = pattern.match(line)
        if not m:
            continue
        name, stype, lat, ns, lon, ew = m.groups()
        lat = float(lat) * (1 if ns == 'N' else -1)
        lon = float(lon) * (1 if ew == 'E' else -1)
        stations.append((name.strip(), stype, lat, lon))
    return stations


tcd_files = sorted(glob.glob(os.path.join(TCD_DIR, "*.tcd")))
print(f"Gefunden: {len(tcd_files)} TCD-Dateien in {TCD_DIR}\n")

# Collect all stations with their source files
by_name = defaultdict(list)
by_coord = defaultdict(list)

for tcd_file in tcd_files:
    basename = os.path.basename(tcd_file)
    stations = get_stations_from_tcd(tcd_file)
    print(f"  {basename}: {len(stations)} Stationen")
    for name, stype, lat, lon in stations:
        by_name[name].append((basename, stype, lat, lon))
        coord_key = (round(lat, 4), round(lon, 4))
        by_coord[coord_key].append((basename, name, stype))

# Report: stations with same name in multiple files
name_dupes = {k: v for k, v in by_name.items() if len(v) > 1}
print(f"\n=== Duplikate nach Name: {len(name_dupes)} Stationen in mehreren Dateien ===")
for name in sorted(name_dupes.keys()):
    entries = name_dupes[name]
    files = [e[0] for e in entries]
    print(f"  {name}")
    for basename, stype, lat, lon in entries:
        print(f"    {basename} ({stype}, {lat:.4f}, {lon:.4f})")

# Report: different stations at same coordinates
coord_dupes = {k: v for k, v in by_coord.items() if len(v) > 1}
# Filter out same-name duplicates (already reported above)
coord_only = {}
for coord, entries in coord_dupes.items():
    names = set(e[1] for e in entries)
    if len(names) > 1:  # Different names at same location
        coord_only[coord] = entries

print(f"\n=== Verschiedene Namen an gleichen Koordinaten: {len(coord_only)} ===")
for (lat, lon), entries in sorted(coord_only.items()):
    print(f"  ({lat}, {lon}):")
    for basename, name, stype in entries:
        print(f"    {basename}: {name} ({stype})")

print(f"\nGesamt: {len(name_dupes)} Namens-Duplikate, {len(coord_only)} Koordinaten-Duplikate")
