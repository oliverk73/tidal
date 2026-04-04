#!/usr/bin/env python3
"""
Convert TICON-4 harmonic constants (CSV) to XTide harmonics text format.

TICON-4: 50 constituents per station, ~4800 stations worldwide.
XTide: 175 constituents per station, missing ones set to 0.

For duplicate locations (same station from multiple sources),
picks the record with the longest observation period.

Amplitudes in TICON-4 are in cm, converted to meters for XTide.
Phases in TICON-4 are nominally Greenwich phase lag, but contain a
local-time offset from the GESLA-4 analysis. The meridian must match
the station's timezone to compensate for this offset.
"""
import csv
import sys
import math
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175

TICON4_CSV = Path("/tmp/ticon4_stations.csv")
TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_template.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt")

# Minimum years of observations to include
MIN_YEARS = 5
# Exclude US stations (already in standard XTide harmonics)
EXCLUDE_US = True

# Map TICON-4 constituent names to XTide constituent names
TICON_TO_XTIDE = {
    'M2': 'M2', 'S2': 'S2', 'N2': 'N2', 'K2': 'K2', 'K1': 'K1',
    'O1': 'O1', 'P1': 'P1', 'Q1': 'Q1', 'M4': 'M4', 'M6': 'M6',
    'M8': 'M8', 'M3': 'M3', 'M1': 'M1', 'J1': 'J1', 'OO1': 'OO1',
    'S1': 'S1', 'S4': 'S4', 'R2': 'R2', 'T2': 'T2', 'L2': 'L2',
    '2N2': '2N2', '2Q1': '2Q1', 'MU2': 'MU2', 'NU2': 'NU2',
    'LAMBDA2': 'LDA2', 'EP2': 'EPS2', 'RHO1': 'RHO1',
    'MN4': 'MN4', 'MS4': 'MS4', 'MF': 'MF', 'MSF': 'MSF',
    'MM': 'MM', 'SA': 'SA', 'SSA': 'SSA', 'N4': 'N4',
    '2SM2': '2SM2', 'MKS2': 'MKS2', '2MK5': '2MK5', '2MO5': '2MO5',
    '2MS6': '2MS6', 'SGM': 'SIG1', 'S3': 'S3',
    # These TICON-4 constituents have no XTide equivalent:
    # '3L2', '3N2', 'MA2', 'MB2', 'MSQM', 'MTM', 'R3', 'T3'
}

# Build XTide constituent name → (index, speed) map
XTIDE_CONSTITS = {}
for i, (name, speed) in enumerate(CONSTITUENTS_175):
    XTIDE_CONSTITS[name] = (i, speed)


