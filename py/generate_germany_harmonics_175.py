#!/usr/bin/env python3
"""
Generate Harmonic Constants from German Pegelonline water level measurements.
Uses UTide for proper harmonic analysis with equilibrium arguments and node factors.
Outputs 175 tidal constituents compatible with XTide format.

Phase convention:
  UTide outputs Greenwich phase lag (g).
  XTide stores Modified Epoch / Kappa Prime (κ').
  Conversion: κ' = g - p * S
    where p = species number, S = time meridian in degrees.
"""
import numpy as np
from datetime import datetime, timedelta, timezone
import os
import json
import zipfile
import requests
from pathlib import Path
import utide

# CET timezone offset: +01:00 = 15 degrees east
TIME_MERIDIAN_HOURS = 1
TIME_MERIDIAN_DEGREES = TIME_MERIDIAN_HOURS * 15  # = 15°

# 175 Constituents with speeds in degrees per solar hour (XTide order)
CONSTITUENTS_175 = [
    ('J1', 15.5854433), ('K1', 15.0410686), ('K2', 30.0821373), ('L2', 29.5284789),
    ('M1', 14.4966939), ('M2', 28.9841042), ('M3', 43.4761563), ('M4', 57.9682084),
    ('M6', 86.9523126), ('M8', 115.9364169), ('N2', 28.4397295), ('2N2', 27.8953548),
    ('O1', 13.9430356), ('OO1', 16.1391017), ('P1', 14.9589314), ('Q1', 13.3986609),
    ('2Q1', 12.8542862), ('R2', 30.0410667), ('S1', 15.0000000), ('S2', 30.0000000),
    ('S4', 60.0000000), ('S6', 90.0000000), ('T2', 29.9589333), ('LDA2', 29.4556253),
    ('MU2', 27.9682084), ('NU2', 28.5125831), ('RHO1', 13.4715145), ('MK3', 44.0251729),
    ('2MK3', 42.9271398), ('MN4', 57.4238337), ('MS4', 58.9841042), ('2SM2', 31.0158958),
    ('MF', 1.0980331), ('MSF', 1.0158958), ('MM', 0.5443747), ('SA', 0.0410686),
    ('SSA', 0.0821373), ('SA-IOS', 0.0410667), ('MF-IOS', 1.0980331), ('S1-IOS', 15.0000020),
    ('OO1-IOS', 16.1391017), ('R2-IOS', 30.0410667), ('A7', 1.6424078), ('2MK5', 73.0092771),
    ('2MK6', 88.0503457), ('2MN2', 29.5284789), ('2MN6', 86.4079379), ('2MS6', 87.9682084),
    ('2NM6', 85.8635632), ('2SK5', 75.0410686), ('2SM6', 88.9841042), ('3MK7', 101.9933813),
    ('3MN8', 115.3920422), ('3MS2', 26.9523126), ('3MS4', 56.9523126), ('3MS8', 116.9523126),
    ('ALP1', 12.3827651), ('BET1', 14.4145567), ('CHI1', 14.5695476), ('H1', 28.9430375),
    ('H2', 29.0251709), ('KJ2', 30.6265120), ('ETA2', 30.6265120), ('KQ1', 16.6834764),
    ('UPS1', 16.6834764), ('M10', 144.9205211), ('M12', 173.9046253), ('MK4', 59.0662415),
    ('MKS2', 29.0662415), ('MNS2', 27.4238337), ('EPS2', 27.4238337), ('MO3', 42.9271398),
    ('MP1', 14.0251729), ('TAU1', 14.0251729), ('MPS2', 28.9430356), ('MSK6', 89.0662415),
    ('MSM', 0.4715211), ('MSN2', 30.5443747), ('MSN6', 87.4238337), ('NLK2', 27.8860711),
    ('NO1', 14.4966939), ('OP2', 28.9019669), ('OQ2', 27.3509801), ('PHI1', 15.1232059),
    ('KP1', 15.1232059), ('PI1', 14.9178647), ('TK1', 14.9178647), ('PSI1', 15.0821353),
    ('RP1', 15.0821353), ('S3', 45.0000000), ('SIG1', 12.9271398), ('SK3', 45.0410686),
    ('SK4', 60.0821373), ('SN4', 58.4397295), ('SNK6', 88.5218668), ('SO1', 16.0569644),
    ('SO3', 43.9430356), ('THE1', 15.5125897), ('2PO1', 15.9748271), ('2NS2', 26.8794590),
    ('MLN2S2', 26.9523126), ('2ML2S2', 27.4966873), ('SKM2', 31.0980331), ('2MS2K2', 27.8039339),
    ('MKL2S2', 28.5947204), ('M2(KS)2', 29.1483788), ('2SN(MK)2', 29.3734880), ('2KM(SN)2', 30.7086493),
    ('NO3', 42.3827651), ('2MLS4', 57.4966873), ('ML4', 58.5125831), ('N4', 56.8794590),
    ('SL4', 59.5284789), ('MNO5', 71.3668693), ('2MO5', 71.9112440), ('MSK5', 74.0251729),
    ('3KM5', 74.1073101), ('2MP5', 72.9271398), ('3MP5', 71.9933813), ('MNK5', 72.4649024),
    ('2NMLS6', 85.3920422), ('MSL6', 88.5125831), ('2ML6', 87.4966873), ('2MNLS6', 85.9364169),
    ('3MLS6', 86.4807916), ('2MNO7', 100.3509735), ('2NMK7', 100.9046319), ('2MSO7', 101.9112440),
    ('MSKO7', 103.0092771), ('2MSN8', 116.4079379), ('2(MS)8', 117.9682084), ('2(MN)8', 114.8476675),
    ('2MSL8', 117.4966873), ('4MLS8', 115.4648958), ('3ML8', 116.4807916), ('3MK8', 117.0344499),
    ('2MSK8', 118.0503457), ('2M2NK9', 129.8887361), ('3MNK9', 130.4331108), ('4MK9', 130.9774855),
    ('3MSK9', 131.9933813), ('4MN10', 144.3761464), ('3MNS10', 145.3920422), ('4MS10', 145.9364169),
    ('3MSL10', 146.4807916), ('3M2S10', 146.9523126), ('4MSK11', 160.9774855), ('4MNS12', 174.3761464),
    ('5MS12', 174.9205211), ('4MSL12', 175.4648958), ('4M2S12', 175.9364169), ('M1C', 14.4920521),
    ('3MKS2', 26.8701754), ('OQ2-HORN', 27.3416965), ('MSK2', 28.9019669), ('MSP2', 29.0251729),
    ('2MP3', 43.0092771), ('4MS4', 55.9364169), ('2MNS4', 56.4079379), ('2MSK4', 57.8860711),
    ('3MN4', 58.5125831), ('2MSN4', 59.5284789), ('3MK5', 71.9112440), ('3MO5', 73.0092771),
    ('3MNS6', 85.3920422), ('4MS6', 85.9364169), ('2MNU6', 86.4807916), ('3MSK6', 86.8701754),
    ('MKNU6', 87.5788246), ('3MSN6', 88.5125831), ('M7', 101.4490066), ('2MNK8', 116.4900752),
    ('2(MS)N10', 146.4079379), ('MNUS2', 27.4966873), ('2MK2', 27.8860711),
]

