#!/usr/bin/env python3
"""
Correct TICON-4 harmonics: filter, deduplicate, fix station names.

Pipeline:
  1. Filter: Remove stations with M2 < 0.01m (no real tides)
  2. Deduplicate: Keep best station per location (2km clusters)
  3. German WSV: Pegelonline API + manual map for proper names
  4. CMEMS lookup: Fix known concatenated CMEMS station names
  5. Reference match + Geonames + heuristic cleanup
"""

import re
import os
import sys
import time
import json
import math
import urllib.request
from pathlib import Path
from collections import defaultdict

INPUT_PATH = Path("/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide_edited.txt")

GEONAMES_USER = "oliver_k73"
MIN_M2_AMPLITUDE = 0.01  # meters
DEDUP_RADIUS_KM = 3.5
MAX_DIST_KM = 5.0  # for reference matching

# US + territories/associated states to exclude (already in other harmonics files)
US_COUNTRIES = {
    'United States', 'USA', 'US', 'Puerto Rico', 'PRI',
    'Guam', 'GUM', 'American Samoa', 'ASM',
    'U.S. Virgin Islands', 'VIR', 'USVI',
    'Northern Mariana Islands', 'MNP',
    'Marshall Islands',  # Compact of Free Association
    'Palau',             # Compact of Free Association
    'Micronesia',        # Compact of Free Association
}

# Reference harmonics files with proper station names
REF_FILES = [
    "/home/oliver/harmonics/classic/harmonics-dwf-20251228-free.txt",
    "/home/oliver/harmonics/classic/harmonics-dwf-20241229-free.txt",
    "/home/oliver/harmonics/classic/harmonics_old_no_us_no_dupes3.txt",
    "/home/oliver/harmonics/classic/harmonics_pierre_lavergne_v10_no_dupes4.txt",
    "/home/oliver/harmonics/classic/harmonics-dwf-20100529-nonfree.txt",
    "/home/oliver/harmonics/classic/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "/home/oliver/harmonics/classic/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "/home/oliver/harmonics/classic/harmonics_pierre_lavergne_v9_europe_no_us_no_dupes5.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_australia.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_france.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_denmark.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_netherlands.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_uk_bodc.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_ireland.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_germany_z0corrected.txt",
    "/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt",
    "/home/oliver/harmonics/ihm/harmonics_puertos_spain.txt",
]

# Manual fixes for German stations not in Pegelonline or with wrong names
GERMAN_MANUAL_MAP = {
    # WSV stations not in Pegelonline API
    '9610025': 'Schleimünde (Sperrwerk)',
    # BFG/CMEMS stations (matched by slug, not number)
    'luebecktg': 'Lübeck',
    'travemunde': 'Travemünde',
    'warnemunde': 'Warnemünde',
    'warnemuendetg': 'Warnemünde',
    'greifswaldtg': 'Greifswald',
    'greifswald_wiek': 'Greifswald-Wieck',
    'rostocktg': 'Rostock',
    'wismartg': 'Wismar',
    'schleswigtg': 'Schleswig',
    'schleimuendetg': 'Schleimünde',
    'neustadttg': 'Neustadt (Holstein)',
    'heiligenhafentg': 'Heiligenhafen',
    'kielholtenautg': 'Kiel-Holtenau',
    'kieltg': 'Kiel',
    'kalkgrundtg': 'Kalkgrund',
    'stpaulitg': 'Hamburg (St. Pauli)',
    'bremerhaventg': 'Bremerhaven',
    'cuxhaventg': 'Cuxhaven',
    'wilhelmshaventg': 'Wilhelmshaven',
    'eckernfoerdetg': 'Eckernförde',
    'barhoefttg': 'Barhöft',
    'stralsundtg': 'Stralsund',
}

