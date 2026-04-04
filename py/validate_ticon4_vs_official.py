#!/usr/bin/env python3
"""
Validiert TICON4-Stationen gegen offizielle Gezeiten-APIs.

Offizielle Quellen (Priorität):
1. BSH Deutschland — JSON API
2. IHM Spanien — JSON API
3. Kartverket Norwegen — XML API
4. NOAA CO-OPS USA — JSON API
5. CHS IWLS Kanada — JSON API

Fallback: Vergleich gegen andere TCD-Dateien (wenn keine offizielle API verfügbar)

Ausgabe: CSV mit Zeitdifferenzen pro Station
"""

import subprocess
import os
import re
import csv
import json
import time
import sys
import xml.etree.ElementTree as ET
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

TCD_DIR = "/usr/share/xtide"
TICON4_TCD = "harmonics_ticon4_worldwide.tcd"
TICON4_TXT = "/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt"
OUTPUT_FILE = "/home/oliver/harmonics/help/ticon4_official_validation.csv"

# Prediction period: 3 days for robust matching
PRED_START = "2026-04-04 00:00"
PRED_END = "2026-04-07 00:00"
PRED_START_ISO = "2026-04-04T00:00:00Z"
PRED_END_ISO = "2026-04-07T00:00:00Z"

# Fallback TCD files (priority order, highest first)
FALLBACK_TCDS = [
    ('DWF 2025', 'harmonics-dwf-20251228-free.tcd'),
    ('UTide DE', 'harmonics_utide_germany_z0corrected.tcd'),
    ('UTide NL', 'harmonics_utide_netherlands.tcd'),
    ('UTide FR', 'harmonics_utide_france.tcd'),
    ('UTide BE', 'harmonics_utide_belgium.tcd'),
    ('UTide CA', 'harmonics_utide_canada_all.tcd'),
    ('UTide UK', 'harmonics_utide_uk_bodc.tcd'),
    ('UTide IE', 'harmonics_utide_ireland.tcd'),
    ('UTide UK2', 'harmonics_utide_uk_ireland.tcd'),
    ('UTide DK', 'harmonics_utide_denmark.tcd'),
    ('UTide AU', 'harmonics_utide_australia.tcd'),
    ('UTide AU2', 'harmonics_utide_australia_qld.tcd'),
    ('UTide AU3', 'harmonics_utide_australia_uhslc.tcd'),
    ('DWF 2010', 'harmonics-dwf-20100529-nonfree.tcd'),
    ('DWF 2007', 'harmonics-dwf-20070318_mod.tcd'),
    ('Lavergne v10', 'harmonics-pierre-lavergne-v10_mod.tcd'),
    ('Classic 2004', 'harmonics-2004-06-14_mod.tcd'),
    ('Classic 1997', 'harmonics-1997-05-25_mod.tcd'),
]

TIDE_RE = re.compile(
    r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s*[AP]M)\s+UTC\s+([\d.]+)\s+(meters|feet)\s+(High|Low)\s+Tide'
)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))


def fetch_json(url, timeout=20):
    try:
        req = Request(url, headers={'User-Agent': 'TideValidation/1.0'})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None


def fetch_xml(url, timeout=20):
    try:
        req = Request(url, headers={'User-Agent': 'TideValidation/1.0'})
        with urlopen(req, timeout=timeout) as resp:
            return ET.fromstring(resp.read())
    except Exception:
        return None


# ============================================================
# Parse TICON4 stations from TXT file (for country info)
# ============================================================
def parse_ticon4_stations_txt():
    """Parse station metadata from TICON4 txt file."""
    with open(TICON4_TXT, 'r', encoding='iso-8859-1') as f:
        lines = f.readlines()

    tz_pat = re.compile(r'^([+-]\d{2}:\d{2})\s+:(.+)')
    stations = {}
    i = 0
    while i < len(lines):
        m = tz_pat.match(lines[i])
        if m and i > 0:
            station_name = lines[i - 1].strip()
            tz_offset = m.group(1)
            country = ''
            source_id = ''
            for j in range(i - 2, max(i - 30, 0), -1):
                line = lines[j].strip()
                if line.startswith('# country:'):
                    country = line.split(':', 1)[1].strip()
                elif line.startswith('# station_id_context:'):
                    source_id = line.split(':', 1)[1].strip()
                elif line.startswith('# BEGIN HOT COMMENTS'):
                    break
            lat, lon = None, None
            for j in range(i - 2, max(i - 30, 0), -1):
                line = lines[j].strip()
                if line.startswith('# !latitude:'):
                    lat = float(line.split(':')[1].strip())
                elif line.startswith('# !longitude:'):
                    lon = float(line.split(':')[1].strip())
                elif line.startswith('# BEGIN HOT COMMENTS'):
                    break
            stations[station_name] = {
                'country': country,
                'source_id': source_id,
                'tz_offset': tz_offset,
                'lat': lat,
                'lon': lon,
            }
        i += 1
    return stations


