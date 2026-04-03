#!/usr/bin/env python3
"""
Vergleicht Stationen ohne interne Referenz gegen externe APIs:
- NOAA CO-OPS (US-Stationen)
- CHS IWLS (Kanadische Stationen)
- BOM (Australische Stationen)

Liest die source_comparison_results.csv und ergänzt Vergleiche für "Keine Referenz"-Stationen.
"""

import subprocess
import os
import re
import csv
import json
import time
import sys
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

TCD_DIR = "/usr/share/xtide"
RESULTS_FILE = "/home/oliver/harmonics/help/source_comparison_results.csv"
OUTPUT_FILE = "/home/oliver/harmonics/help/source_comparison_external.csv"

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


def fetch_json(url, timeout=15):
    """Fetch JSON from URL with error handling."""
    try:
        req = Request(url, headers={'User-Agent': 'TideComparison/1.0'})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (URLError, HTTPError, json.JSONDecodeError, Exception) as e:
        return None


def get_predictions_xtide(station_name, tcd_file):
    """Get HW/LW predictions from XTide."""
    tcd_path = os.path.join(TCD_DIR, tcd_file)
    env = os.environ.copy()
    env["HFILE_PATH"] = tcd_path
    try:
        r = subprocess.run(
            ["tide", "-l", station_name, "-m", "p", "-b", "2026-04-03 00:00",
             "-e", "2026-04-05 00:00", "-em", "pSsMm", "-z", "-s", "00:15"],
            capture_output=True, text=True, env=env, timeout=10
        )
    except subprocess.TimeoutExpired:
        return []

    events = []
    for line in (r.stdout or "").splitlines():
        m = TIDE_RE.match(line.strip())
        if m:
            date_str, time_str, height, unit, event_type = m.groups()
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
                h *= 0.3048
            events.append({'dt': dt, 'height': h, 'type': event_type})
    return events


def compare_events(events_check, events_ref):
    """Compare HW/LW events."""
    if not events_check or not events_ref:
        return None, None, 0

    time_diffs = []
    height_diffs = []

    for ec in events_check:
        best_diff = None
        best_ref = None
        for er in events_ref:
            if er['type'] != ec['type']:
                continue
            diff_sec = abs((ec['dt'] - er['dt']).total_seconds())
            if diff_sec < 6 * 3600:
                if best_diff is None or diff_sec < abs(best_diff):
                    best_diff = (ec['dt'] - er['dt']).total_seconds()
                    best_ref = er

        if best_ref is not None:
            time_diffs.append(best_diff / 60.0)
            height_diffs.append(ec['height'] - best_ref['height'])

    if not time_diffs:
        return None, None, 0

    avg_time = sum(time_diffs) / len(time_diffs)
    avg_height = sum(abs(h) for h in height_diffs) / len(height_diffs)
    return avg_time, avg_height, len(time_diffs)


# ============================================================
# NOAA CO-OPS API
# ============================================================
def load_noaa_stations():
    """Load NOAA station list."""
    url = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions"
    data = fetch_json(url)
    if not data or 'stations' not in data:
        print("  NOAA Stationsliste konnte nicht geladen werden")
        return []
    stations = []
    for s in data['stations']:
        try:
            stations.append({
                'id': s['id'],
                'name': s['name'],
                'lat': float(s['lat']),
                'lon': float(s['lng']),
            })
        except (KeyError, ValueError):
            pass
    return stations


def get_noaa_predictions(station_id):
    """Get HW/LW from NOAA CO-OPS API."""
    url = (f"https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
           f"?begin_date=20260403&end_date=20260405"
           f"&station={station_id}&product=predictions"
           f"&datum=MSL&units=metric&time_zone=gmt"
           f"&application=tide_comparison&format=json&interval=hilo")
    data = fetch_json(url)
    if not data or 'predictions' not in data:
        return []

    events = []
    for p in data['predictions']:
        try:
            dt = datetime.strptime(p['t'], "%Y-%m-%d %H:%M")
            events.append({
                'dt': dt,
                'height': float(p['v']),
                'type': 'High' if p['type'] == 'H' else 'Low'
            })
        except (ValueError, KeyError):
            pass
    return events


# ============================================================
# CHS IWLS API (Canada)
# ============================================================
def load_chs_stations():
    """Load CHS station list."""
    stations = []
    for region in ['PAC', 'ATL', 'CEN', 'ARC']:
        url = f"https://api-iwls.dfo-mpo.gc.ca/api/v1/stations?chs_region_code={region}"
        data = fetch_json(url)
        if data:
            for s in data:
                try:
                    stations.append({
                        'id': s['id'],
                        'name': s.get('officialName', ''),
                        'lat': float(s['latitude']),
                        'lon': float(s['longitude']),
                    })
                except (KeyError, ValueError, TypeError):
                    pass
    return stations