# Known CMEMS concatenated names → proper names
CMEMS_NAME_MAP = {
    'goteborgagnesberg': 'Göteborg Agnesburg',
    'goteborgklippan': 'Göteborg Klippan',
    'goteborglarjeholm': 'Göteborg Lärjeholm',
    'goteborgorsh': 'Göteborg Orsholmen',
    'palmademallorca': 'Palma de Mallorca',
    'houtribsluizennoord': 'Houtribsluizen Noord',
    'krabbersgatsluizenzuid': 'Krabbersgat Sluizen Zuid',
    'roggebotsluisnoord': 'Roggebotsluis Noord',
    'roggebotsluiszuid': 'Roggebotsluis Zuid',
    'hvidesandekyst': 'Hvide Sande Kyst',
    'northcormorant': 'North Cormorant',
    'balisearouen': 'Balisea Rouen',
    'morlaixvigicrue': 'Morlaix Vigicrue',
    'ilesdusalut': 'Îles du Salut',
    'teignbridge': 'Teignbridge',
    'tallinnamadal': 'Tallinna Madal',
    'rossaveelpier': 'Rossaveel Pier',
    'castletownbere': 'Castletownbere',
    'hollandsebrugge': 'Hollandse Brug',
    'schellingwoude': 'Schellingwoude',
    'schiermonnikoog': 'Schiermonnikoog',
    'haringvlietsluizen': 'Haringvlietsluizen',
    'kornwerderzand': 'Kornwerderzand',
    'hellevoetsluis': 'Hellevoetsluis',
    'ijgeulstroompaal1': 'IJgeul Stroompaal 1',
    'torsmindekyst': 'Torsminde Kyst',
    'kapingamarangi': 'Kapingamarangi',
    'ittoqqortoormiit': 'Ittoqqortoormiit',
    'vishakhapatnam': 'Visakhapatnam',
    'strombolicchio': 'Strombolicchio',
    'frederikshavn': 'Frederikshavn',
    'karrebaeksminde': 'Karrebæksminde',
    'sjaellandsodde': 'Sjællands Odde',
    'kinlochbervie': 'Kinlochbervie',
    'marienleuchte': 'Marienleuchte',
    'heiligenhafen': 'Heiligenhafen',
    'minamitorishima': 'Minamitorishima',
    'niigatahigashi': 'Niigata Higashi',
    'tomakomaihigashiko': 'Tomakomai Higashiko',
}

# German abbreviations to keep uppercase in title case conversion
GERMAN_ABBREVS = {'MPM', 'AP', 'BP', 'UP', 'UF', 'OP', 'OW', 'UW', 'NOK', 'LT'}