def get_timezone_name(lat, lon, country, source=''):
    """Get timezone meridian and name.

    The meridian must match the timezone of the original measurement data,
    because TICON-4/GESLA-4 phases contain a local-time offset from the
    original analysis. The meridian compensates for this offset in XTide's
    prediction formula: h = cos(speed*(UTC + meridian) + V0 + u - phase).

    UHSLC data (uhslc_rq/uhslc_fd) was analyzed in UTC by GESLA-4, so
    phases are pure Greenwich phases → meridian must be +00:00.
    Verified empirically against official sources: Peru/DHN, Singapore/MPA,
    Malaysia/UHSLC obs, Japan/UHSLC obs (2026-04-04).

    Returns (meridian_offset, timezone_name) tuple.
    """
    # UHSLC stations: data analyzed in UTC → Greenwich phases → meridian +00:00
    if 'uhslc_rq' in source or 'uhslc_fd' in source:
        tz_name = _get_display_timezone(lat, lon, country)
        return '+00:00', tz_name
    tz_map = {
        'DEU': ('+01:00', 'Europe/Berlin'),
        'GBR': ('+00:00', 'Europe/London'),
        'FRA': ('+01:00', 'Europe/Paris'),
        'NLD': ('+01:00', 'Europe/Amsterdam'),
        'BEL': ('+01:00', 'Europe/Brussels'),
        'ESP': ('+01:00', 'Europe/Madrid'),
        'PRT': ('+00:00', 'Europe/Lisbon'),
        'ITA': ('+01:00', 'Europe/Rome'),
        'GRC': ('+02:00', 'Europe/Athens'),
        'TUR': ('+03:00', 'Europe/Istanbul'),
        'NOR': ('+01:00', 'Europe/Oslo'),
        'SWE': ('+01:00', 'Europe/Stockholm'),
        'FIN': ('+02:00', 'Europe/Helsinki'),
        'DNK': ('+01:00', 'Europe/Copenhagen'),
        'IRL': ('+00:00', 'Europe/Dublin'),
        'ISL': ('+00:00', 'Atlantic/Reykjavik'),
        'JPN': ('+00:00', 'Asia/Tokyo'),
        'KOR': ('+09:00', 'Asia/Seoul'),
        'CHN': ('+08:00', 'Asia/Shanghai'),
        'TWN': ('+08:00', 'Asia/Taipei'),
        'IND': ('+05:30', 'Asia/Kolkata'),
        'THA': ('+07:00', 'Asia/Bangkok'),
        'NZL': ('+12:00', 'Pacific/Auckland'),
        'BRA': ('-03:00', 'America/Sao_Paulo'),
        'ARG': ('-03:00', 'America/Buenos_Aires'),
        'CHL': ('-04:00', 'America/Santiago'),
        'ZAF': ('+02:00', 'Africa/Johannesburg'),
    }

    # Peru: meridian +00:00 because GESLA-4 analyzed UHSLC data in UTC.
    # Phases are pure Greenwich phases, no local-time offset.
    # Verified against DHN Peru (dhn.mil.pe) official tide tables.
    if country == 'PER':
        return '+00:00', 'America/Lima'

    # Australia by longitude
    if country == 'AUS':
        if lon < 115:
            return '+06:30', 'Indian/Cocos'
        elif lon < 129:
            return '+08:00', 'Australia/Perth'
        elif lon < 138:
            return '+09:30', 'Australia/Darwin'
        elif lon < 141:
            return '+09:30', 'Australia/Adelaide'
        elif lon < 152 and lat < -39:
            return '+10:00', 'Australia/Hobart'
        elif lon < 152:
            return '+10:00', 'Australia/Sydney'
        else:
            return '+10:00', 'Australia/Brisbane'

    # Canada: meridian always +00:00 because TICON4/GESLA-4 phases are true
    # Greenwich phases for Canadian MEDS stations. Only the timezone name
    # varies for correct local time display.
    if country == 'CAN':
        if lon < -120:
            return '+00:00', 'America/Vancouver'
        elif lon < -90:
            return '+00:00', 'America/Winnipeg'
        elif lon < -60:
            return '+00:00', 'America/Halifax'
        else:
            return '+00:00', 'America/St_Johns'

    # Mexico: meridian always -06:00 because GESLA-4 analyzed all Mexican
    # stations with UTC-6 (Mexico City) timestamps. The meridian compensates
    # for this in XTide's prediction formula. Only the timezone name varies
    # for correct local time display.
    if country == 'MEX':
        if lon < -113:
            return '-06:00', 'America/Tijuana'
        elif lon < -107 and lat > 27:
            return '-06:00', 'America/Hermosillo'
        elif lon < -107 and lat <= 27:
            return '-06:00', 'America/Mazatlan'
        else:
            return '-06:00', 'America/Mexico_City'

    if country in tz_map:
        return tz_map[country]

    # Fallback: derive from longitude
    tz_name = _get_display_timezone(lat, lon, country)
    offset_hours = round(lon / 15.0)
    offset_hours = max(-12, min(12, offset_hours))
    h = abs(offset_hours)
    sign = '+' if offset_hours >= 0 else '-'
    return f"{sign}{h:02d}:00", tz_name


