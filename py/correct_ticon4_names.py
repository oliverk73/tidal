#!/usr/bin/env python3
"""
Correct station names in TICON-4 harmonics file:
1. Match against reference harmonics files by coordinate proximity (~2km)
2. Use geonames.org API for unmatched stations
3. Apply proper diacritics and country-specific characters
4. Save as harmonics_ticon4_worldwide_edited.txt (ISO-8859-1)
"""

import re
import os
import sys
import time
import json
import math
import urllib.request
import urllib.parse
from pathlib import Path

INPUT_PATH = Path("/home/oliver/harmonics_working/harmonics_ticon4_worldwide.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics_working/harmonics_ticon4_worldwide_edited.txt")

GEONAMES_USER = "oliver_k73"

# Reference harmonics files with proper station names
REF_FILES = [
    "/home/oliver/harmonics/harmonics-dwf-20251228-free.txt",
    "/home/oliver/harmonics_edited/harmonics-dwf-20241229-free.txt",
    "/home/oliver/harmonics_edited/harmonics_old_no_us_no_dupes3.txt",
    "/home/oliver/harmonics_edited/harmonics_pierre_lavergne_v10_no_dupes4.txt",
    "/home/oliver/harmonics_edited/harmonics-dwf-20100529-nonfree.txt",
    "/home/oliver/harmonics_edited/harmonics-dwf-20070318_no_us_no_dupes.txt",
    "/home/oliver/harmonics_edited/harmonics-2004-06-14_no_us_no_dupes2.txt",
    "/home/oliver/harmonics_edited/harmonics_pierre_lavergne_v9_europe_no_us_no_dupes5.txt",
    # UTide output files
    "/home/oliver/harmonics_working/harmonics_utide_australia.txt",
    "/home/oliver/harmonics_working/harmonics_utide_france.txt",
    "/home/oliver/harmonics_working/harmonics_utide_denmark.txt",
    "/home/oliver/harmonics_working/harmonics_utide_netherlands.txt",
    "/home/oliver/harmonics_working/harmonics_utide_uk_bodc.txt",
    "/home/oliver/harmonics_working/harmonics_utide_ireland.txt",
    "/home/oliver/harmonics_working/harmonics_utide_germany_z0corrected.txt",
    "/home/oliver/harmonics_working/harmonics_utide_canada_all.txt",
    "/home/oliver/harmonics_working/harmonics_puertos_spain.txt",
]

# Distance threshold in km for coordinate matching
MAX_DIST_KM = 5.0

# Common diacritics corrections for city names (ISO-8859-1 compatible)
DIACRITICS_MAP = {
    'Goteborg': 'Göteborg', 'Malmo': 'Malmö', 'Norrkoping': 'Norrköping',
    'Helsingborg': 'Helsingborg', 'Gavle': 'Gävle', 'Boras': 'Borås',
    'Jonkoping': 'Jönköping', 'Orebro': 'Örebro', 'Norrkoping': 'Norrköping',
    'Stromstad': 'Strömstad', 'Sundsvall': 'Sundsvall', 'Soderhamn': 'Söderhamn',
    'Kobenhavn': 'København', 'Aarhus': 'Århus', 'Aalborg': 'Aalborg',
    'Aalesund': 'Ålesund', 'Bodo': 'Bodø', 'Tromso': 'Tromsø',
    'Alesund': 'Ålesund', 'Vadso': 'Vadsø', 'Roros': 'Røros',
    'Longyearbyen': 'Longyearbyen', 'Honefoss': 'Hønefoss',
    'Cadiz': 'Cádiz', 'Malaga': 'Málaga', 'Almeria': 'Almería',
    'Coruna': 'Coruña', 'Aviles': 'Avilés', 'Gijon': 'Gijón',
    'Alcudia': 'Alcúdia', 'Algeciras': 'Algeciras', 'Bilbao': 'Bilbao',
    'Santander': 'Santander', 'Tarifa': 'Tarifa', 'Sevilla': 'Sevilla',
    'Huelva': 'Huelva', 'Arrecife': 'Arrecife', 'Tenerife': 'Tenerife',
    'Dusseldorf': 'Düsseldorf', 'Munchen': 'München', 'Koln': 'Köln',
    'Nurnberg': 'Nürnberg', 'Lubeck': 'Lübeck', 'Wurzburg': 'Würzburg',
    'Belem': 'Belém', 'Sao': 'São', 'Fortaleza': 'Fortaleza',
    'Florianopolis': 'Florianópolis', 'Itajai': 'Itajaí',
    'Reunion': 'Réunion', 'Noumea': 'Nouméa', 'Setubal': 'Setúbal',
    'Funchal': 'Funchal', 'Acores': 'Açores',
    'Djibouti': 'Djibouti', 'Dakar': 'Dakar',
    'Gdansk': 'Gdańsk', 'Swinoujscie': 'Świnoujście',
    'Dubrovnik': 'Dubrovnik', 'Rijeka': 'Rijeka',
    'Naha': 'Naha', 'Kushiro': 'Kushiro',
    'Belize': 'Belize', 'Colon': 'Colón', 'Panama': 'Panamá',
    'Veracruz': 'Veracruz', 'Mazatlan': 'Mazatlán', 'Acapulco': 'Acapulco',
    'Valparaiso': 'Valparaíso', 'Callao': 'Callao',
    'Recife': 'Recife', 'Maceio': 'Maceió',
    'Zurich': 'Zürich', 'Geneve': 'Genève',
    'Angra': 'Angra', 'Faial': 'Faial',
    'Ponta Delgada': 'Ponta Delgada',
}


def haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def extract_reference_stations():
    """Extract station names with coordinates from all reference files."""
    stations = {}  # (round_lat, round_lon) -> {'name': ..., 'lat': ..., 'lon': ...}

    for fpath in REF_FILES:
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='iso-8859-1') as f:
                text = f.read()
        except Exception as e:
            print(f"  Fehler beim Lesen von {fpath}: {e}")
            continue

        lat = lon = None
        count = 0
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('# !latitude:'):
                try:
                    lat = float(line.split(':', 1)[1].strip())
                except ValueError:
                    lat = None
            elif line.startswith('# !longitude:'):
                try:
                    lon = float(line.split(':', 1)[1].strip())
                except ValueError:
                    lon = None
            elif lat is not None and lon is not None and not line.startswith('#') and not line.startswith('x ') and ',' in line:
                name = line.strip()
                if name and len(name) > 2:
                    key = (round(lat, 2), round(lon, 2))
                    # Prefer names with diacritics over plain ASCII
                    if key not in stations or any(ord(c) > 127 for c in name):
                        stations[key] = {'name': name, 'lat': lat, 'lon': lon}
                    count += 1
                lat = lon = None

        print(f"  {Path(fpath).name}: {count} Stationen")

    return stations


def normalize_name(name):
    """Normalize a name for comparison (lowercase, no punctuation, no suffixes)."""
    n = name.lower().strip()
    # Remove country suffix after comma
    if ',' in n:
        n = n.split(',')[0].strip()
    # Remove common suffixes
    for suffix in ['tg', ' tg', '_tg', ' a', ' b', ' c']:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()
    # Remove numeric IDs
    n = re.sub(r'\s*\d{3}[a-z]?\s*$', '', n)
    n = re.sub(r'\s*[a-z]{2}\d{2}\s*$', '', n)
    # Replace underscores with spaces
    n = n.replace('_', ' ')
    return n.strip()


def find_best_ref_match(lat, lon, name, ref_stations):
    """Find the best matching reference station by coordinates and name."""
    best = None
    best_dist = MAX_DIST_KM + 1

    # Quick search using rounded coordinates (0.05° ≈ 5.5km)
    for dlat in [-0.05, -0.04, -0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03, 0.04, 0.05]:
        for dlon in [-0.05, -0.04, -0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03, 0.04, 0.05]:
            key = (round(lat + dlat, 2), round(lon + dlon, 2))
            if key in ref_stations:
                ref = ref_stations[key]
                dist = haversine_km(lat, lon, ref['lat'], ref['lon'])
                if dist < best_dist:
                    best_dist = dist
                    best = ref

    if best is not None and best_dist <= MAX_DIST_KM:
        # Clean up reference name: remove "- READ flaterco.com/pol.html" suffix
        name = best['name']
        name = re.sub(r'\s*-\s*READ\s+flaterco\.com/pol\.html\s*', '', name)
        best = dict(best, name=name)
        return best, best_dist
    return None, None