# Common diacritics corrections for city names (ISO-8859-1 compatible)
DIACRITICS_MAP = {
    'Goteborg': 'Göteborg', 'Malmo': 'Malmö', 'Norrkoping': 'Norrköping',
    'Gavle': 'Gävle', 'Boras': 'Borås', 'Jonkoping': 'Jönköping',
    'Orebro': 'Örebro', 'Stromstad': 'Strömstad', 'Soderhamn': 'Söderhamn',
    'Kobenhavn': 'København', 'Aarhus': 'Århus',
    'Aalesund': 'Ålesund', 'Alesund': 'Ålesund', 'Bodo': 'Bodø',
    'Tromso': 'Tromsø', 'Vadso': 'Vadsø', 'Honefoss': 'Hønefoss',
    'Cadiz': 'Cádiz', 'Malaga': 'Málaga', 'Almeria': 'Almería',
    'Coruna': 'Coruña', 'Aviles': 'Avilés', 'Gijon': 'Gijón',
    'Alcudia': 'Alcúdia',
    'Lubeck': 'Lübeck', 'Belem': 'Belém',
    'Florianopolis': 'Florianópolis', 'Itajai': 'Itajaí',
    'Reunion': 'Réunion', 'Noumea': 'Nouméa', 'Setubal': 'Setúbal',
    'Gdansk': 'Gdańsk', 'Colon': 'Colón', 'Mazatlan': 'Mazatlán',
    'Valparaiso': 'Valparaíso', 'Maceio': 'Maceió',
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def encode_iso8859(text):
    """Convert text to ISO-8859-1, replacing unencodable chars."""
    try:
        text.encode('iso-8859-1')
        return text
    except UnicodeEncodeError:
        replacements = {
            'Ā': 'A', 'ā': 'a', 'Ă': 'A', 'ă': 'a', 'Đ': 'D', 'đ': 'd',
            'Ē': 'E', 'ē': 'e', 'Ī': 'I', 'ī': 'i', 'İ': 'I', 'ı': 'i',
            'Ō': 'O', 'ō': 'o', 'Ő': 'O', 'ő': 'o', 'Ş': 'S', 'ş': 's',
            'Ū': 'U', 'ū': 'u', 'Ű': 'U', 'ű': 'u', 'Ż': 'Z', 'ż': 'z',
            'Ł': 'L', 'ł': 'l', 'Ń': 'N', 'ń': 'n', 'Ś': 'S', 'ś': 's',
            'Ć': 'C', 'ć': 'c', 'Ę': 'E', 'ę': 'e', 'Ž': 'Z', 'ž': 'z',
            'Š': 'S', 'š': 's', 'Č': 'C', 'č': 'c', 'Ř': 'R', 'ř': 'r',
            'Ď': 'D', 'ď': 'd', 'Ť': 'T', 'ť': 't', 'Ů': 'U', 'ů': 'u',
            '\u2018': "'", '\u2019': "'", '\u2013': '-', '\u2014': '-',
            'ğ': 'g', 'Ğ': 'G',
        }
        return ''.join(replacements.get(ch, ch if ord(ch) < 256 else '?') for ch in text)


def normalize_for_compare(name):
    """Normalize name for comparison: lowercase, strip suffixes/IDs."""
    n = name.lower().strip()
    if ',' in n:
        n = n.split(',')[0].strip()
    # Strip common suffixes
    n = re.sub(r'\s*tg$', '', n)
    n = re.sub(r'\s*\d{3}[a-z]?\s*$', '', n)
    n = re.sub(r'\s*[a-z]{2}\d{2}\s*$', '', n)
    n = n.replace('_', ' ').replace('-', ' ')
    # Remove non-alphanumeric
    n = re.sub(r'[^a-z0-9 ]', '', n)
    return n.strip()


def name_similarity(name1, name2):
    """Compute character-level similarity between two names (0-1)."""
    a = normalize_for_compare(name1)
    b = normalize_for_compare(name2)
    if not a or not b:
        return 0
    # Use longest common subsequence ratio
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return len(shorter) / len(longer)
    common = sum(1 for c in shorter if c in longer)
    return common / max(len(shorter), len(longer))


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------

def parse_ticon4_blocks(text):
    """Parse TICON-4 harmonics file into header + station blocks."""
    lines = text.split('\n')
    first_station_idx = None
    for i, line in enumerate(lines):
        if line.startswith('# Harmonic constants from TICON-4'):
            first_station_idx = i
            break
    if first_station_idx is None:
        print("FEHLER: Keine Stationsblöcke gefunden!")
        sys.exit(1)

    header_lines = lines[:first_station_idx]
    blocks = []
    current_block = []
    for line in lines[first_station_idx:]:
        if line.startswith('# Harmonic constants from TICON-4') and current_block:
            blocks.append(current_block)
            current_block = []
        current_block.append(line)
    if current_block:
        blocks.append(current_block)
    return header_lines, blocks


def extract_block_info(block_lines):
    """Extract metadata from a station block."""
    lat = lon = m2_amp = None
    name_line = None
    name_line_idx = None
    country = station_id = quality = None
    years = obs_count = 0

    for i, line in enumerate(block_lines):
        if line.startswith('# !latitude:'):
            try: lat = float(line.split(':', 1)[1].strip())
            except: pass
        elif line.startswith('# !longitude:'):
            try: lon = float(line.split(':', 1)[1].strip())
            except: pass
        elif line.startswith('# country:'):
            country = line.split(':', 1)[1].strip()
        elif line.startswith('# station_id_context:'):
            station_id = line.split(':', 1)[1].strip()
        elif '# Quality:' in line or 'Quality:' in line:
            quality = line.split('Quality:', 1)[1].strip() if 'Quality:' in line else ''
        elif 'observations over' in line:
            m = re.search(r'(\d+)\s+observations over\s+(\d+)\s+years', line)
            if m:
                obs_count = int(m.group(1))
                years = int(m.group(2))
        elif line.startswith('M2 ') and m2_amp is None:
            parts = line.split()
            if len(parts) >= 2:
                try: m2_amp = float(parts[1])
                except: pass
        elif (not line.startswith('#') and not line.startswith('x ')
              and ',' in line and name_line is None):
            parts = line.strip().split(',')
            if len(parts) >= 2 and not re.match(r'^[\d.]+$', parts[0].strip()):
                name_line = line.strip()
                name_line_idx = i

    return {
        'lat': lat, 'lon': lon, 'm2_amp': m2_amp,
        'name_line': name_line, 'name_line_idx': name_line_idx,
        'country': country, 'station_id': station_id or '',
        'quality': quality or '', 'years': years, 'obs_count': obs_count,
    }


def fetch_pegelonline_names():
    """Fetch proper German station names from Pegelonline API."""
    url = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"   WARNUNG: Pegelonline API nicht erreichbar: {e}")
        return {}

    mapping = {}
    for s in data:
        number = s.get('number', '')
        name = s.get('longname', s.get('shortname', ''))
        water = s.get('water', {}).get('longname', '')
        if number and name:
            # Convert UPPERCASE to proper case
            proper = pegelonline_to_proper_name(name, water)
            mapping[number] = proper
    return mapping