def _get_display_timezone(lat, lon, country):
    """Get IANA timezone name for display purposes (no meridian)."""
    display_tz = {
        'DEU': 'Europe/Berlin', 'GBR': 'Europe/London', 'FRA': 'Europe/Paris',
        'NLD': 'Europe/Amsterdam', 'BEL': 'Europe/Brussels', 'ESP': 'Europe/Madrid',
        'PRT': 'Europe/Lisbon', 'ITA': 'Europe/Rome', 'GRC': 'Europe/Athens',
        'TUR': 'Europe/Istanbul', 'NOR': 'Europe/Oslo', 'SWE': 'Europe/Stockholm',
        'FIN': 'Europe/Helsinki', 'DNK': 'Europe/Copenhagen', 'IRL': 'Europe/Dublin',
        'ISL': 'Atlantic/Reykjavik', 'JPN': 'Asia/Tokyo', 'KOR': 'Asia/Seoul',
        'CHN': 'Asia/Shanghai', 'TWN': 'Asia/Taipei', 'IND': 'Asia/Kolkata',
        'THA': 'Asia/Bangkok', 'NZL': 'Pacific/Auckland', 'BRA': 'America/Sao_Paulo',
        'ARG': 'America/Buenos_Aires', 'CHL': 'America/Santiago',
        'ZAF': 'Africa/Johannesburg', 'PER': 'America/Lima',
        'MYS': 'Asia/Kuala_Lumpur', 'SGP': 'Asia/Singapore',
        'IDN': 'Asia/Jakarta', 'PHL': 'Asia/Manila', 'VNM': 'Asia/Ho_Chi_Minh',
        'BGD': 'Asia/Dhaka', 'MMR': 'Asia/Yangon', 'LKA': 'Asia/Colombo',
        'PAK': 'Asia/Karachi', 'OMN': 'Asia/Muscat', 'IRN': 'Asia/Tehran',
        'BHR': 'Asia/Bahrain', 'YEM': 'Asia/Aden', 'COL': 'America/Bogota',
        'ECU': 'America/Guayaquil', 'VEN': 'America/Caracas',
        'PAN': 'America/Panama', 'CRI': 'America/Costa_Rica',
        'GTM': 'America/Guatemala', 'HND': 'America/Tegucigalpa',
        'CUB': 'America/Havana', 'JAM': 'America/Jamaica',
        'HTI': 'America/Port-au-Prince', 'DOM': 'America/Santo_Domingo',
        'TTO': 'America/Port_of_Spain', 'BHS': 'America/Nassau',
        'PNG': 'Pacific/Port_Moresby', 'FJI': 'Pacific/Fiji',
        'TON': 'Pacific/Tongatapu', 'WSM': 'Pacific/Apia',
        'KIR': 'Pacific/Tarawa', 'SLB': 'Pacific/Guadalcanal',
        'COK': 'Pacific/Rarotonga', 'NIU': 'Pacific/Niue',
        'NRU': 'Pacific/Nauru', 'TUV': 'Pacific/Funafuti',
        'KEN': 'Africa/Nairobi', 'TZA': 'Africa/Dar_es_Salaam',
        'MOZ': 'Africa/Maputo', 'MDG': 'Indian/Antananarivo',
        'MUS': 'Indian/Mauritius', 'ATA': 'Antarctica/McMurdo',
        'RUS': 'Europe/Moscow', 'POL': 'Europe/Warsaw',
        'EST': 'Europe/Tallinn', 'BGR': 'Europe/Sofia',
        'HRV': 'Europe/Zagreb', 'EGY': 'Africa/Cairo',
        'SEN': 'Africa/Dakar', 'GHA': 'Africa/Accra',
        'NGA': 'Africa/Lagos', 'AGO': 'Africa/Luanda',
    }
    if country in display_tz:
        return display_tz[country]

    # Australia/Canada/Mexico: use longitude-based logic
    if country == 'AUS':
        if lon < 115: return 'Indian/Cocos'
        elif lon < 129: return 'Australia/Perth'
        elif lon < 138: return 'Australia/Darwin'
        elif lon < 141: return 'Australia/Adelaide'
        elif lon < 152 and lat < -39: return 'Australia/Hobart'
        elif lon < 152: return 'Australia/Sydney'
        else: return 'Australia/Brisbane'
    if country == 'CAN':
        if lon < -120: return 'America/Vancouver'
        elif lon < -90: return 'America/Winnipeg'
        elif lon < -60: return 'America/Halifax'
        else: return 'America/St_Johns'
    if country == 'MEX':
        if lon < -113: return 'America/Tijuana'
        elif lon < -107 and lat > 27: return 'America/Hermosillo'
        elif lon < -107: return 'America/Mazatlan'
        else: return 'America/Mexico_City'

    # Final fallback: Etc/GMT with POSIX inverted signs
    offset_hours = round(lon / 15.0)
    offset_hours = max(-12, min(12, offset_hours))
    h = abs(offset_hours)
    posix_sign = '-' if offset_hours >= 0 else '+'
    return f'Etc/GMT{posix_sign}{h}'