def query_geonames(lat, lon, radius_km=2):
    """Query geonames.org API for nearest place name."""
    url = (f"http://api.geonames.org/findNearbyPlaceNameJSON?"
           f"lat={lat}&lng={lon}&radius={radius_km}&maxRows=1"
           f"&username={GEONAMES_USER}&style=FULL")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if 'geonames' in data and data['geonames']:
            place = data['geonames'][0]
            return {
                'name': place.get('name', ''),
                'country': place.get('countryName', ''),
                'lat': float(place.get('lat', lat)),
                'lon': float(place.get('lng', lon)),
                'distance': float(place.get('distance', 0)),
                'fcode': place.get('fcode', ''),
            }
    except Exception as e:
        pass
    return None


def encode_iso8859(text):
    """Convert text to ISO-8859-1, replacing unencodable chars."""
    try:
        text.encode('iso-8859-1')
        return text
    except UnicodeEncodeError:
        result = []
        for ch in text:
            try:
                ch.encode('iso-8859-1')
                result.append(ch)
            except UnicodeEncodeError:
                # Common replacements for non-ISO-8859-1 chars
                replacements = {
                    '\u0100': 'A', '\u0101': 'a',  # Ā ā
                    '\u0102': 'A', '\u0103': 'a',  # Ă ă
                    '\u0110': 'D', '\u0111': 'd',  # Đ đ
                    '\u0112': 'E', '\u0113': 'e',  # Ē ē
                    '\u012a': 'I', '\u012b': 'i',  # Ī ī
                    '\u0130': 'I', '\u0131': 'i',  # İ ı
                    '\u014c': 'O', '\u014d': 'o',  # Ō ō
                    '\u0150': 'O', '\u0151': 'o',  # Ő ő
                    '\u015e': 'S', '\u015f': 's',  # Ş ş
                    '\u016a': 'U', '\u016b': 'u',  # Ū ū
                    '\u0170': 'U', '\u0171': 'u',  # Ű ű
                    '\u017b': 'Z', '\u017c': 'z',  # Ż ż
                    '\u0141': 'L', '\u0142': 'l',  # Ł ł
                    '\u0143': 'N', '\u0144': 'n',  # Ń ń
                    '\u015a': 'S', '\u015b': 's',  # Ś ś
                    '\u0106': 'C', '\u0107': 'c',  # Ć ć
                    '\u0118': 'E', '\u0119': 'e',  # Ę ę
                    '\u017d': 'Z', '\u017e': 'z',  # Ž ž
                    '\u0160': 'S', '\u0161': 's',  # Š š
                    '\u010c': 'C', '\u010d': 'c',  # Č č
                    '\u0158': 'R', '\u0159': 'r',  # Ř ř
                    '\u010e': 'D', '\u010f': 'd',  # Ď ď
                    '\u0164': 'T', '\u0165': 't',  # Ť ť
                    '\u016e': 'U', '\u016f': 'u',  # Ů ů
                    '\u2018': "'", '\u2019': "'",   # ' '
                    '\u201c': '"', '\u201d': '"',   # " "
                    '\u2013': '-', '\u2014': '-',   # – —
                    '\u0327': '',                    # cedilla combining
                }
                result.append(replacements.get(ch, '?'))
        return ''.join(result)