def pegelonline_to_proper_name(name, water=''):
    """Convert Pegelonline UPPERCASE name to proper Title Case."""
    # Split into words and convert
    words = name.split()
    result = []
    for w in words:
        if w in GERMAN_ABBREVS:
            result.append(w)
        elif w.startswith('(') and w[1:] in GERMAN_ABBREVS:
            result.append(w)
        elif w.endswith(')') and w[:-1] in GERMAN_ABBREVS:
            result.append(w)
        else:
            result.append(w.title())
    proper = ' '.join(result)

    # Fix common title case issues for German prepositions/articles
    for wrong, right in [(' Auf ', ' auf '), (' Und ', ' und '), (' Der ', ' der '),
                         (' Die ', ' die '), (' Das ', ' das '), (' Von ', ' von '),
                         (' Am ', ' am '), (' An ', ' an '), (' Im ', ' im '),
                         (' In ', ' in '), (' Zur ', ' zur '), (' Zum ', ' zum ')]:
        proper = proper.replace(wrong, right)

    # Known abbreviation expansions
    proper = proper.replace('Bhv ', 'Bremerhaven ')
    proper = proper.replace('Whv ', 'Wilhelmshaven ')

    # Add water body in parentheses if not already in name
    if water and water not in ('', 'NORDSEE', 'OSTSEE'):
        water_proper = water.title()
        # Fix title case for water body too
        for wrong, right in [(' Und ', ' und '), (' Der ', ' der ')]:
            water_proper = water_proper.replace(wrong, right)
        # Don't add if water name is already part of station name
        if water_proper.lower() not in proper.lower():
            proper = f"{proper} ({water_proper})"

    return proper


def extract_reference_stations():
    """Extract station names with coordinates from reference files."""
    stations = {}
    for fpath in REF_FILES:
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='iso-8859-1') as f:
                text = f.read()
        except Exception:
            continue
        lat = lon = None
        count = 0
        for line in text.split('\n'):
            if line.startswith('# !latitude:'):
                try: lat = float(line.split(':', 1)[1].strip())
                except: lat = None
            elif line.startswith('# !longitude:'):
                try: lon = float(line.split(':', 1)[1].strip())
                except: lon = None
            elif (lat is not None and lon is not None
                  and not line.startswith('#') and not line.startswith('x ') and ',' in line):
                name = line.strip()
                if name and len(name) > 2:
                    key = (round(lat, 2), round(lon, 2))
                    if key not in stations or any(ord(c) > 127 for c in name):
                        stations[key] = {'name': name, 'lat': lat, 'lon': lon}
                    count += 1
                lat = lon = None
        print(f"  {Path(fpath).name}: {count} Stationen")
    return stations


def find_best_ref_match(lat, lon, ticon_name, ref_stations):
    """Find matching reference station by coordinates + name similarity."""
    best = None
    best_dist = MAX_DIST_KM + 1

    for dlat_i in range(-5, 6):
        for dlon_i in range(-5, 6):
            key = (round(lat + dlat_i * 0.01, 2), round(lon + dlon_i * 0.01, 2))
            if key in ref_stations:
                ref = ref_stations[key]
                dist = haversine_km(lat, lon, ref['lat'], ref['lon'])
                if dist < best_dist:
                    best_dist = dist
                    best = ref

    if best is not None and best_dist <= MAX_DIST_KM:
        # Verify name similarity to avoid false matches
        sim = name_similarity(ticon_name, best['name'])
        if sim < 0.25:
            return None, None
        name = best['name']
        name = re.sub(r'\s*-\s*READ\s+flaterco\.com/pol\.html\s*', '', name)
        return {'name': name, 'lat': best['lat'], 'lon': best['lon']}, best_dist
    return None, None