def get_chs_predictions(station_id):
    """Get HW/LW from CHS API."""
    url = (f"https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/{station_id}/data"
           f"?time-series-code=wlp-hilo"
           f"&from=2026-04-03T00:00:00Z&to=2026-04-05T00:00:00Z")
    data = fetch_json(url)
    if not data:
        return []

    events = []
    for p in data:
        try:
            dt_str = p['eventDate']
            # Handle various datetime formats
            dt_str = dt_str.replace('Z', '').replace('+00:00', '')
            if 'T' in dt_str:
                dt = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S")
            else:
                dt = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
            events.append({
                'dt': dt,
                'height': float(p['value']),
                'type': 'High' if p.get('eventType', '') in ('HW', 'high', 'H') else 'Low'
            })
        except (ValueError, KeyError, TypeError):
            pass
    return events


# ============================================================
# BOM (Australia) - via API
# ============================================================
def load_bom_stations():
    """Try to load BOM station list."""
    # BOM doesn't have a simple public API for tide predictions
    # We'll skip this for now
    return []


# ============================================================
# Main
# ============================================================
def main():
    # Load unmatched stations from previous results
    with open(RESULTS_FILE, encoding='utf-8') as f:
        all_rows = list(csv.DictReader(f, delimiter=';'))

    unmatched = [r for r in all_rows if r['Status'] == 'Keine Referenz gefunden']
    print(f"Insgesamt {len(unmatched)} Stationen ohne interne Referenz")

    # Categorize by likely country/API
    us_stations = []
    ca_stations = []
    other_stations = []

    US_STATES = {'Alabama', 'Alaska', 'Arizona', 'California', 'Colorado', 'Connecticut',
                 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana',
                 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts',
                 'Michigan', 'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska',
                 'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
                 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania',
                 'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah',
                 'Vermont', 'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming',
                 'Puerto Rico', 'Virgin Islands', 'American Samoa', 'Guam', 'CNMI'}

    for r in unmatched:
        parts = r['Station'].rsplit(',', 1)
        last_part = parts[-1].strip() if len(parts) > 1 else ''
        # Remove (2), (3) etc from last part
        last_part_clean = re.sub(r'\s*\(\d+\)', '', last_part).strip()

        if last_part_clean in US_STATES or 'Alaska' in r['Station']:
            us_stations.append(r)
        elif 'Canada' in r['Station']:
            ca_stations.append(r)
        else:
            other_stations.append(r)

    print(f"  US: {len(us_stations)}, Kanada: {len(ca_stations)}, Andere: {len(other_stations)}")

    results = []

    # ---- NOAA ----
    if us_stations:
        print(f"\n=== NOAA API: {len(us_stations)} US-Stationen ===")
        noaa_stations = load_noaa_stations()
        print(f"  {len(noaa_stations)} NOAA-Stationen geladen")

        matched = 0
        for idx, r in enumerate(us_stations):
            if idx % 20 == 0 and idx > 0:
                print(f"  ... {idx}/{len(us_stations)} ({matched} verglichen)")

            lat, lon = float(r['Lat']), float(r['Lon'])

            # Find nearest NOAA station
            best_dist = 999999
            best_noaa = None
            for ns in noaa_stations:
                d = haversine(lat, lon, ns['lat'], ns['lon'])
                if d < best_dist:
                    best_dist = d
                    best_noaa = ns

            if best_dist > 3.0 or not best_noaa:
                results.append({
                    'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
                    'lat': lat, 'lon': lon,
                    'ref_source': '', 'ref_station': '', 'match_type': '',
                    'dist': '', 'time_diff': '', 'height_diff': '',
                    'n_events': '', 'status': 'Keine NOAA-Station <3km'
                })
                continue

            # Get predictions
            tcd_file = 'harmonics-2004-06-14_mod.tcd' if r['Quelle'] == 'Classic 2004' else 'harmonics-1997-05-25_mod.tcd'
            events_check = get_predictions_xtide(r['Station'], tcd_file)

            time.sleep(0.3)  # Rate limit
            events_ref = get_noaa_predictions(best_noaa['id'])

            if not events_check or not events_ref:
                results.append({
                    'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
                    'lat': lat, 'lon': lon,
                    'ref_source': 'NOAA', 'ref_station': best_noaa['name'],
                    'match_type': f"Proximity ({best_dist:.1f}km)",
                    'dist': f"{best_dist:.1f}", 'time_diff': '', 'height_diff': '',
                    'n_events': '', 'status': 'Keine Vorhersagen'
                })
                continue

            avg_time, avg_height, n = compare_events(events_check, events_ref)

            if avg_time is not None:
                matched += 1
                results.append({
                    'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
                    'lat': lat, 'lon': lon,
                    'ref_source': 'NOAA API', 'ref_station': best_noaa['name'],
                    'match_type': f"Proximity ({best_dist:.1f}km)",
                    'dist': f"{best_dist:.1f}",
                    'time_diff': f"{avg_time:.1f}", 'height_diff': f"{avg_height:.3f}",
                    'n_events': n, 'status': 'OK'
                })
            else:
                results.append({
                    'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
                    'lat': lat, 'lon': lon,
                    'ref_source': 'NOAA API', 'ref_station': best_noaa['name'],
                    'match_type': f"Proximity ({best_dist:.1f}km)",
                    'dist': f"{best_dist:.1f}", 'time_diff': '', 'height_diff': '',
                    'n_events': '', 'status': 'Keine passenden Events'
                })

        print(f"  NOAA: {matched} verglichen")

    # ---- CHS ----
    if ca_stations:
        print(f"\n=== CHS API: {len(ca_stations)} kanadische Stationen ===")
        chs_stations = load_chs_stations()
        print(f"  {len(chs_stations)} CHS-Stationen geladen")

        matched = 0
        api_errors = 0
        for idx, r in enumerate(ca_stations):
            if idx % 50 == 0 and idx > 0:
                print(f"  ... {idx}/{len(ca_stations)} ({matched} verglichen, {api_errors} API-Fehler)")

            lat, lon = float(r['Lat']), float(r['Lon'])

            # Find nearest CHS station
            best_dist = 999999
            best_chs = None
            for cs in chs_stations:
                d = haversine(lat, lon, cs['lat'], cs['lon'])
                if d < best_dist:
                    best_dist = d
                    best_chs = cs

            if best_dist > 5.0 or not best_chs:
                results.append({
                    'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
                    'lat': lat, 'lon': lon,
                    'ref_source': '', 'ref_station': '', 'match_type': '',
                    'dist': '', 'time_diff': '', 'height_diff': '',
                    'n_events': '', 'status': 'Keine CHS-Station <5km'
                })
                continue

            tcd_file = 'harmonics-2004-06-14_mod.tcd' if r['Quelle'] == 'Classic 2004' else 'harmonics-1997-05-25_mod.tcd'
            events_check = get_predictions_xtide(r['Station'], tcd_file)

            time.sleep(0.2)  # Rate limit
            events_ref = get_chs_predictions(best_chs['id'])

            if not events_check or not events_ref:
                if not events_ref:
                    api_errors += 1
                results.append({
                    'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
                    'lat': lat, 'lon': lon,
                    'ref_source': 'CHS API', 'ref_station': best_chs['name'],
                    'match_type': f"Proximity ({best_dist:.1f}km)",
                    'dist': f"{best_dist:.1f}", 'time_diff': '', 'height_diff': '',
                    'n_events': '', 'status': 'Keine Vorhersagen'
                })
                continue

            avg_time, avg_height, n = compare_events(events_check, events_ref)

            if avg_time is not None:
                matched += 1
                results.append({
                    'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
                    'lat': lat, 'lon': lon,
                    'ref_source': 'CHS API', 'ref_station': best_chs['name'],
                    'match_type': f"Proximity ({best_dist:.1f}km)",
                    'dist': f"{best_dist:.1f}",
                    'time_diff': f"{avg_time:.1f}", 'height_diff': f"{avg_height:.3f}",
                    'n_events': n, 'status': 'OK'
                })
            else:
                results.append({
                    'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
                    'lat': lat, 'lon': lon,
                    'ref_source': 'CHS API', 'ref_station': best_chs['name'],
                    'match_type': f"Proximity ({best_dist:.1f}km)",
                    'dist': f"{best_dist:.1f}", 'time_diff': '', 'height_diff': '',
                    'n_events': '', 'status': 'Keine passenden Events'
                })

        print(f"  CHS: {matched} verglichen, {api_errors} API-Fehler")

    # ---- Record other stations as unverifiable ----
    for r in other_stations:
        results.append({
            'source': r['Quelle'], 'station': r['Station'], 'type': r['Typ'],
            'lat': r['Lat'], 'lon': r['Lon'],
            'ref_source': '', 'ref_station': '', 'match_type': '',
            'dist': '', 'time_diff': '', 'height_diff': '',
            'n_events': '', 'status': 'Keine externe API verfügbar'
        })

    # Write results
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'source', 'station', 'type', 'lat', 'lon',
            'ref_source', 'ref_station', 'match_type', 'dist',
            'time_diff', 'height_diff', 'n_events', 'status'
        ], delimiter=';')
        writer.writeheader()
        writer.writerows(results)

    print(f"\nErgebnisse gespeichert: {OUTPUT_FILE}")

    # Summary
    ok_results = [r for r in results if r['status'] == 'OK']
    if ok_results:
        tds = [abs(float(r['time_diff'])) for r in ok_results]
        print(f"\n=== Zusammenfassung externe APIs ===")
        print(f"Verglichen: {len(ok_results)}")
        print(f"Ø|Δt|: {sum(tds)/len(tds):.1f}min")
        good = sum(1 for t in tds if t <= 15)
        ok_count = sum(1 for t in tds if 15 < t <= 30)
        bad = sum(1 for t in tds if t > 30)
        print(f"  ≤15min: {good}, 15-30min: {ok_count}, >30min: {bad}")


if __name__ == '__main__':
    main()