# Explicit name mapping: UTide name -> XTide name
# For constituents where names differ but speeds match
UTIDE_TO_XTIDE_NAME = {
    'SA':   'SA-IOS',   # UTide SA speed 0.0410667 matches SA-IOS, not SA (0.0410686)
    'S1':   'S1-IOS',   # UTide S1 speed 15.0000020 matches S1-IOS
    'ETA2': 'ETA2',
    'NO1':  'NO1',
    'TAU1': 'TAU1',
    'EPS2': 'EPS2',
}

# Build speed-based lookup for XTide constituents
XTIDE_BY_SPEED = {}
for name, speed in CONSTITUENTS_175:
    key = round(speed * 1000)  # round to 0.001 deg/hr for matching
    if key not in XTIDE_BY_SPEED:
        XTIDE_BY_SPEED[key] = []
    XTIDE_BY_SPEED[key].append((name, speed))


def get_species(speed):
    """Determine species number from constituent speed (degrees/hour)."""
    return round(speed / (360.0 / 24.0))


def greenwich_to_kappa_prime(greenwich_phase, speed):
    """
    Convert Greenwich phase lag (g) to Modified Epoch (κ').
    κ' = g - p * S
    where p = species, S = time meridian in degrees.
    """
    species = get_species(speed)
    kappa_prime = greenwich_phase - species * TIME_MERIDIAN_DEGREES
    # Normalize to 0-360
    kappa_prime = kappa_prime % 360
    return kappa_prime