def query_geonames(lat, lon, radius_km=5):
    """Query geonames.org API for nearest place name."""
    url = (f"http://api.geonames.org/findNearbyPlaceNameJSON?"
           f"lat={lat}&lng={lon}&radius={radius_km}&maxRows=1"
           f"&username={GEONAMES_USER}&style=FULL")
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if 'geonames' in data and data['geonames']:
            place = data['geonames'][0]
            return {
                'name': place.get('name', ''),
                'country': place.get('countryName', ''),
                'distance': float(place.get('distance', 0)),
            }
    except Exception:
        pass
    return None


def improve_name_from_geonames(cleaned_name, country, geo_result):
    """Use geonames to improve station name (add diacritics)."""
    if not geo_result:
        return None
    geo_name = geo_result['name']
    dist = geo_result['distance']
    orig_norm = normalize_for_compare(cleaned_name)
    geo_norm = normalize_for_compare(geo_name)

    # Same name → use geonames version (may have diacritics)
    if orig_norm == geo_norm:
        return f"{geo_name}, {country}"
    # Starts with same → use if close
    if (geo_norm.startswith(orig_norm) or orig_norm.startswith(geo_norm)) and dist < 1.0:
        return f"{geo_name}, {country}"
    # Very close and high char overlap
    if dist < 0.5:
        common = sum(1 for a, b in zip(orig_norm, geo_norm) if a == b)
        if common >= min(len(orig_norm), len(geo_norm)) * 0.7:
            return f"{geo_name}, {country}"
    return None


def clean_suffix(name):
    """Remove TICON-4 technical suffixes from station name."""
    cleaned = name
    # Trailing IDs: "347A", "080A", "316C"
    cleaned = re.sub(r'\s+\d{3}[A-Za-z]?\s*$', '', cleaned)
    # Sensor codes: "Ma02", "Gs01", "Hd25"
    cleaned = re.sub(r'\s+[A-Z][a-z]\d{2}\s*$', '', cleaned)
    # "Tg" suffix
    cleaned = re.sub(r'[Tt]g$', '', cleaned).strip()
    # "Uscgs", "Ridi"
    cleaned = re.sub(r'\s+(?:Uscgs|Ridi)\s*$', '', cleaned, flags=re.IGNORECASE)
    # Short technical trailing codes (Alge, Alio, Sjov, etc.)
    cleaned = re.sub(r'\s+[A-Z][a-z]{2,4}(?:pfm|fpfm)?\s*$', '', cleaned)
    # Timing suffixes: "05Minute", "60Minute", "10Minute"
    cleaned = re.sub(r'\s*\d+[Mm]inute\s*$', '', cleaned)
    # Trailing duplicate number: "Coruna2", "Fuerteventura3"
    cleaned = re.sub(r'(\w[a-z])\d+$', r'\1', cleaned)
    return cleaned.strip()


def split_compound_name(name):
    """Split concatenated multi-word station names."""
    if ' ' in name or '-' in name or len(name) <= 10:
        return name

    low = name.lower()

    # Try CMEMS lookup first
    if low in CMEMS_NAME_MAP:
        return CMEMS_NAME_MAP[low]

    # Language-specific compound suffixes to split on
    suffixes = {
        # German
        'hafen': ' Hafen', 'sperrwerk': '-Sperrwerk', 'leuchtturm': ' Leuchtturm',
        'reede': ' Reede', 'schleuse': ' Schleuse', 'binnenhafen': ' Binnenhafen',
        'vorhafen': ' Vorhafen', 'südhafen': ' Südhafen', 'anleger': ' Anleger',
        'mündung': ' Mündung', 'plate': 'plate',
        # Dutch
        'sluizen': ' Sluizen', 'haven': ' Haven', 'polder': ' Polder',
        'buiten': ' Buiten', 'binnen': ' Binnen',
        'noord': ' Noord', 'zuid': ' Zuid', 'oost': ' Oost', 'west': ' West',
        # English
        'harbour': ' Harbour', 'harbor': ' Harbor', 'island': ' Island',
        'point': ' Point', 'bridge': ' Bridge', 'pier': ' Pier',
        # Danish/Swedish
        'havn': ' Havn', 'hamn': ' Hamn', 'kyst': ' Kyst',
    }

    for suffix, replacement in sorted(suffixes.items(), key=lambda x: -len(x[0])):
        if low.endswith(suffix) and len(name) > len(suffix) + 3:
            prefix = name[:-len(suffix)]
            if replacement.startswith(' ') or replacement.startswith('-'):
                return prefix + replacement
            else:
                return name  # No split needed (like 'plate')

    return name


