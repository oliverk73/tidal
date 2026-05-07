#!/usr/bin/env python3
"""
Vergleicht Stationen aus niedrig-rangigen Harmonics-Dateien (Classic 1997/2004, Lavergne)
gegen höherrangige Quellen (DWF 2025, UTide, Puertos, TICON4, DWF 2010/2007).

Für jede Station wird:
1. Ein Match in höherrangigen TCD-Dateien gesucht (Name + Koordinaten < 5km)
2. HW/LW-Vorhersagen generiert und verglichen (Timing + Amplitude)
3. Ergebnis in CSV geschrieben

Aufruf: python3 compare_harmonics_sources.py
"""

import subprocess
import os
import re
import csv
import sys
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime

TCD_DIR = "/usr/share/xtide"

# Sources to CHECK (low-ranked, in order)
CHECK_SOURCES = [
    ('Classic 1997', 'harmonics-1997-05-25_mod.tcd'),
    ('Classic 2004', 'harmonics-2004-06-14_mod.tcd'),
    ('Lavergne v10', 'harmonics-pierre-lavergne-v10_mod.tcd'),
    ('Lavergne v9',  'harmonics-pierre-lavergne-v9-europe_mod.tcd'),
]

# Reference sources (higher-ranked, in priority order)
REF_SOURCES = [
    ('DWF 2025',  'harmonics-dwf-20251228-free.tcd'),
    ('Puertos',   'harmonics_puertos_spain.tcd'),
    ('UTide DE',  'harmonics_utide_germany_z0corrected.tcd'),
    ('UTide NL',  'harmonics_utide_netherlands.tcd'),
    ('UTide FR',  'harmonics_utide_france.tcd'),
    ('UTide BE',  'harmonics_utide_belgium.tcd'),
    ('UTide CA',  'harmonics_utide_canada_all.tcd'),
    ('UTide UK',  'harmonics_utide_uk_bodc.tcd'),
    ('UTide IE',  'harmonics_utide_ireland.tcd'),
    ('UTide UK2', 'harmonics_utide_uk_ireland.tcd'),
    ('UTide DK',  'harmonics_utide_denmark.tcd'),
    ('UTide AU',  'harmonics_utide_australia.tcd'),
    ('UTide AU2', 'harmonics_utide_australia_qld.tcd'),
    ('UTide AU3', 'harmonics_utide_australia_uhslc.tcd'),
    ('DWF 2010',  'harmonics-dwf-20100529-nonfree_mod.tcd'),
    ('DWF 2007',  'harmonics-dwf-20070318_mod.tcd'),
    ('TICON4',    'harmonics_ticon4_worldwide.tcd'),
]

STATION_RE = re.compile(
    r'^(.+?)\s{2,}(Ref|Sub)\s+([\d.]+)°\s*([NS]),\s*([\d.]+)°\s*([EW])$'
)

TIDE_RE = re.compile(
    r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s*[AP]M)\s+UTC\s+([\d.]+)\s+(meters|feet)\s+(High|Low)\s+Tide'
)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))


def normalize_name(name):
    """Normalize station name for matching."""
    n = name.lower().strip()
    # Remove (2), (3), etc.
    n = re.sub(r'\s*\(\d+\)\s*', ' ', n)
    # Remove extra whitespace
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def get_stations(tcd_file):
    """Get all stations from a TCD file via tide -m l."""
    tcd_path = os.path.join(TCD_DIR, tcd_file)
    if not os.path.exists(tcd_path):
        return []
    env = os.environ.copy()
    env["HFILE_PATH"] = tcd_path
    r = subprocess.run(
        ["tide", "-m", "l", "-tw", "200"],
        capture_output=True, text=True, env=env
    )
    stations = []
    for line in (r.stdout or r.stderr).splitlines():
        m = STATION_RE.match(line)
        if m:
            name, stype, lat, ns, lon, ew = m.groups()
            lat = float(lat) * (1 if ns == 'N' else -1)
            lon = float(lon) * (1 if ew == 'E' else -1)
            stations.append((name.strip(), stype, lat, lon))
    return stations


def get_predictions(station_name, tcd_file, date_start="2026-04-03 00:00", date_end="2026-04-05 00:00"):
    """Get HW/LW predictions for a station from a specific TCD file."""
    tcd_path = os.path.join(TCD_DIR, tcd_file)
    env = os.environ.copy()
    env["HFILE_PATH"] = tcd_path
    r = subprocess.run(
        ["tide", "-l", station_name, "-m", "p", "-b", date_start, "-e", date_end,
         "-em", "pSsMm", "-z", "-s", "00:15"],
        capture_output=True, text=True, env=env, timeout=10
    )
    output = r.stdout or ""
    events = []
    for line in output.splitlines():
        m = TIDE_RE.match(line.strip())
        if m:
            date_str, time_str, height, unit, event_type = m.groups()
            # Parse datetime
            dt_str = f"{date_str} {time_str}"
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
            except ValueError:
                try:
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M%p")
                except ValueError:
                    continue
            h = float(height)
            if unit == 'feet':
                h *= 0.3048  # Convert to meters
            events.append({
                'dt': dt,
                'height': h,
                'type': event_type  # 'High' or 'Low'
            })
    return events