def parse_ticon4_blocks(text):
    """Parse TICON-4 harmonics file into header + station blocks."""
    lines = text.split('\n')

    # Find where header ends and first station begins
    # Stations start with "# Harmonic constants derived from TICON-4" or similar comment blocks
    # The header contains the constituent list etc.

    # Find first station block - look for "# station_id_context: " pattern
    first_station_idx = None
    for i, line in enumerate(lines):
        if line.startswith('# Harmonic constants from TICON-4') or line.startswith('# Harmonic constants derived from TICON-4'):
            first_station_idx = i
            break

    if first_station_idx is None:
        print("FEHLER: Keine Stationsblöcke gefunden!")
        sys.exit(1)

    header_lines = lines[:first_station_idx]
    station_text = '\n'.join(lines[first_station_idx:])

    # Split into blocks: each starts with "# Harmonic constants derived from"
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
    """Extract lat, lon, name, country from a station block."""
    lat = lon = None
    name_line = None
    name_line_idx = None
    country = None
    station_id = None

    for i, line in enumerate(block_lines):
        if line.startswith('# !latitude:'):
            try:
                lat = float(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith('# !longitude:'):
            try:
                lon = float(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith('# country:'):
            country = line.split(':', 1)[1].strip()
        elif line.startswith('# station_id_context:'):
            station_id = line.split(':', 1)[1].strip()
        elif not line.startswith('#') and not line.startswith('x ') and ',' in line and name_line is None:
            # First non-comment line with comma = station name line
            parts = line.strip().split(',')
            if len(parts) >= 2 and not re.match(r'^[\d.]+$', parts[0].strip()):
                name_line = line.strip()
                name_line_idx = i

    return {
        'lat': lat, 'lon': lon,
        'name_line': name_line, 'name_line_idx': name_line_idx,
        'country': country, 'station_id': station_id,
    }


def improve_name_from_geonames(original_name, country, geo_result):
    """Decide whether to use geonames result to improve station name."""
    if geo_result is None:
        return None

    geo_name = geo_result['name']
    geo_country = geo_result['country']
    dist = geo_result['distance']

    # Only use if very close (<1km) or name is similar
    orig_norm = normalize_name(original_name)
    geo_norm = normalize_name(geo_name)

    # Check if names are similar
    if orig_norm == geo_norm:
        # Same name - use geonames version (may have diacritics)
        return f"{geo_name}, {country}"

    # Check if geonames name starts with or contains the original
    if geo_norm.startswith(orig_norm) or orig_norm.startswith(geo_norm):
        if dist < 1.0:
            return f"{geo_name}, {country}"

    # Very close match and short distance
    if dist < 0.5:
        # Check character overlap
        common = sum(1 for a, b in zip(orig_norm, geo_norm) if a == b)
        if common >= min(len(orig_norm), len(geo_norm)) * 0.7:
            return f"{geo_name}, {country}"

    return None


def main():
    print("=" * 70)
    print("TICON-4 Stationsnamen korrigieren")
    print("=" * 70)

    # Step 1: Load reference stations
    print("\n1. Referenz-Stationen laden...")
    ref_stations = extract_reference_stations()
    n_with_diacritics = sum(1 for s in ref_stations.values() if any(ord(c) > 127 for c in s['name']))
    print(f"   Gesamt: {len(ref_stations)} Referenz-Stationen ({n_with_diacritics} mit Sonderzeichen)")

    # Step 2: Parse TICON-4 file
    print("\n2. TICON-4 Datei einlesen...")
    with open(INPUT_PATH, 'r', encoding='iso-8859-1') as f:
        text = f.read()
    header_lines, blocks = parse_ticon4_blocks(text)
    print(f"   {len(blocks)} Stationsblöcke gefunden")

    # Step 3: Match and correct
    print("\n3. Stationsnamen korrigieren...")
    matched_ref = 0
    matched_geo = 0
    matched_cleaned = 0
    unchanged = 0
    errors = 0
    geo_cache = {}

    for bi, block in enumerate(blocks):
        info = extract_block_info(block)
        if info['lat'] is None or info['lon'] is None or info['name_line'] is None:
            unchanged += 1
            continue

        lat, lon = info['lat'], info['lon']
        old_name = info['name_line']
        country = info['country'] or ''
        idx = info['name_line_idx']

        # Try reference match first
        ref, dist = find_best_ref_match(lat, lon, old_name, ref_stations)
        if ref is not None:
            new_name = ref['name']
            if new_name != old_name:
                block[idx] = new_name
                if (bi + 1) % 200 == 0 or any(ord(c) > 127 for c in new_name):
                    pass  # Quiet
                matched_ref += 1
            else:
                unchanged += 1
            continue

        # Try cleaning up name: remove technical suffixes and apply diacritics
        name_part = old_name.split(',')[0].strip()
        country_part = old_name.split(',', 1)[1].strip() if ',' in old_name else country

        # First clean up the name
        cleaned = name_part
        # Remove trailing IDs like "347A", "080A", "316C", "229A"
        cleaned = re.sub(r'\s+\d{3}[A-Za-z]?\s*$', '', cleaned)
        # Remove trailing sensor codes like "Ma02", "Gs01", "Hd25", "Gs15"
        cleaned = re.sub(r'\s+[A-Z][a-z]\d{2}\s*$', '', cleaned)
        # Remove trailing "Tg" suffix (tide gauge marker)
        cleaned = re.sub(r'[Tt]g$', '', cleaned).strip()
        # Remove "Uscgs" suffix
        cleaned = re.sub(r'\s+Uscgs\s*$', '', cleaned, flags=re.IGNORECASE)
        # Remove trailing "Ridi" (from CMEMS ID conventions)
        cleaned = re.sub(r'\s+Ridi\s*$', '', cleaned, flags=re.IGNORECASE)
        # Remove trailing technical codes (Alge, Alio, Sjov, Pfm, etc.)
        cleaned = re.sub(r'\s+[A-Z][a-z]{2,4}(?:pfm|fpfm)?\s*$', '', cleaned)
        # Remove "05Minute" or similar timing suffixes
        cleaned = re.sub(r'\s+\d+[Mm]inute\s*$', '', cleaned)
        # Clean up duplicate number suffix like "Coruna2"
        cleaned = re.sub(r'(\w[a-z])\d+$', r'\1', cleaned)
        # Split CamelCase compound names like "Arklowharbour" → "Arklow Harbour"
        # Only if the name is one word and >10 chars
        if ' ' not in cleaned and len(cleaned) > 10:
            # Known compound words
            compounds = {
                'harbour': ' Harbour', 'harbor': ' Harbor', 'haven': ' Haven',
                'island': ' Island', 'point': ' Point', 'castle': ' Castle',
                'bridge': ' Bridge', 'creek': ' Creek', 'river': ' River',
                'polder': ' Polder', 'sluis': ' Sluis', 'platform': ' Platform',
            }
            for suffix, replacement in compounds.items():
                if cleaned.lower().endswith(suffix) and len(cleaned) > len(suffix) + 2:
                    prefix = cleaned[:-len(suffix)]
                    cleaned = prefix + replacement
                    break
        # Capitalize properly
        if cleaned.isupper() or cleaned.islower():
            cleaned = cleaned.title()
        # Don't apply to pure ID names (all alphanumeric with numbers)
        if re.match(r'^[A-Z]\d+[A-Za-z]+\s', cleaned) and len(cleaned) < 15:
            cleaned = name_part  # Revert, it's an ID

        # Apply diacritics from dictionary
        changed = False
        for plain, accented in DIACRITICS_MAP.items():
            if plain.lower() in cleaned.lower():
                # Replace case-insensitively but preserve the accented version
                pattern = re.compile(re.escape(plain), re.IGNORECASE)
                new_cleaned = pattern.sub(accented, cleaned)
                if new_cleaned != cleaned:
                    cleaned = new_cleaned
                    changed = True

        # Try geonames API to get proper name with diacritics
        cache_key = (round(lat, 3), round(lon, 3))
        if cache_key not in geo_cache:
            geo_result = query_geonames(lat, lon, radius_km=5)
            geo_cache[cache_key] = geo_result
            time.sleep(0.4)  # Rate limit
        else:
            geo_result = geo_cache[cache_key]

        if geo_result:
            improved = improve_name_from_geonames(cleaned, country_part, geo_result)
            if improved:
                improved = encode_iso8859(improved)
                if improved != old_name:
                    block[idx] = improved
                    matched_geo += 1
                    continue

        new_name = f"{cleaned}, {country_part}"
        new_name = encode_iso8859(new_name)

        if new_name != old_name:
            block[idx] = new_name
            matched_cleaned += 1
        else:
            unchanged += 1

        if (bi + 1) % 100 == 0:
            print(f"   [{bi+1}/{len(blocks)}] ref={matched_ref}, geo={matched_geo}, bereinigt={matched_cleaned}, unverändert={unchanged}")

    print(f"\n   Ergebnis:")
    print(f"   - Referenz-Match:  {matched_ref}")
    print(f"   - Geonames-Match:  {matched_geo}")
    print(f"   - Bereinigt:       {matched_cleaned}")
    print(f"   - Unverändert:     {unchanged}")

    # Step 4: Write output
    print(f"\n4. Schreibe {OUTPUT_PATH.name}...")
    with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(header_lines))
        f.write('\n')  # Ensure header ends with newline
        for block in blocks:
            f.write('\n'.join(block))
            f.write('\n')

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"   Gespeichert: {size_kb:.0f} KB")

    # Step 5: Show some examples of corrections
    print(f"\n5. Beispiele für Korrekturen:")
    # Re-read and compare
    with open(INPUT_PATH, 'r', encoding='iso-8859-1') as f:
        old_text = f.read()
    with open(OUTPUT_PATH, 'r', encoding='iso-8859-1') as f:
        new_text = f.read()

    old_names = re.findall(r'^(?!#)(?!x )(?!\+)(?!\d)(.+,.+)$', old_text, re.MULTILINE)
    new_names = re.findall(r'^(?!#)(?!x )(?!\+)(?!\d)(.+,.+)$', new_text, re.MULTILINE)

    shown = 0
    for old, new in zip(old_names, new_names):
        if old != new and shown < 50:
            print(f"   {old}")
            print(f"   → {new}")
            print()
            shown += 1


if __name__ == '__main__':
    main()