def apply_diacritics(name):
    """Apply diacritics from dictionary."""
    for plain, accented in DIACRITICS_MAP.items():
        if plain.lower() in name.lower():
            pattern = re.compile(re.escape(plain), re.IGNORECASE)
            name = pattern.sub(accented, name)
    return name


def score_station(info):
    """Score a station for deduplication (higher = better)."""
    score = 0
    if 'No obvious' in info['quality']:
        score += 30
    elif 'Possible datum issues' == info['quality']:
        score += 10
    # Prefer longer observation
    score += min(info['years'], 30)
    # Prefer national services over aggregators
    sid = info['station_id']
    if any(src in sid for src in ['-wsv', '-bfg', '-refmar', '-smhi', '-bodc',
                                   '-bom', '-rws', '-noaa', '-dmi']):
        score += 10
    elif '-cmems' in sid:
        score += 2
    elif '-uhslc' in sid:
        score += 5
    return score


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("TICON-4 Stationsnamen korrigieren, filtern, deduplizieren")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # Load input
    # -----------------------------------------------------------------------
    print("\n0. Eingabe lesen...")
    with open(INPUT_PATH, 'r', encoding='iso-8859-1') as f:
        text = f.read()
    header_lines, blocks = parse_ticon4_blocks(text)
    print(f"   {len(blocks)} Stationsblöcke")

    # Extract info for all blocks
    all_info = [extract_block_info(b) for b in blocks]

    # -----------------------------------------------------------------------
    # Phase 1: Filter M2 < 0.01m
    # -----------------------------------------------------------------------
    print(f"\n1. Filter: M2 < {MIN_M2_AMPLITUDE}m + US-Stationen entfernen...")
    keep_mask = []
    filtered_m2 = 0
    filtered_us = 0
    for info in all_info:
        if info['country'] in US_COUNTRIES:
            keep_mask.append(False)
            filtered_us += 1
        elif info['m2_amp'] is not None and info['m2_amp'] < MIN_M2_AMPLITUDE:
            keep_mask.append(False)
            filtered_m2 += 1
        else:
            keep_mask.append(True)

    blocks = [b for b, keep in zip(blocks, keep_mask) if keep]
    all_info = [i for i, keep in zip(all_info, keep_mask) if keep]
    print(f"   {filtered_us} US-Stationen entfernt")
    print(f"   {filtered_m2} Stationen mit M2 < {MIN_M2_AMPLITUDE}m entfernt")
    print(f"   {len(blocks)} übrig")

    # -----------------------------------------------------------------------
    # Phase 2: Deduplicate (2km clusters, keep best)
    # -----------------------------------------------------------------------
    print(f"\n2. Deduplizierung ({DEDUP_RADIUS_KM}km Radius)...")

    # Build clusters using simple grid
    grid = defaultdict(list)
    for idx, info in enumerate(all_info):
        if info['lat'] is not None and info['lon'] is not None:
            key = (round(info['lat'], 1), round(info['lon'], 1))
            grid[key].append(idx)

    # Find duplicates within clusters
    dedup_remove = set()
    cluster_count = 0
    for key, indices in grid.items():
        if len(indices) < 2:
            continue
        # Compare all pairs
        clusters_local = []
        assigned = set()
        for i, idx_a in enumerate(indices):
            if idx_a in assigned:
                continue
            cluster = [idx_a]
            assigned.add(idx_a)
            for idx_b in indices[i + 1:]:
                if idx_b in assigned:
                    continue
                dist = haversine_km(
                    all_info[idx_a]['lat'], all_info[idx_a]['lon'],
                    all_info[idx_b]['lat'], all_info[idx_b]['lon'])
                if dist <= DEDUP_RADIUS_KM:
                    # Check if genuinely different stations
                    name_a = normalize_for_compare(all_info[idx_a]['name_line'] or '')
                    name_b = normalize_for_compare(all_info[idx_b]['name_line'] or '')
                    sim = name_similarity(all_info[idx_a]['name_line'] or '',
                                          all_info[idx_b]['name_line'] or '')
                    if sim > 0.4:  # Similar enough → duplicate
                        cluster.append(idx_b)
                        assigned.add(idx_b)
            if len(cluster) > 1:
                clusters_local.append(cluster)

        for cluster in clusters_local:
            cluster_count += 1
            # Score each station, keep the best
            scored = [(score_station(all_info[idx]), idx) for idx in cluster]
            scored.sort(reverse=True)
            # Remove all but the best
            for _, idx in scored[1:]:
                dedup_remove.add(idx)

    blocks = [b for i, b in enumerate(blocks) if i not in dedup_remove]
    all_info = [info for i, info in enumerate(all_info) if i not in dedup_remove]
    print(f"   {len(dedup_remove)} Duplikate entfernt aus {cluster_count} Clustern")
    print(f"   {len(blocks)} Stationen übrig")

    # -----------------------------------------------------------------------
    # Phase 3: German WSV names from Pegelonline API
    # -----------------------------------------------------------------------
    print(f"\n3. Deutsche WSV-Stationen (Pegelonline-API)...")
    pegelonline = fetch_pegelonline_names()
    print(f"   {len(pegelonline)} Pegelonline-Stationen geladen")

    wsv_matched = 0
    for bi, (block, info) in enumerate(zip(blocks, all_info)):
        sid = info['station_id']
        if not sid:
            continue
        parts = sid.split('-')
        country_code = parts[-2] if len(parts) >= 4 else ''
        source = parts[-1] if len(parts) >= 4 else ''
        slug = parts[0] if parts else ''

        if country_code != 'deu':
            continue

        proper_name = None

        # Try manual map by slug first (highest priority)
        if slug in GERMAN_MANUAL_MAP:
            proper_name = GERMAN_MANUAL_MAP[slug]

        # Try WSV Pegelonline by station number
        elif source == 'wsv' and len(parts) >= 3:
            number = parts[-3] if parts[-3].isdigit() else None
            if number:
                # Check manual map by number first
                if number in GERMAN_MANUAL_MAP:
                    proper_name = GERMAN_MANUAL_MAP[number]
                elif number in pegelonline:
                    proper_name = pegelonline[number]

        if proper_name:
            new_name_line = f"{proper_name}, Germany"
            new_name_line = encode_iso8859(new_name_line)
            idx = info['name_line_idx']
            if idx is not None:
                block[idx] = new_name_line
                wsv_matched += 1

    print(f"   {wsv_matched} deutsche Stationen korrigiert")

    # -----------------------------------------------------------------------
    # Phase 4: CMEMS concatenated names
    # -----------------------------------------------------------------------
    print(f"\n4. CMEMS-Stationsnamen korrigieren...")
    cmems_matched = 0
    for bi, (block, info) in enumerate(zip(blocks, all_info)):
        sid = info['station_id']
        if not sid or '-cmems' not in sid:
            continue
        # Extract slug from ID like "goteborgagnesberg-got-swe-cmems"
        slug = sid.split('-')[0]
        # Remove trailing "tg" from slug
        slug_clean = re.sub(r'tg$', '', slug)
        # Also remove timing suffixes
        slug_clean = re.sub(r'_?\d+minute$', '', slug_clean)

        if slug_clean in CMEMS_NAME_MAP:
            proper = CMEMS_NAME_MAP[slug_clean]
            country = info['country'] or ''
            new_line = f"{proper}, {country}"
            new_line = encode_iso8859(new_line)
            idx = info['name_line_idx']
            if idx is not None:
                block[idx] = new_line
                cmems_matched += 1

    print(f"   {cmems_matched} CMEMS-Stationen korrigiert")

    # -----------------------------------------------------------------------
    # Phase 5: Reference match + Geonames + heuristic cleanup
    # -----------------------------------------------------------------------
    print(f"\n5. Referenz-Abgleich + Geonames + Heuristik...")
    ref_stations = extract_reference_stations()
    print(f"   {len(ref_stations)} Referenz-Stationen")

    ref_matched = 0
    geo_matched = 0
    heur_matched = 0
    unchanged = 0
    geo_cache = {}

    for bi, (block, info) in enumerate(zip(blocks, all_info)):
        if info['lat'] is None or info['lon'] is None or info['name_line'] is None:
            unchanged += 1
            continue

        idx = info['name_line_idx']
        old_name = block[idx]  # May already be updated by phase 3/4
        country = info['country'] or ''

        # Skip if already corrected by phase 3/4 (check if name changed)
        if old_name != info['name_line']:
            continue

        lat, lon = info['lat'], info['lon']

        # 5a: Reference match with name similarity check
        ref, dist = find_best_ref_match(lat, lon, old_name, ref_stations)
        if ref is not None:
            new_name = ref['name']
            if new_name != old_name:
                block[idx] = new_name
                ref_matched += 1
            else:
                unchanged += 1
            continue

        # 5b: Clean up name
        name_part = old_name.split(',')[0].strip()
        country_part = old_name.split(',', 1)[1].strip() if ',' in old_name else country

        cleaned = clean_suffix(name_part)
        cleaned = split_compound_name(cleaned)
        if cleaned.isupper() or cleaned.islower():
            cleaned = cleaned.title()
        cleaned = apply_diacritics(cleaned)

        # 5c: Geonames API
        cache_key = (round(lat, 3), round(lon, 3))
        if cache_key not in geo_cache:
            geo_result = query_geonames(lat, lon, radius_km=5)
            geo_cache[cache_key] = geo_result
            time.sleep(0.4)
        else:
            geo_result = geo_cache[cache_key]

        if geo_result:
            improved = improve_name_from_geonames(cleaned, country_part, geo_result)
            if improved:
                improved = encode_iso8859(improved)
                if improved != old_name:
                    block[idx] = improved
                    geo_matched += 1
                    continue

        new_name = f"{cleaned}, {country_part}"
        new_name = encode_iso8859(new_name)

        if new_name != old_name:
            block[idx] = new_name
            heur_matched += 1
        else:
            unchanged += 1

        if (bi + 1) % 200 == 0:
            print(f"   [{bi+1}/{len(blocks)}] ref={ref_matched} geo={geo_matched} heur={heur_matched}")

    print(f"\n   Referenz-Match:  {ref_matched}")
    print(f"   Geonames-Match:  {geo_matched}")
    print(f"   Heuristik:       {heur_matched}")
    print(f"   Unverändert:     {unchanged}")

    # -----------------------------------------------------------------------
    # Write output
    # -----------------------------------------------------------------------
    print(f"\n6. Schreibe {OUTPUT_PATH.name}...")
    with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(header_lines))
        f.write('\n')
        for block in blocks:
            f.write('\n'.join(block))
            f.write('\n')

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"   {len(blocks)} Stationen, {size_kb:.0f} KB")

    # -----------------------------------------------------------------------
    # Summary: show some corrections
    # -----------------------------------------------------------------------
    print(f"\n7. Beispiele:")
    with open(INPUT_PATH, 'r', encoding='iso-8859-1') as f:
        old_names = re.findall(r'^(?!#)(?!x )(?!\+)(?!\d)(.+,.+)$', f.read(), re.MULTILINE)
    with open(OUTPUT_PATH, 'r', encoding='iso-8859-1') as f:
        new_names = re.findall(r'^(?!#)(?!x )(?!\+)(?!\d)(.+,.+)$', f.read(), re.MULTILINE)

    # Show German corrections
    print(f"  === Deutsche Stationen ===")
    shown = 0
    new_set = set(new_names)
    for n in sorted(new_set):
        if n.endswith(', Germany') and shown < 30:
            print(f"  {n}")
            shown += 1

    # Show diacritics corrections
    print(f"\n  === Sonderzeichen-Korrekturen ===")
    old_set = set(old_names)
    shown = 0
    for n in sorted(new_set - old_set):
        if any(ord(c) > 127 for c in n) and shown < 20:
            print(f"  {n}")
            shown += 1


if __name__ == '__main__':
    main()