def get_country_name(code):
    """Map ISO 3166-1 alpha-3 to country name."""
    names = {
        'AUS': 'Australia', 'CAN': 'Canada', 'DEU': 'Germany',
        'GBR': 'United Kingdom', 'FRA': 'France', 'NLD': 'Netherlands',
        'BEL': 'Belgium', 'ESP': 'Spain', 'PRT': 'Portugal',
        'ITA': 'Italy', 'GRC': 'Greece', 'TUR': 'Turkey',
        'NOR': 'Norway', 'SWE': 'Sweden', 'FIN': 'Finland',
        'DNK': 'Denmark', 'IRL': 'Ireland', 'ISL': 'Iceland',
        'JPN': 'Japan', 'KOR': 'South Korea', 'CHN': 'China',
        'TWN': 'Taiwan', 'IND': 'India', 'THA': 'Thailand',
        'IDN': 'Indonesia', 'MYS': 'Malaysia', 'PHL': 'Philippines',
        'VNM': 'Vietnam', 'NZL': 'New Zealand', 'BRA': 'Brazil',
        'ARG': 'Argentina', 'CHL': 'Chile', 'MEX': 'Mexico',
        'USA': 'United States', 'ZAF': 'South Africa',
        'RUS': 'Russia', 'HRV': 'Croatia', 'POL': 'Poland',
        'ATA': 'Antarctica', 'PER': 'Peru', 'COL': 'Colombia',
        'ECU': 'Ecuador', 'URY': 'Uruguay', 'VEN': 'Venezuela',
        'CUB': 'Cuba', 'PAN': 'Panama', 'CRI': 'Costa Rica',
        'GTM': 'Guatemala', 'HND': 'Honduras', 'NIC': 'Nicaragua',
        'BLZ': 'Belize', 'JAM': 'Jamaica', 'HTI': 'Haiti',
        'DOM': 'Dominican Republic', 'TTO': 'Trinidad and Tobago',
        'BRB': 'Barbados', 'BHS': 'Bahamas', 'BMU': 'Bermuda',
        'FJI': 'Fiji', 'TON': 'Tonga', 'WSM': 'Samoa',
        'PNG': 'Papua New Guinea', 'SLB': 'Solomon Islands',
        'MHL': 'Marshall Islands', 'FSM': 'Micronesia',
        'PLW': 'Palau', 'KIR': 'Kiribati', 'TUV': 'Tuvalu',
        'NRU': 'Nauru', 'COK': 'Cook Islands', 'NIU': 'Niue',
        'GUM': 'Guam', 'ASM': 'American Samoa',
        'EGY': 'Egypt', 'MAR': 'Morocco', 'TUN': 'Tunisia',
        'SEN': 'Senegal', 'GHA': 'Ghana', 'NGA': 'Nigeria',
        'KEN': 'Kenya', 'TZA': 'Tanzania', 'MOZ': 'Mozambique',
        'MDG': 'Madagascar', 'MUS': 'Mauritius', 'REU': 'Reunion',
        'SGP': 'Singapore', 'LKA': 'Sri Lanka', 'MMR': 'Myanmar',
        'BGD': 'Bangladesh', 'PAK': 'Pakistan', 'OMN': 'Oman',
        'ARE': 'United Arab Emirates', 'SAU': 'Saudi Arabia',
        'IRN': 'Iran', 'IRQ': 'Iraq', 'ISR': 'Israel',
        'LBN': 'Lebanon', 'SYR': 'Syria', 'QAT': 'Qatar',
        'BHR': 'Bahrain', 'KWT': 'Kuwait', 'YEM': 'Yemen',
        'NCL': 'New Caledonia', 'PYF': 'French Polynesia',
        'MNE': 'Montenegro', 'ALB': 'Albania', 'SVN': 'Slovenia',
        'EST': 'Estonia', 'LVA': 'Latvia', 'LTU': 'Lithuania',
        'ROU': 'Romania', 'BGR': 'Bulgaria', 'UKR': 'Ukraine',
        'GEO': 'Georgia', 'MLT': 'Malta', 'CYP': 'Cyprus',
    }
    return names.get(code, code)