def find_xtide_match(utide_name, utide_speed):
    """Find matching XTide constituent by name or speed."""
    # First try explicit name mapping
    mapped_name = UTIDE_TO_XTIDE_NAME.get(utide_name, utide_name)

    # Try exact name match
    for xt_name, xt_speed in CONSTITUENTS_175:
        if xt_name == mapped_name:
            return xt_name, xt_speed

    # Try speed match (within 0.001 deg/hr)
    key = round(utide_speed * 1000)
    for delta in [0, -1, 1]:
        candidates = XTIDE_BY_SPEED.get(key + delta, [])
        for xt_name, xt_speed in candidates:
            if abs(xt_speed - utide_speed) < 0.002:
                return xt_name, xt_speed

    return None, None


def parse_json_water_levels(zip_path, sample_interval_minutes=60, use_last_n_years=5):
    """
    Parse water level data from Pegelonline ZIP file.
    Returns UTC datetime array and levels in meters.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith(':Zone.Identifier'):
                    continue
                with zf.open(name) as f:
                    content = f.read()
                    break
    except Exception as e:
        return None

    try:
        data = json.loads(content.decode('utf-8'))
    except:
        return None

    if not data or len(data) < 1000:
        return None

    # Use only the last n years of data
    samples_per_year = 365 * 24 * 60  # 1-minute data
    max_samples = use_last_n_years * samples_per_year
    if len(data) > max_samples:
        data = data[-max_samples:]

    datetimes_utc = []
    levels = []

    # Sample at specified interval
    for i in range(0, len(data), sample_interval_minutes):
        entry = data[i]
        value = entry.get('value')

        if value is None:
            continue

        ts_str = entry['timestamp']
        try:
            # Parse timestamp: "2000-01-01T01:00:00+01:00" (CET)
            #              or: "2024-07-15T12:00:00+02:00" (CEST)
            # Extract the actual UTC offset from each timestamp
            ts_base = ts_str[:19]
            dt_local = datetime.strptime(ts_base, "%Y-%m-%dT%H:%M:%S")

            # Parse UTC offset: "+01:00" or "+02:00"
            if '+' in ts_str[19:]:
                offset_str = ts_str[19:].lstrip('+')
                offset_parts = offset_str.split(':')
                offset_hours = int(offset_parts[0])
                offset_minutes = int(offset_parts[1]) if len(offset_parts) > 1 else 0
                utc_offset = timedelta(hours=offset_hours, minutes=offset_minutes)
            elif '-' in ts_str[19:]:
                offset_str = ts_str[19:].lstrip('-')
                offset_parts = offset_str.split(':')
                offset_hours = int(offset_parts[0])
                offset_minutes = int(offset_parts[1]) if len(offset_parts) > 1 else 0
                utc_offset = -timedelta(hours=offset_hours, minutes=offset_minutes)
            else:
                utc_offset = timedelta(hours=1)  # Default CET

            # Convert to UTC
            dt_utc = dt_local - utc_offset

            level = float(value) / 100.0  # cm to meters
            datetimes_utc.append(dt_utc)
            levels.append(level)
        except:
            continue

    if len(datetimes_utc) < 8760:  # Minimum ~1 year of hourly data
        print(f" WARNING: only {len(datetimes_utc)} obs (< 8760 for 1 year)", end='')
        if len(datetimes_utc) < 2000:
            return None

    return {
        'datetimes_utc': np.array(datetimes_utc),
        'levels': np.array(levels),
        'start_time': datetimes_utc[0],
        'n_obs': len(datetimes_utc)
    }


def harmonic_analysis_utide(datetimes_utc, levels, lat):
    """
    Perform harmonic analysis using UTide.
    Returns results with Greenwich phase lags converted to Modified Epochs.
    """
    # UTide solve - let it choose constituents automatically based on record length
    try:
        coef = utide.solve(
            datetimes_utc,
            levels,
            lat=lat,
            nodal=True,       # Apply nodal corrections
            trend=False,       # No linear trend (tides only)
            method='ols',      # Ordinary least squares
            conf_int='linear', # Confidence intervals
            verbose=False,
            constit='auto',    # Auto-select based on record length
        )
    except Exception as e:
        print(f" UTide error: {e}", end='')
        return None

    # Map UTide results to XTide 175-constituent format
    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amplitude = coef['A'][i]
        greenwich_phase = coef['g'][i]
        snr = coef['SNR'][i] if 'SNR' in coef else 999

        # Get UTide speed for this constituent
        from utide._ut_constants import ut_constants
        const_table = ut_constants['const']
        utide_names = [n.strip() for n in const_table.name]
        if uname in utide_names:
            idx = utide_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue

        # Find matching XTide constituent
        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue

        # Store Greenwich phase directly (matching DWF convention with +00:00 meridian)
        utide_results[xt_name] = {
            'amplitude': amplitude,
            'phase': greenwich_phase % 360,
            'snr': snr
        }

    # Build full 175-constituent result
    results = {'mean': coef['mean'], 'constituents': []}

    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            results['constituents'].append({
                'name': name,
                'amplitude': r['amplitude'],
                'phase': r['phase'],
                'speed': speed,
                'snr': r['snr']
            })
        else:
            results['constituents'].append({
                'name': name,
                'amplitude': 0.0,
                'phase': 0.0,
                'speed': speed,
                'not_analyzed': True
            })

    # Goodness of fit via reconstruction
    try:
        reconstruction = utide.reconstruct(datetimes_utc, coef, verbose=False)
        h_predicted = reconstruction['h']
        residuals = levels - h_predicted
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((levels - np.mean(levels))**2)
        results['r_squared'] = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        results['rms_error'] = np.sqrt(np.mean(residuals**2))
    except:
        results['r_squared'] = 0
        results['rms_error'] = 0

    # Count analyzed constituents
    results['n_analyzed'] = sum(1 for c in results['constituents'] if not c.get('not_analyzed'))

    return results


def normalize_for_matching(text):
    """Normalize a string for fuzzy matching: lowercase, remove umlauts/special chars."""
    text = text.lower()
    # Replace German umlauts and special chars
    replacements = {
        'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'á': 'a', 'à': 'a', 'â': 'a',
        'ó': 'o', 'ò': 'o', 'ô': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u',
        'í': 'i', 'ì': 'i', 'î': 'i',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Remove everything except alphanumeric
    text = ''.join(c for c in text if c.isalnum())
    return text


def extract_stations_from_harmonics(harmonics_file):
    """
    Extract station info (name, lat, lon, water body) from existing harmonics file.
    Returns list of station dicts.
    """
    stations = []
    current = {}

    with open(harmonics_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith('# !latitude:'):
            current['latitude'] = float(stripped.split(':')[1].strip())
        elif stripped.startswith('# !longitude:'):
            current['longitude'] = float(stripped.split(':')[1].strip())
        elif stripped.startswith('# Water body:'):
            current['water'] = stripped.split(':', 1)[1].strip()
        elif stripped.endswith(', Germany') and not stripped.startswith('#'):
            current['name'] = stripped.replace(', Germany', '')
            current['full_name'] = stripped
            if 'latitude' in current and 'longitude' in current:
                stations.append(current.copy())
            current = {}

    return stations


def build_station_lookup(stations):
    """Build a fuzzy-matchable lookup from station list."""
    lookup = {}
    for station in stations:
        name = station['name']
        # Generate multiple normalized keys
        norm = normalize_for_matching(name)
        lookup[norm] = station

        # Also try without parenthetical parts: "Bremerhaven (Alter Leuchtturm)" -> "bremerhaven"
        if '(' in name:
            main_part = name.split('(')[0].strip()
            lookup[normalize_for_matching(main_part)] = station

            # Also: content inside parens: "Alter Leuchtturm"
            paren_part = name.split('(')[1].rstrip(')')
            combined = normalize_for_matching(main_part + paren_part)
            lookup[combined] = station

        # Hyphenated names: "Cuxhaven-Steubenhöft (Elbe)" -> "cuxhavensteubenhoft"
        if '-' in name:
            lookup[normalize_for_matching(name.replace('-', ''))] = station

    return lookup


# Manual overrides for ZIP keys that can't be fuzzy-matched
ZIP_KEY_OVERRIDES = {
    'lne': 'Lüneburg (Ilmenau)',
    'bhvalterleuchtturm': 'Bremerhaven (Alter Leuchtturm)',
    'bremervrdeuw': 'Bremervörde (Oste)',
    'brunsbttelmpm': 'Brunsbüttel (Elbe)',
    'buttelerhrne': 'Buttelerhörne (Hunte)',
    'cuxhavensteubenhft': 'Cuxhaven-Steubenhöft (Elbe)',
    'eidersperrwerkap': 'Eider-Sperrwerk (Außenpegel)',
    'elmshornhafen': 'Elsmhorn Hafen (Krückau)',
    'emdenneueseeschleuse': 'Emden (Ems, Große Seeschleuse)',
    'esteinneressperrwerkbp': 'Este (Inneres Sperrwerk Binnepegel)',
    'friedrichstadtstrassenbrcke': 'Friedrichstadt (Eider Strassenbrücke)',
    'grosseweserbrcke': 'Bremen (Wilhelm-Kaisen-Brücke, Weser)',
    'krckausperrwerkap': 'Krückau-Sperrwerk (Außenpegel)',
    'krckausperrwerkbp': 'Krückau-Sperrwerk (Binnenpegel)',
    'lexfhreoberwasser': 'Lexfähre (Eider Oberwasser)',
    'nordfeldoberwasser': 'Nordfeld (Eider, Oberwasser)',
    'osteriffmpm': 'Osterriff (Elbe)',
    'pinnausperrwerkap': 'Pinnau-Speerwerk (Außenpegel)',
    'pinnausperrwerkbp': 'Pinnau-Speerwerk (Binnenpegel)',
    'reithrne': 'Reithörne (Hunte)',
    'robbensdsteert': 'Robbensüdsteert / Solthörn',
    'wangeroogenord': 'Wangerooge (Langes Riff, Nord)',
    'wangeroogewest': 'Wangerooge (Hafen)',
    'weserwehruw': 'Bremen-Weserwehr (Unterpegel)',
    'whvaltervorhafen': 'Wilhelmshaven (Alter Vorhafen)',
    'whvneuervorhafen': 'Wilhelmshaven (Neuer Vorhafen)',
    'wittorfop': 'Wittorf (Ilmenau Oberpegel)',
}


def extract_zip_key(filename):
    """Extract the station key from a Pegelonline ZIP filename.
    Example: 'pegelonline-bhvalterleuchtturm-W-20000101-20260123.zip' -> 'bhvalterleuchtturm'
    """
    basename = os.path.basename(filename)
    # Format: pegelonline-<key>-W-<daterange>.zip
    parts = basename.replace('.zip', '').split('-')
    if len(parts) >= 2:
        return parts[1].lower()
    return None


def fuzzy_match_station(zip_key, station_lookup, all_stations):
    """
    Match a ZIP file key to a station using fuzzy logic.
    Tries exact match, then substring matching, then best overlap.
    """
    # Check manual overrides first
    if zip_key in ZIP_KEY_OVERRIDES:
        override_name = ZIP_KEY_OVERRIDES[zip_key]
        for station in all_stations:
            if station['name'] == override_name:
                return station

    # Normalize the zip key first
    norm_zip = normalize_for_matching(zip_key)

    # 1. Direct lookup (normalized)
    if norm_zip in station_lookup:
        return station_lookup[norm_zip]

    # 2. Check if norm_zip is contained in any lookup key or vice versa
    best_match = None
    best_score = 0

    for norm_key, station in station_lookup.items():
        if norm_zip in norm_key or norm_key in norm_zip:
            # Score: prefer longest overlap, and penalize length difference
            overlap = min(len(norm_zip), len(norm_key))
            length_diff = abs(len(norm_zip) - len(norm_key))
            score = overlap * 10 - length_diff
            if score > best_score:
                best_score = score
                best_match = station

    if best_match and best_score >= 30:  # Minimum ~3 chars overlap
        return best_match

    # 3. Character-level similarity
    best_match = None
    best_ratio = 0

    for station in all_stations:
        norm_name = normalize_for_matching(station['name'])

        # Simple character overlap ratio
        common = sum(1 for c in norm_zip if c in norm_name)
        ratio = (2.0 * common) / (len(norm_zip) + len(norm_name)) if (len(norm_zip) + len(norm_name)) > 0 else 0

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = station

    if best_match and best_ratio >= 0.6:
        return best_match

    return None


def format_station_block(station_name, lat, lon, water, results, data):
    """Format a single station block in XTide harmonics format."""
    lines = []

    lines.append(f"# Harmonic constants derived from Pegelonline water level data")
    lines.append(f"# using UTide (v{utide.__version__}) with {data['n_obs']} observations from {data['start_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {results['r_squared']:.4f}, RMS error = {results['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {results['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# Water body: {water}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Germany")
    lines.append(f"# source: Derived from Pegelonline data with UTide harmonic analysis")
    lines.append(f"# restriction: Non-commercial use only")
    lines.append(f"# station_id_context: WSV")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: Mean Sea Level")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.4f}")
    lines.append(f"# !latitude: {lat:.4f}")

    lines.append(f"{station_name}, Germany")
    lines.append(f"+00:00 :Europe/Berlin")
    lines.append(f"{results['mean']:.4f} meters")

    for c in results['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def read_header_from_template(template_path):
    """Read header from template file up to (but not including) first station block.

    Includes everything through the second *END* marker plus generic comment
    lines that follow, but stops before station-specific comments (identified
    by 'derived' or 'BEGIN HOT COMMENTS' which belong to individual stations).
    """
    with open(template_path, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    header_lines = []
    end_count = 0
    after_second_end = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped == '*END*':
            end_count += 1
            header_lines.append(line.rstrip())
            if end_count >= 2:
                after_second_end = True
            continue

        if after_second_end:
            # Stop before station-specific comments
            if any(kw in stripped for kw in [
                'derived by', 'derived from', 'BEGIN HOT COMMENTS',
                'observations from', 'minut data',
            ]):
                break
            # Only keep comment lines (skip non-comment = station data)
            if stripped and not stripped.startswith('#'):
                break

        header_lines.append(line.rstrip())

    return '\n'.join(header_lines)


def main():
    water_levels_dir = Path("/home/oliver/water_levels/Germany")
    harmonics_ref = Path("/home/oliver/harmonics_working/harmonics_germany_2026-01-23.txt")
    template_path = Path("/home/oliver/harmonics_working/harmonics-dwf-20070318_no_us_no_dupes.txt")
    output_path = Path("/home/oliver/harmonics_working/harmonics_utide_germany_2026-01-27.txt")

    print("=" * 60)
    print("Generate Germany Harmonics with UTide")
    print("=" * 60)

    print(f"\nReading station info from {harmonics_ref.name}...")
    all_stations = extract_stations_from_harmonics(harmonics_ref)
    print(f"  Found {len(all_stations)} stations with coordinates")

    station_lookup = build_station_lookup(all_stations)
    print(f"  Built lookup with {len(station_lookup)} keys")

    print(f"\nReading header from {template_path.name}...")
    header = read_header_from_template(template_path)

    print("\nProcessing water level files...")
    zip_files = sorted(water_levels_dir.glob("*.zip"))
    zip_files = [f for f in zip_files if not str(f).endswith(':Zone.Identifier')]
    print(f"Found {len(zip_files)} ZIP files to process\n")

    # First pass: match all ZIP files to stations
    print("--- Fuzzy Matching ---")
    matched = []
    unmatched = []

    for zip_path in zip_files:
        zip_key = extract_zip_key(str(zip_path))
        if not zip_key:
            unmatched.append((zip_path, None))
            continue

        station_info = fuzzy_match_station(zip_key, station_lookup, all_stations)
        if station_info:
            matched.append((zip_path, station_info, zip_key))
        else:
            unmatched.append((zip_path, zip_key))

    print(f"  Matched: {len(matched)}, Unmatched: {len(unmatched)}")
    if unmatched:
        print("  Unmatched files:")
        for zp, key in unmatched:
            print(f"    {zp.name} (key: {key})")
    print()

    # Second pass: run UTide analysis
    print("--- UTide Analysis ---")
    station_blocks = []
    processed = 0
    failed = 0

    for i, (zip_path, station_info, zip_key) in enumerate(matched):
        station_name = station_info['name']
        lat = station_info['latitude']
        lon = station_info['longitude']
        water = station_info.get('water', 'Unknown')

        print(f"  [{i+1}/{len(matched)}] {station_name} (key: {zip_key})...", end='', flush=True)

        try:
            data = parse_json_water_levels(zip_path, sample_interval_minutes=60)
            if data is None:
                print(" FAILED (insufficient data)")
                failed += 1
                continue

            results = harmonic_analysis_utide(
                data['datetimes_utc'], data['levels'], lat
            )
            if results is None:
                print(" FAILED (analysis error)")
                failed += 1
                continue

            block = format_station_block(station_name, lat, lon, water, results, data)
            station_blocks.append(block)

            # Find M2 amplitude
            m2_amp = 0
            for c in results['constituents']:
                if c['name'] == 'M2':
                    m2_amp = c['amplitude']
                    break

            print(f" OK (R²={results['r_squared']:.3f}, M2={m2_amp:.3f}m, "
                  f"n={data['n_obs']}, constit={results['n_analyzed']})")
            processed += 1

        except Exception as e:
            print(f" FAILED ({e})")
            failed += 1
            continue

    print(f"\n{'='*60}")
    print(f"Processed: {processed}, Failed: {failed}")

    print(f"\nWriting output to {output_path}...")
    with open(output_path, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for block in station_blocks:
            f.write(block)
            f.write('\n')

    print(f"Done! Created {output_path}")
    print(f"Total stations: {len(station_blocks)}")


if __name__ == "__main__":
    main()