# ============================================================
# Get TICON4 station list from TCD
# ============================================================
def get_ticon4_tcd_stations():
    """Get station list from TICON4 TCD file."""
    tcd_path = os.path.join(TCD_DIR, TICON4_TCD)
    env = os.environ.copy()
    env["HFILE_PATH"] = tcd_path
    r = subprocess.run(
        ["tide", "-m", "l"],
        capture_output=True, text=True, env=env, timeout=30
    )
    station_re = re.compile(
        r'^(.+?)\s{2,}(Ref|Sub)\s+([\d.]+)\xb0\s*([NS]),\s*([\d.]+)\xb0\s*([EW])$'
    )
    stations = []
    for line in (r.stdout or "").splitlines():
        m = station_re.match(line.strip())
        if m:
            name = m.group(1)
            lat = float(m.group(3)) * (1 if m.group(4) == 'N' else -1)
            lon = float(m.group(5)) * (1 if m.group(6) == 'E' else -1)
            stations.append({'name': name, 'lat': lat, 'lon': lon, 'type': m.group(2)})
    return stations


# ============================================================
# XTide predictions
# ============================================================
def get_predictions_xtide(station_name, tcd_file=TICON4_TCD):
    """Get HW/LW predictions from XTide in UTC."""
    tcd_path = os.path.join(TCD_DIR, tcd_file)
    env = os.environ.copy()
    env["HFILE_PATH"] = tcd_path
    try:
        r = subprocess.run(
            ["tide", "-l", station_name, "-m", "p", "-b", PRED_START,
             "-e", PRED_END, "-em", "pSsMm", "-z", "-s", "00:15"],
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


# ============================================================
# BSH Germany API
# ============================================================
def load_bsh_stations():
    """Load BSH station list."""
    data = fetch_json("https://gezeiten.bsh.de/data/tides_overview.json")
    if not data or 'gauges' not in data:
        print("  BSH: Stationsliste nicht geladen")
        return []
    stations = []
    for g in data['gauges']:
        stations.append({
            'id': g['bshnr'],
            'name': g['station_name'],
            'lat': g['latitude'],
            'lon': g['longitude'],
        })
    return stations


def get_bsh_predictions(station_id):
    """Get HW/LW from BSH API."""
    url = f"https://gezeiten.bsh.de/data/DE__{station_id}_tides.json"
    data = fetch_json(url)
    if not data:
        return []

    events = []
    for year_data in data.get('years', []):
        for entry in year_data.get('hwnw_prediction', {}).get('data', []):
            try:
                ts = entry['timestamp']
                # Parse "2026-04-04 12:26:00+01:00" or similar
                # Remove timezone offset for UTC conversion
                dt_str = ts[:19]
                dt_local = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                # Parse timezone offset
                tz_str = ts[19:].strip()
                if tz_str:
                    sign = 1 if tz_str[0] == '+' else -1
                    parts = tz_str[1:].split(':')
                    tz_hours = int(parts[0])
                    tz_mins = int(parts[1]) if len(parts) > 1 else 0
                    tz_offset = timedelta(hours=sign * tz_hours, minutes=sign * tz_mins)
                    dt_utc = dt_local - tz_offset
                else:
                    dt_utc = dt_local

                height_cm = entry['height']
                event_type = 'High' if entry['type'] == 'HW' else 'Low'

                # Filter to prediction period
                pred_start = datetime(2026, 4, 4)
                pred_end = datetime(2026, 4, 7)
                if pred_start <= dt_utc <= pred_end:
                    events.append({
                        'dt': dt_utc,
                        'height': height_cm / 100.0,  # cm -> m (relative, not comparable)
                        'type': event_type
                    })
            except (ValueError, KeyError, TypeError):
                pass
    return events


# ============================================================
# IHM Spain API
# ============================================================
def load_ihm_stations():
    """Load IHM station list."""
    data = fetch_json("https://ideihm.covam.es/api-ihm/getmarea?request=getlist&format=json")
    if not data:
        print("  IHM: Stationsliste nicht geladen")
        return []
    stations = []
    for p in data.get('estaciones', {}).get('puertos', []):
        try:
            stations.append({
                'id': p['id'],
                'name': p['puerto'],
                'lat': float(p['lat']),
                'lon': float(p['lon']),
            })
        except (KeyError, ValueError):
            pass
    return stations


def get_ihm_predictions(station_id):
    """Get HW/LW from IHM API (month-based)."""
    events = []
    for month in ['202604', '202605']:
        url = f"https://ideihm.covam.es/api-ihm/getmarea?request=gettide&id={station_id}&format=json&month={month}"
        data = fetch_json(url)
        if not data:
            continue
        for day_data in data.get('mapiDelDia', data.get('datos', [])):
            # Structure may vary, try both formats
            if isinstance(day_data, dict):
                for key in ['datos', 'data']:
                    if key in day_data:
                        for entry in day_data[key]:
                            _parse_ihm_entry(entry, events)
                # Direct entry
                _parse_ihm_entry(day_data, events)
    return events


def _parse_ihm_entry(entry, events):
    """Parse a single IHM tide entry."""
    try:
        hora = entry.get('hora', '')
        altura = entry.get('altura')
        tipo = entry.get('tipo', '')
        fecha = entry.get('fecha', '')

        if not hora or altura is None or not fecha:
            return

        dt_str = f"{fecha} {hora}"
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        # IHM times are in local time (CET = UTC+1)
        dt_utc = dt - timedelta(hours=1)

        event_type = 'High' if 'pleamar' in tipo.lower() else 'Low'

        pred_start = datetime(2026, 4, 4)
        pred_end = datetime(2026, 4, 7)
        if pred_start <= dt_utc <= pred_end:
            events.append({
                'dt': dt_utc,
                'height': float(altura),
                'type': event_type
            })
    except (ValueError, KeyError, TypeError, AttributeError):
        pass


# ============================================================
# Kartverket Norway API
# ============================================================
def get_kartverket_predictions(lat, lon):
    """Get HW/LW from Kartverket API."""
    url = (f"https://vannstand.kartverket.no/tideapi.php?"
           f"lat={lat}&lon={lon}"
           f"&fromtime=2026-04-04T00:00:00&totime=2026-04-07T00:00:00"
           f"&datatype=tab&refcode=cd&lang=en&interval=60&dst=0&tzone=0"
           f"&tide_request=locationdata")
    root = fetch_xml(url)
    if root is None:
        return []

    events = []
    for wl in root.iter('waterlevel'):
        try:
            flag = wl.get('flag', '')
            if flag not in ('high', 'low'):
                continue
            value_cm = float(wl.get('value'))
            time_str = wl.get('time')
            # Parse "2026-04-04T06:19:00+00:00"
            dt = datetime.strptime(time_str[:19], "%Y-%m-%dT%H:%M:%S")
            events.append({
                'dt': dt,  # already UTC (tzone=0)
                'height': value_cm / 100.0,
                'type': 'High' if flag == 'high' else 'Low'
            })
        except (ValueError, TypeError):
            pass
    return events


# ============================================================
# NOAA CO-OPS API
# ============================================================
_noaa_stations_cache = None

def load_noaa_stations():
    global _noaa_stations_cache
    if _noaa_stations_cache is not None:
        return _noaa_stations_cache
    data = fetch_json("https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions")
    if not data or 'stations' not in data:
        print("  NOAA: Stationsliste nicht geladen")
        _noaa_stations_cache = []
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
    _noaa_stations_cache = stations
    return stations


def get_noaa_predictions(station_id):
    """Get HW/LW from NOAA API."""
    url = (f"https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
           f"?begin_date=20260404&end_date=20260407"
           f"&station={station_id}&product=predictions"
           f"&datum=MSL&units=metric&time_zone=gmt"
           f"&application=tide_validation&format=json&interval=hilo")
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
_chs_stations_cache = None

def load_chs_stations():
    global _chs_stations_cache
    if _chs_stations_cache is not None:
        return _chs_stations_cache
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
    _chs_stations_cache = stations
    return stations


def get_chs_predictions(station_id):
    """Get HW/LW from CHS API."""
    url = (f"https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/{station_id}/data"
           f"?time-series-code=wlp-hilo"
           f"&from=2026-04-04T00:00:00Z&to=2026-04-07T00:00:00Z")
    data = fetch_json(url)
    if not data:
        return []

    events = []
    prev_val = None
    for p in data:
        try:
            dt_str = p['eventDate'].replace('Z', '').replace('+00:00', '')
            if 'T' in dt_str:
                dt = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S")
            else:
                dt = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
            val = float(p['value'])
            # CHS doesn't provide HW/LW type, infer from value
            event_type = p.get('eventType', '')
            if event_type in ('HW', 'high', 'H'):
                etype = 'High'
            elif event_type in ('LW', 'low', 'L'):
                etype = 'Low'
            elif prev_val is not None:
                etype = 'High' if val > prev_val else 'Low'
            else:
                etype = 'High'  # first event, will be corrected
            prev_val = val
            events.append({'dt': dt, 'height': val, 'type': etype})
        except (ValueError, KeyError, TypeError):
            pass
    return events


# ============================================================
# Event comparison
# ============================================================
def compare_events(events_ticon, events_ref):
    """Compare HW/LW events, return avg time diff in minutes."""
    if not events_ticon or not events_ref:
        return None, None, 0

    time_diffs = []
    height_diffs = []

    for et in events_ticon:
        best_diff = None
        best_ref = None
        for er in events_ref:
            if er['type'] != et['type']:
                continue
            diff_sec = abs((et['dt'] - er['dt']).total_seconds())
            if diff_sec < 6 * 3600:  # max 6h tolerance
                if best_diff is None or diff_sec < abs(best_diff):
                    best_diff = (et['dt'] - er['dt']).total_seconds()
                    best_ref = er

        if best_ref is not None:
            time_diffs.append(best_diff / 60.0)
            height_diffs.append(et['height'] - best_ref['height'])

    if not time_diffs:
        return None, None, 0

    avg_time = sum(time_diffs) / len(time_diffs)
    avg_height = sum(abs(h) for h in height_diffs) / len(height_diffs)
    return avg_time, avg_height, len(time_diffs)


# ============================================================
# Fallback: find station in other TCD files
# ============================================================
_fallback_station_cache = {}

def load_fallback_stations(tcd_name):
    """Load station list from a fallback TCD."""
    if tcd_name in _fallback_station_cache:
        return _fallback_station_cache[tcd_name]

    tcd_path = os.path.join(TCD_DIR, tcd_name)
    if not os.path.exists(tcd_path):
        _fallback_station_cache[tcd_name] = []
        return []

    env = os.environ.copy()
    env["HFILE_PATH"] = tcd_path
    try:
        r = subprocess.run(
            ["tide", "-m", "l"],
            capture_output=True, text=True, env=env, timeout=30
        )
    except subprocess.TimeoutExpired:
        _fallback_station_cache[tcd_name] = []
        return []

    station_re = re.compile(
        r'^(.+?)\s{2,}(Ref|Sub)\s+([\d.]+)\xb0\s*([NS]),\s*([\d.]+)\xb0\s*([EW])$'
    )
    stations = []
    for line in (r.stdout or "").splitlines():
        m = station_re.match(line.strip())
        if m:
            name = m.group(1)
            lat = float(m.group(3)) * (1 if m.group(4) == 'N' else -1)
            lon = float(m.group(5)) * (1 if m.group(6) == 'E' else -1)
            stations.append({'name': name, 'lat': lat, 'lon': lon})

    _fallback_station_cache[tcd_name] = stations
    return stations


def find_fallback_match(station_name, lat, lon):
    """Find matching station in fallback TCD files."""
    norm_name = station_name.lower().strip()

    for source_name, tcd_file in FALLBACK_TCDS:
        fb_stations = load_fallback_stations(tcd_file)
        for fs in fb_stations:
            d = haversine(lat, lon, fs['lat'], fs['lon'])
            if d < 5.0:  # within 5km
                events = get_predictions_xtide(fs['name'], tcd_file)
                if events:
                    return source_name, fs['name'], events
    return None, None, None


# ============================================================
# Main
# ============================================================
def main():
    print("=== TICON4 Validierung gegen offizielle APIs ===\n")

    # Parse station metadata
    print("Lade TICON4-Stationsmetadaten...")
    station_meta = parse_ticon4_stations_txt()
    print(f"  {len(station_meta)} Stationen aus TXT geladen")

    # Get station list from TCD
    print("Lade TICON4-Stationsliste aus TCD...")
    tcd_stations = get_ticon4_tcd_stations()
    print(f"  {len(tcd_stations)} Stationen aus TCD geladen")

    # Load official station lists
    print("\nLade offizielle Stationslisten...")
    bsh_stations = load_bsh_stations()
    print(f"  BSH: {len(bsh_stations)} Stationen")
    ihm_stations = load_ihm_stations()
    print(f"  IHM Spanien: {len(ihm_stations)} Stationen")
    noaa_stations = load_noaa_stations()
    print(f"  NOAA: {len(noaa_stations)} Stationen")
    chs_stations = load_chs_stations()
    print(f"  CHS Kanada: {len(chs_stations)} Stationen")

    # Country -> API mapping
    # BSH: Germany, IHM: Spain, Kartverket: Norway, NOAA: USA, CHS: Canada
    results = []
    api_stats = {'BSH': 0, 'IHM': 0, 'Kartverket': 0, 'NOAA': 0, 'CHS': 0, 'Fallback': 0, 'Keine Referenz': 0}

    total = len(tcd_stations)
    print(f"\nValidiere {total} TICON4-Stationen...\n")

    for idx, ts in enumerate(tcd_stations):
        name = ts['name']
        lat = ts['lat']
        lon = ts['lon']

        meta = station_meta.get(name, {})
        country = meta.get('country', '')
        source_id = meta.get('source_id', '')
        tz_offset = meta.get('tz_offset', '')

        if idx % 50 == 0:
            print(f"  [{idx}/{total}] {name}")

        # Try official APIs based on country
        ref_source = ''
        ref_station = ''
        events_ref = None

        # 1. BSH (Germany)
        if country == 'Germany' and bsh_stations:
            best_dist = 999999
            best_bsh = None
            for bs in bsh_stations:
                d = haversine(lat, lon, bs['lat'], bs['lon'])
                if d < best_dist:
                    best_dist = d
                    best_bsh = bs
            if best_dist < 5.0 and best_bsh:
                events_ref = get_bsh_predictions(best_bsh['id'])
                if events_ref:
                    ref_source = 'BSH'
                    ref_station = best_bsh['name']
                    api_stats['BSH'] += 1
                time.sleep(0.2)

        # 2. IHM (Spain)
        elif country == 'Spain' and ihm_stations:
            best_dist = 999999
            best_ihm = None
            for ih in ihm_stations:
                d = haversine(lat, lon, ih['lat'], ih['lon'])
                if d < best_dist:
                    best_dist = d
                    best_ihm = ih
            if best_dist < 10.0 and best_ihm:
                events_ref = get_ihm_predictions(best_ihm['id'])
                if events_ref:
                    ref_source = 'IHM'
                    ref_station = best_ihm['name']
                    api_stats['IHM'] += 1
                time.sleep(0.3)

        # 3. Kartverket (Norway)
        elif country == 'Norway':
            events_ref = get_kartverket_predictions(lat, lon)
            if events_ref:
                ref_source = 'Kartverket'
                ref_station = f"lat={lat},lon={lon}"
                api_stats['Kartverket'] += 1
            time.sleep(0.3)

        # 4. NOAA (USA + territories)
        elif country in ('United States', 'USA') and noaa_stations:
            best_dist = 999999
            best_noaa = None
            for ns in noaa_stations:
                d = haversine(lat, lon, ns['lat'], ns['lon'])
                if d < best_dist:
                    best_dist = d
                    best_noaa = ns
            if best_dist < 5.0 and best_noaa:
                events_ref = get_noaa_predictions(best_noaa['id'])
                if events_ref:
                    ref_source = 'NOAA'
                    ref_station = best_noaa['name']
                    api_stats['NOAA'] += 1
                time.sleep(0.3)

        # 5. CHS (Canada)
        elif country == 'Canada' and chs_stations:
            best_dist = 999999
            best_chs = None
            for cs in chs_stations:
                d = haversine(lat, lon, cs['lat'], cs['lon'])
                if d < best_dist:
                    best_dist = d
                    best_chs = cs
            if best_dist < 5.0 and best_chs:
                events_ref = get_chs_predictions(best_chs['id'])
                if events_ref:
                    ref_source = 'CHS'
                    ref_station = best_chs['name']
                    api_stats['CHS'] += 1
                time.sleep(0.2)

        # 6. Fallback: other TCD files
        if not events_ref:
            fb_source, fb_name, fb_events = find_fallback_match(name, lat, lon)
            if fb_events:
                events_ref = fb_events
                ref_source = f"Fallback:{fb_source}"
                ref_station = fb_name
                api_stats['Fallback'] += 1

        # Get TICON4 predictions
        events_ticon = get_predictions_xtide(name)

        if not events_ref:
            api_stats['Keine Referenz'] += 1
            results.append({
                'station': name, 'country': country, 'lat': lat, 'lon': lon,
                'tz_offset': tz_offset, 'source_id': source_id,
                'ref_source': '', 'ref_station': '',
                'avg_time_diff_min': '', 'avg_height_diff_m': '',
                'n_events': 0, 'status': 'Keine Referenz'
            })
            continue

        avg_time, avg_height, n = compare_events(events_ticon, events_ref)

        if avg_time is not None:
            # Classify
            abs_time = abs(avg_time)
            if abs_time <= 15:
                status = 'OK'
            elif abs_time <= 30:
                status = 'Akzeptabel'
            elif abs_time <= 60:
                status = 'Verdächtig'
            else:
                status = 'FEHLER'

            results.append({
                'station': name, 'country': country, 'lat': lat, 'lon': lon,
                'tz_offset': tz_offset, 'source_id': source_id,
                'ref_source': ref_source, 'ref_station': ref_station,
                'avg_time_diff_min': f"{avg_time:.1f}",
                'avg_height_diff_m': f"{avg_height:.3f}" if avg_height is not None else '',
                'n_events': n, 'status': status
            })
        else:
            results.append({
                'station': name, 'country': country, 'lat': lat, 'lon': lon,
                'tz_offset': tz_offset, 'source_id': source_id,
                'ref_source': ref_source, 'ref_station': ref_station,
                'avg_time_diff_min': '', 'avg_height_diff_m': '',
                'n_events': 0, 'status': 'Keine passenden Events'
            })

    # Write CSV
    print(f"\nSchreibe Ergebnisse nach {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'station', 'country', 'lat', 'lon', 'tz_offset', 'source_id',
            'ref_source', 'ref_station',
            'avg_time_diff_min', 'avg_height_diff_m', 'n_events', 'status'
        ], delimiter=';')
        writer.writeheader()
        writer.writerows(results)

    # Summary
    print(f"\n{'='*60}")
    print(f"ZUSAMMENFASSUNG")
    print(f"{'='*60}")
    print(f"Stationen gesamt: {total}")
    print(f"\nAPI-Abdeckung:")
    for api, count in sorted(api_stats.items(), key=lambda x: -x[1]):
        print(f"  {api}: {count}")

    compared = [r for r in results if r['status'] not in ('Keine Referenz', 'Keine passenden Events')]
    if compared:
        time_diffs = [abs(float(r['avg_time_diff_min'])) for r in compared]
        print(f"\nVergleichsergebnisse ({len(compared)} Stationen):")
        print(f"  Ø|Δt|: {sum(time_diffs)/len(time_diffs):.1f} min")
        ok = sum(1 for t in time_diffs if t <= 15)
        akz = sum(1 for t in time_diffs if 15 < t <= 30)
        verd = sum(1 for t in time_diffs if 30 < t <= 60)
        fehler = sum(1 for t in time_diffs if t > 60)
        print(f"  OK (≤15min):       {ok}")
        print(f"  Akzeptabel (15-30): {akz}")
        print(f"  Verdächtig (30-60): {verd}")
        print(f"  FEHLER (>60min):    {fehler}")

        if fehler > 0:
            print(f"\n  FEHLER-Stationen (>60min Abweichung):")
            for r in sorted(compared, key=lambda x: abs(float(x['avg_time_diff_min'])), reverse=True):
                if abs(float(r['avg_time_diff_min'])) > 60:
                    print(f"    {r['station']} [{r['country']}]: "
                          f"Δt={r['avg_time_diff_min']}min (Ref: {r['ref_source']})")

    print(f"\nErgebnisse: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