def clean_station_name(raw_name):
    """Convert TICON-4 station name to a human-readable display name."""
    # Extract base name (before source IDs)
    # Pattern: name-id-country-source
    parts = raw_name.split('-')
    # Take parts that look like name words (not IDs or source codes)
    name_parts = []
    for p in parts:
        # Stop at numeric IDs or known source suffixes
        if p.isdigit() or len(p) <= 3 and p.isalpha() and p.islower():
            break
        if p in ('aus', 'bom', 'uhslc_fd', 'uhslc_rq', 'cmems', 'refmar',
                 'noaa', 'gesla4', 'noc', 'sonel', 'psmsl'):
            break
        name_parts.append(p)

    if not name_parts:
        name_parts = [parts[0]]

    name = ' '.join(name_parts)
    # Capitalize properly
    name = name.replace('_', ' ').title()
    # Fix common issues
    name = name.replace("'S", "'s").replace(" Of ", " of ").replace(" The ", " the ")
    return name.strip()


def read_header(template_path):
    """Read the XTide header (everything before first station block)."""
    lines = []
    with open(template_path, 'r', encoding='latin-1') as f:
        for line in f:
            lines.append(line.rstrip('\n'))
            # Header ends after the constituent speed+equilibrium+node sections
            # Look for the pattern that indicates station data starts
            if line.startswith('# Equilibrium') or line.startswith('# Node factor'):
                continue
            # The header includes all constituent definitions
    return lines


