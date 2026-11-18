#!/usr/bin/env python3
"""
Final extraction of Oliver's corrections from leaflet_markers.js.

For renamed stations: the new name exists ONLY in current markers, not in HEAD.
The old name still exists in both (because build_tide_station_markers.py re-ran).
Match new names to TXT stations by coordinate proximity.

For coordinate corrections: compare HEAD vs current markers (last-wins).
Also show ALL correction entries (not just last) so Oliver can pick the right one.
"""

import re
import subprocess
from collections import OrderedDict


MARKERS_FILE = '/home/oliver/static/js/leaflet_markers.js'
TXT_FILE = '/home/oliver/harmonics/classic/harmonics-1997-05-25_mod.txt'
TCD_NAME = 'harmonics-1997-05-25_mod.tcd'


def parse_all_entries(text):
    """Parse ALL stationCoords entries (not just last), filtered by source TCD.
    Returns: {name: [(lat, lon), ...]}"""
    sources = {}
    entries = OrderedDict()

    for m in re.finditer(r"stationSources\['(.+?)'\]\s*=\s*'(.+?)';", text):
        sources[m.group(1)] = m.group(2)

    for m in re.finditer(r"stationCoords\['(.+?)'\]\s*=\s*\[([^,]+),\s*([^\]]+)\];", text):
        name = m.group(1)
        lat = float(m.group(2).strip())
        lon = float(m.group(3).strip())
        if sources.get(name) == TCD_NAME:
            entries.setdefault(name, []).append((lat, lon))

    return entries


def parse_txt(path):
    """Parse harmonics TXT. Return dict: name -> (lat, lon)."""
    stations = OrderedDict()
    with open(path, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()
    lat = lon = None
    for line in lines:
        line = line.rstrip()
        if line.startswith('# !latitude:'):
            lat = float(line.split(':', 1)[1].strip())
        elif line.startswith('# !longitude:'):
            lon = float(line.split(':', 1)[1].strip())
        elif not line.startswith('#') and line.strip() and lat is not None and lon is not None:
            stations[line.strip()] = (lat, lon)
            lat = lon = None
    return stations


def main():
    # Parse HEAD and current markers
    r = subprocess.run(['git', 'show', 'HEAD:static/js/leaflet_markers.js'],
                       capture_output=True, text=True)
    head_entries = parse_all_entries(r.stdout)
    with open(MARKERS_FILE, 'r', encoding='utf-8') as f:
        curr_entries = parse_all_entries(f.read())

    # Parse TXT
    txt = parse_txt(TXT_FILE)

    # === 1) New names (in current but not in HEAD) — these are renames ===
    new_names = set(curr_entries.keys()) - set(head_entries.keys())

    # Match new names to TXT stations by coordinate proximity
    renames = []
    for new_name in sorted(new_names):
        new_coords = curr_entries[new_name][-1]  # last entry
        best_txt = None
        best_dist = 999
        for txt_name, txt_c in txt.items():
            dist = ((txt_c[0] - new_coords[0])**2 + (txt_c[1] - new_coords[1])**2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_txt = txt_name
        if best_txt and best_dist < 5.0:
            renames.append((best_txt, new_name, txt[best_txt], new_coords, best_dist))

    # === 2) Coordinate changes (same name in HEAD and current, different coords) ===
    coord_fixes = []
    for name in sorted(set(head_entries.keys()) & set(curr_entries.keys())):
        head_c = head_entries[name]  # list of all entries in HEAD
        curr_c = curr_entries[name]  # list of all entries in current

        # HEAD should have 1 entry; current may have more (corrections appended)
        head_last = head_c[-1]
        curr_last = curr_c[-1]

        if abs(head_last[0] - curr_last[0]) > 0.0001 or abs(head_last[1] - curr_last[1]) > 0.0001:
            # Find which entries are new (in current but not in HEAD)
            new_entries = [c for c in curr_c if c not in head_c]
            coord_fixes.append((name, head_last, curr_last, new_entries, curr_c))

    # === OUTPUT ===
    print("=" * 100)
    print("OLIVERS KORREKTUREN — Vollständige Liste zur Überprüfung")
    print("=" * 100)

    nr = 0

    print(f"\n{'─'*100}")
    print(f"TEIL 1: UMBENENNUNGEN ({len(renames)} Stationen)")
    print(f"{'─'*100}")
    for old_name, new_name, old_c, new_c, dist in sorted(renames):
        nr += 1
        coord_change = abs(old_c[0] - new_c[0]) > 0.001 or abs(old_c[1] - new_c[1]) > 0.001
        print(f"\n  {nr}. TXT-Name: {old_name}")
        print(f"     Neuer Name: {new_name}")
        if coord_change:
            print(f"     Alt:  ({old_c[0]:.4f}, {old_c[1]:.4f})")
            print(f"     Neu:  ({new_c[0]:.4f}, {new_c[1]:.4f})")
        else:
            print(f"     Koordinaten: ({old_c[0]:.4f}, {old_c[1]:.4f}) [unverändert]")

    print(f"\n{'─'*100}")
    print(f"TEIL 2: NUR KOORDINATEN-KORREKTUREN ({len(coord_fixes)} Stationen)")
    print(f"{'─'*100}")

    # Filter out stations that are also in renames (coord already shown)
    rename_txt_names = {r[0] for r in renames}
    for name, head_c, curr_last, new_entries, all_curr in coord_fixes:
        if name in rename_txt_names:
            continue  # Already shown in renames
        nr += 1
        txt_c = txt.get(name)
        txt_status = ""
        if txt_c:
            if abs(txt_c[0] - head_c[0]) <= 0.001 and abs(txt_c[1] - head_c[1]) <= 0.001:
                txt_status = " [TXT hat alte Koordinaten]"
            elif abs(txt_c[0] - curr_last[0]) <= 0.001 and abs(txt_c[1] - curr_last[1]) <= 0.001:
                txt_status = " [TXT bereits korrekt]"
        else:
            txt_status = " [NICHT in TXT!]"

        print(f"\n  {nr}. {name}{txt_status}")
        print(f"     Alt:    ({head_c[0]:.4f}, {head_c[1]:.4f})")

        if len(new_entries) > 1:
            print(f"     Korrektur-Einträge (mehrere!):")
            for i, (lat, lon) in enumerate(new_entries, 1):
                print(f"       {i}. ({lat:.4f}, {lon:.4f})")
            print(f"     Letzter: ({curr_last[0]:.4f}, {curr_last[1]:.4f})")
        else:
            print(f"     Neu:    ({curr_last[0]:.4f}, {curr_last[1]:.4f})")

    print(f"\n{'='*100}")
    print(f"GESAMT: {nr} Korrekturen")
    print(f"{'='*100}")


if __name__ == '__main__':
    main()