def compare_predictions(events_check, events_ref):
    """Compare HW/LW events. Returns (avg_time_diff_min, avg_height_diff_m, n_matched, details)."""
    if not events_check or not events_ref:
        return None, None, 0, "Keine Vorhersagen"

    time_diffs = []
    height_diffs = []

    for ec in events_check:
        # Find closest matching event of same type in ref
        best_diff = None
        best_ref = None
        for er in events_ref:
            if er['type'] != ec['type']:
                continue
            diff_sec = abs((ec['dt'] - er['dt']).total_seconds())
            if diff_sec < 6 * 3600:  # Max 6h difference
                if best_diff is None or diff_sec < abs(best_diff):
                    best_diff = (ec['dt'] - er['dt']).total_seconds()
                    best_ref = er

        if best_ref is not None:
            time_diffs.append(best_diff / 60.0)  # minutes
            height_diffs.append(ec['height'] - best_ref['height'])

    if not time_diffs:
        return None, None, 0, "Keine passenden Events"

    avg_time = sum(time_diffs) / len(time_diffs)
    avg_height = sum(abs(h) for h in height_diffs) / len(height_diffs)

    return avg_time, avg_height, len(time_diffs), "OK"


def find_match(station, ref_stations_by_source):
    """Find best matching reference station. Returns (ref_source, ref_name, distance_km, match_type)."""
    name, stype, lat, lon = station
    norm = normalize_name(name)

    for ref_source_name, ref_stations in ref_stations_by_source:
        # 1. Exact name match
        for rname, rstype, rlat, rlon in ref_stations:
            if normalize_name(rname) == norm:
                dist = haversine(lat, lon, rlat, rlon)
                return ref_source_name, rname, dist, "Name"

        # 2. Proximity match < 3km
        best_dist = 999999
        best_ref = None
        for rname, rstype, rlat, rlon in ref_stations:
            dist = haversine(lat, lon, rlat, rlon)
            if dist < best_dist:
                best_dist = dist
                best_ref = (rname, rstype, rlat, rlon)

        if best_dist < 3.0 and best_ref:
            return ref_source_name, best_ref[0], best_dist, f"Proximity ({best_dist:.1f}km)"

    return None, None, None, "Keine Referenz"


def main():
    print("=== Lade Referenz-Stationen ===")
    ref_data = []
    for ref_name, ref_tcd in REF_SOURCES:
        stations = get_stations(ref_tcd)
        if stations:
            print(f"  {ref_name}: {len(stations)} Stationen")
            ref_data.append((ref_name, ref_tcd, stations))

    ref_stations_for_match = [(name, stations) for name, tcd, stations in ref_data]

    output_file = "/home/oliver/harmonics/help/source_comparison_results.csv"

    with open(output_file, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.writer(csvf, delimiter=';')
        writer.writerow([
            'Quelle', 'Station', 'Typ', 'Lat', 'Lon',
            'Referenz-Quelle', 'Referenz-Station', 'Match-Typ', 'Distanz_km',
            'Ø_Zeitdiff_min', 'Ø_Höhendiff_m', 'N_Events', 'Status'
        ])

        for check_name, check_tcd in CHECK_SOURCES:
            print(f"\n=== Prüfe {check_name} ===")
            check_stations = get_stations(check_tcd)
            print(f"  {len(check_stations)} Stationen geladen")

            matched = 0
            no_ref = 0
            errors = 0

            for idx, (sname, stype, slat, slon) in enumerate(check_stations):
                if idx % 50 == 0 and idx > 0:
                    print(f"  ... {idx}/{len(check_stations)} ({matched} verglichen, {no_ref} ohne Referenz)")

                # Skip current stations for tide comparison
                if 'Current' in sname:
                    writer.writerow([
                        check_name, sname, stype, slat, slon,
                        '', '', '', '',
                        '', '', '', 'Current-Station (übersprungen)'
                    ])
                    continue

                # Find reference
                ref_source, ref_name, dist, match_type = find_match(
                    (sname, stype, slat, slon), ref_stations_for_match
                )

                if not ref_source:
                    no_ref += 1
                    writer.writerow([
                        check_name, sname, stype, slat, slon,
                        '', '', '', '',
                        '', '', '', 'Keine Referenz gefunden'
                    ])
                    continue

                # Find the TCD file for this reference source
                ref_tcd = None
                for rn, rt, rs in ref_data:
                    if rn == ref_source:
                        ref_tcd = rt
                        break

                if not ref_tcd:
                    continue

                # Generate predictions
                try:
                    events_check = get_predictions(sname, check_tcd)
                    events_ref = get_predictions(ref_name, ref_tcd)

                    avg_time, avg_height, n_events, status = compare_predictions(events_check, events_ref)

                    if avg_time is not None:
                        matched += 1
                        writer.writerow([
                            check_name, sname, stype, slat, slon,
                            ref_source, ref_name, match_type, f"{dist:.1f}" if dist else '',
                            f"{avg_time:.1f}", f"{avg_height:.3f}", n_events, status
                        ])
                    else:
                        errors += 1
                        writer.writerow([
                            check_name, sname, stype, slat, slon,
                            ref_source, ref_name, match_type, f"{dist:.1f}" if dist else '',
                            '', '', '', status
                        ])
                except Exception as e:
                    errors += 1
                    writer.writerow([
                        check_name, sname, stype, slat, slon,
                        ref_source, ref_name, match_type, f"{dist:.1f}" if dist else '',
                        '', '', '', f"Fehler: {str(e)[:50]}"
                    ])

            total = len(check_stations)
            print(f"  Fertig: {matched} verglichen, {no_ref} ohne Referenz, {errors} Fehler (von {total})")

    print(f"\nErgebnisse gespeichert: {output_file}")


if __name__ == '__main__':
    main()