def main():
    print("=" * 70)
    print("Convert TICON-4 to XTide Harmonics Format")
    print("=" * 70)

    # 1. Read all TICON-4 data
    print("\nLese TICON-4 CSV...", end='', flush=True)
    raw_stations = {}
    with open(TICON4_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['tide_gauge_name']
            if name not in raw_stations:
                raw_stations[name] = {
                    'lat': float(row['lat']),
                    'lon': float(row['lon']),
                    'years': float(row['years_of_obs']),
                    'start': row['start_date'],
                    'end': row['end_date'],
                    'source': row['gesla_source'],
                    'country': row['country'],
                    'quality': row['record_quality'],
                    'type': row['type'],
                    'datum': row['datum_information'],
                    'n_obs': int(row['no_of_obs']),
                    'constits': {}
                }
            raw_stations[name]['constits'][row['con']] = {
                'amp': float(row['amp']),
                'pha': float(row['pha']),
            }
    print(f" {len(raw_stations)} Stationen geladen")

    # 2. Deduplicate: group by location, keep best per location
    print("Dedupliziere nach Standort...", end='', flush=True)
    loc_groups = defaultdict(list)
    for name, s in raw_stations.items():
        # Group by ~1km radius
        key = (round(s['lat'], 2), round(s['lon'], 2))
        loc_groups[key].append((name, s))

    stations = {}
    for key, group in loc_groups.items():
        # Pick the one with best quality + longest record + most recent end date
        def score(item):
            name, s = item
            quality_score = 2 if 'No obvious' in s['quality'] else 1 if 'Possible datum' in s['quality'] else 0
            year_end = int(s['end'].split('/')[-1])
            return (quality_score, s['years'], year_end)

        group.sort(key=score, reverse=True)
        best_name, best = group[0]
        stations[best_name] = best

    print(f" {len(stations)} einzigartige Standorte")

    # 3. Filter
    excluded_us = 0
    excluded_short = 0
    excluded_quality = 0
    filtered = {}
    for name, s in stations.items():
        if EXCLUDE_US and s['country'] == 'USA':
            excluded_us += 1
            continue
        if s['years'] < MIN_YEARS:
            excluded_short += 1
            continue
        if 'Possible quality' in s['quality'] and s['years'] < 10:
            excluded_quality += 1
            continue
        filtered[name] = s

    print(f"\nFilter:")
    print(f"  US-Stationen ausgeschlossen: {excluded_us}")
    print(f"  < {MIN_YEARS} Jahre: {excluded_short}")
    print(f"  Qualitätsprobleme + kurz: {excluded_quality}")
    print(f"  Verbleibend: {len(filtered)}")

    # 4. Read template header
    print("\nLese Template-Header...", end='', flush=True)
    header = read_header_from_template(TEMPLATE_PATH)
    print(" OK")

    # 5. Write XTide harmonics file
    print(f"\nSchreibe {OUTPUT_PATH.name}...")
    n_written = 0
    country_count = defaultdict(int)

    with open(OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
        f.write(header)
        f.write('\n')

        for name in sorted(filtered.keys()):
            s = filtered[name]
            display_name = clean_station_name(name)
            country_code = s['country']
            country_name = get_country_name(country_code)
            lat = s['lat']
            lon = s['lon']
            tz_offset, tz_name = get_timezone_name(lat, lon, country_code, source=name)

            # Build constituent values for all 175 XTide constituents
            constit_values = []
            n_matched = 0
            for xt_name, xt_speed in CONSTITUENTS_175:
                # Find matching TICON-4 constituent
                matched = False
                for ticon_name, xt_mapped in TICON_TO_XTIDE.items():
                    if xt_mapped == xt_name and ticon_name in s['constits']:
                        c = s['constits'][ticon_name]
                        amp_m = c['amp'] / 100.0  # cm → meters
                        phase = c['pha'] % 360.0
                        constit_values.append((xt_name, amp_m, phase))
                        n_matched += 1
                        matched = True
                        break
                if not matched:
                    constit_values.append((xt_name, 0.0, 0.0))

            # Compute mean level (use datum info or 0)
            mean_level = 0.0

            # Write station block
            lines = []
            lines.append(f"# Harmonic constants from TICON-4 database (GESLA-4 analysis)")
            lines.append(f"# {int(s['n_obs'])} observations over {s['years']:.0f} years")
            lines.append(f"# from {s['start']} to {s['end']}")
            lines.append(f"# Quality: {s['quality']}")
            lines.append(f"# Source: {s['source']}")
            lines.append(f"# Constituents matched: {n_matched}/50")
            lines.append(f"#")
            lines.append(f"# {display_name}")
            lines.append(f"# BEGIN HOT COMMENTS")
            lines.append(f"# country: {country_name}")
            lines.append(f"# source: TICON-4 (GESLA-4 harmonic analysis)")
            lines.append(f"# station_id_context: {name}")
            lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
            lines.append(f"# datum: {s['datum']}")
            lines.append(f"# confidence: 7")
            lines.append(f"# !units: meters")
            lines.append(f"# !longitude: {lon:.6f}")
            lines.append(f"# !latitude: {lat:.6f}")
            lines.append(f"{display_name}, {country_name}")
            lines.append(f"{tz_offset} :{tz_name}")
            lines.append(f"{mean_level:.4f} meters")

            for xt_name, amp, phase in constit_values:
                if amp < 0.00005:
                    lines.append("x 0 0")
                else:
                    lines.append(f"{xt_name:15s} {amp:.4f}  {phase:.2f}")

            f.write('\n'.join(lines))
            f.write('\n')
            n_written += 1
            country_count[country_code] += 1

    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"\n{'='*70}")
    print(f"Geschrieben: {n_written} Stationen, {size_mb:.1f} MB")
    print(f"\nStationen nach Land (Top 20):")
    for code, count in sorted(country_count.items(), key=lambda x: -x[1])[:20]:
        print(f"  {get_country_name(code):<30s} {count:>5d}")

    # Aktualitäts-Statistik
    from collections import Counter
    end_years = Counter()
    for s in filtered.values():
        year = int(s['end'].split('/')[-1])
        end_years[year] += 1
    print(f"\nAktualität (End-Jahr):")
    for year in sorted(end_years.keys(), reverse=True)[:8]:
        print(f"  {year}: {end_years[year]} Stationen")


def read_header_from_template(template_path):
    """Read template header up to first station block."""
    lines = []
    with open(template_path, 'r', encoding='latin-1') as f:
        in_header = True
        for line in f:
            stripped = line.rstrip('\n')
            if in_header:
                lines.append(stripped)
                # Check if we've passed all header sections
                # Header ends when we hit a station data line (not starting with #, not a number,
                # not a constituent definition)
                # The header contains: comments, constituent count, speeds, equilibrium args, node factors
                # Station data starts after the last node factor line
            else:
                break

    # Actually, use the same function from generate_germany_harmonics_175
    from generate_germany_harmonics_175 import read_header_from_template as rh
    return rh(template_path)


if __name__ == '__main__':
    main()
