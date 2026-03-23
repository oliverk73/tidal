#!/usr/bin/env python3
"""
Script to add country names to tide station entries in harmonics files.
Identifies stations without country names and adds them based on:
- Station name patterns
- Timezone information
- Geographic coordinates
"""

import re
import sys

# Mapping of timezones to countries
TIMEZONE_TO_COUNTRY = {
    'Europe/London': 'United Kingdom',
    'Europe/Dublin': 'Ireland',
    'Europe/Paris': 'France',
    'Europe/Berlin': 'Germany',
    'Europe/Amsterdam': 'Netherlands',
    'Europe/Brussels': 'Belgium',
    'Europe/Copenhagen': 'Denmark',
    'Europe/Oslo': 'Norway',
    'Europe/Stockholm': 'Sweden',
    'Europe/Helsinki': 'Finland',
    'Europe/Lisbon': 'Portugal',
    'Europe/Madrid': 'Spain',
    'Europe/Rome': 'Italy',
    'Europe/Athens': 'Greece',
    'Europe/Istanbul': 'Turkey',
    'Europe/Moscow': 'Russia',
    'Europe/Warsaw': 'Poland',
    'Europe/Prague': 'Czech Republic',
    'Europe/Vienna': 'Austria',
    'Europe/Zurich': 'Switzerland',
    'Asia/Tokyo': 'Japan',
    'Asia/Seoul': 'South Korea',
    'Asia/Shanghai': 'China',
    'Asia/Hong_Kong': 'China',
    'Asia/Taipei': 'Taiwan',
    'Asia/Manila': 'Philippines',
    'Asia/Singapore': 'Singapore',
    'Asia/Jakarta': 'Indonesia',
    'Asia/Bangkok': 'Thailand',
    'Asia/Kuala_Lumpur': 'Malaysia',
    'Asia/Rangoon': 'Myanmar',
    'Asia/Yangon': 'Myanmar',
    'Asia/Kolkata': 'India',
    'Asia/Calcutta': 'India',
    'Asia/Colombo': 'Sri Lanka',
    'Asia/Karachi': 'Pakistan',
    'Asia/Dhaka': 'Bangladesh',
    'Asia/Kathmandu': 'Nepal',
    'Asia/Dubai': 'United Arab Emirates',
    'Asia/Muscat': 'Oman',
    'Asia/Qatar': 'Qatar',
    'Asia/Bahrain': 'Bahrain',
    'Asia/Kuwait': 'Kuwait',
    'Asia/Riyadh': 'Saudi Arabia',
    'Asia/Aden': 'Yemen',
    'Asia/Tehran': 'Iran',
    'Asia/Baghdad': 'Iraq',
    'Asia/Jerusalem': 'Israel',
    'Asia/Beirut': 'Lebanon',
    'Asia/Damascus': 'Syria',
    'Asia/Amman': 'Jordan',
    'Asia/Vladivostok': 'Russia',
    'Asia/Novosibirsk': 'Russia',
    'Asia/Yekaterinburg': 'Russia',
    'Asia/Irkutsk': 'Russia',
    'Asia/Magadan': 'Russia',
    'Asia/Kamchatka': 'Russia',
    'Asia/Brunei': 'Brunei',
    'Asia/Phnom_Penh': 'Cambodia',
    'Asia/Vientiane': 'Laos',
    'Asia/Ho_Chi_Minh': 'Vietnam',
    'Asia/Saigon': 'Vietnam',
    'Africa/Abidjan': 'Cote D\'Ivoire',
    'Africa/Lagos': 'Nigeria',
    'Africa/Accra': 'Ghana',
    'Africa/Dakar': 'Senegal',
    'Africa/Casablanca': 'Morocco',
    'Africa/Cairo': 'Egypt',
    'Africa/Johannesburg': 'South Africa',
    'Africa/Nairobi': 'Kenya',
    'Africa/Dar_es_Salaam': 'Tanzania',
    'Africa/Maputo': 'Mozambique',
    'Africa/Luanda': 'Angola',
    'Africa/Douala': 'Cameroon',
    'Africa/Libreville': 'Gabon',
    'Africa/Brazzaville': 'Congo',
    'Africa/Kinshasa': 'Democratic Republic of Congo',
    'Africa/Tunis': 'Tunisia',
    'Africa/Algiers': 'Algeria',
    'Africa/Tripoli': 'Libya',
    'Africa/Addis_Ababa': 'Ethiopia',
    'Africa/Mogadishu': 'Somalia',
    'Africa/Djibouti': 'Djibouti',
    'Africa/Asmara': 'Eritrea',
    'Africa/Nouakchott': 'Mauritania',
    'Africa/Freetown': 'Sierra Leone',
    'Africa/Monrovia': 'Liberia',
    'Africa/Conakry': 'Guinea',
    'Africa/Bissau': 'Guinea-Bissau',
    'Africa/Banjul': 'Gambia',
    'Africa/Lome': 'Togo',
    'Africa/Porto-Novo': 'Benin',
    'Africa/Sao_Tome': 'Sao Tome and Principe',
    'Africa/Malabo': 'Equatorial Guinea',
    'Atlantic/Reykjavik': 'Iceland',
    'Atlantic/Azores': 'Portugal',
    'Atlantic/Madeira': 'Portugal',
    'Atlantic/Canary': 'Spain',
    'Atlantic/Cape_Verde': 'Cape Verde',
    'Atlantic/St_Helena': 'Saint Helena',
    'Australia/Sydney': 'Australia',
    'Australia/Melbourne': 'Australia',
    'Australia/Brisbane': 'Australia',
    'Australia/Perth': 'Australia',
    'Australia/Adelaide': 'Australia',
    'Australia/Darwin': 'Australia',
    'Australia/Hobart': 'Australia',
    'Australia/Lord_Howe': 'Australia',
    'Pacific/Auckland': 'New Zealand',
    'Pacific/Wellington': 'New Zealand',
    'Pacific/Chatham': 'New Zealand',
    'Pacific/Fiji': 'Fiji',
    'Pacific/Noumea': 'New Caledonia',
    'Pacific/Tahiti': 'French Polynesia',
    'Pacific/Rarotonga': 'Cook Islands',
    'Pacific/Apia': 'Samoa',
    'Pacific/Tongatapu': 'Tonga',
    'Pacific/Port_Moresby': 'Papua New Guinea',
    'Pacific/Guam': 'Guam',
    'Pacific/Saipan': 'Northern Mariana Islands',
    'Pacific/Palau': 'Palau',
    'Pacific/Majuro': 'Marshall Islands',
    'Pacific/Pohnpei': 'Micronesia',
    'Pacific/Tarawa': 'Kiribati',
    'Pacific/Nauru': 'Nauru',
    'Pacific/Funafuti': 'Tuvalu',
    'Pacific/Efate': 'Vanuatu',
    'Pacific/Guadalcanal': 'Solomon Islands',
    'America/Argentina/Buenos_Aires': 'Argentina',
    'America/Sao_Paulo': 'Brazil',
    'America/Rio_Branco': 'Brazil',
    'America/Manaus': 'Brazil',
    'America/Recife': 'Brazil',
    'America/Lima': 'Peru',
    'America/Bogota': 'Colombia',
    'America/Caracas': 'Venezuela',
    'America/Santiago': 'Chile',
    'America/Montevideo': 'Uruguay',
    'America/Asuncion': 'Paraguay',
    'America/La_Paz': 'Bolivia',
    'America/Guayaquil': 'Ecuador',
    'America/Paramaribo': 'Suriname',
    'America/Cayenne': 'French Guiana',
    'America/Guyana': 'Guyana',
    'America/Mexico_City': 'Mexico',
    'America/Cancun': 'Mexico',
    'America/Tijuana': 'Mexico',
    'America/Panama': 'Panama',
    'America/Costa_Rica': 'Costa Rica',
    'America/Guatemala': 'Guatemala',
    'America/Tegucigalpa': 'Honduras',
    'America/Managua': 'Nicaragua',
    'America/El_Salvador': 'El Salvador',
    'America/Belize': 'Belize',
    'America/Havana': 'Cuba',
    'America/Jamaica': 'Jamaica',
    'America/Port-au-Prince': 'Haiti',
    'America/Santo_Domingo': 'Dominican Republic',
    'America/Puerto_Rico': 'Puerto Rico',
    'America/Martinique': 'Martinique',
    'America/Guadeloupe': 'Guadeloupe',
    'America/Barbados': 'Barbados',
    'America/Trinidad': 'Trinidad and Tobago',
    'America/Curacao': 'Curacao',
    'America/Aruba': 'Aruba',
    'America/Nassau': 'Bahamas',
    'America/Grand_Turk': 'Turks and Caicos Islands',
    'America/Cayman': 'Cayman Islands',
    'America/St_Thomas': 'U.S. Virgin Islands',
    'America/Tortola': 'British Virgin Islands',
    'America/St_Kitts': 'Saint Kitts and Nevis',
    'America/Antigua': 'Antigua and Barbuda',
    'America/Dominica': 'Dominica',
    'America/St_Lucia': 'Saint Lucia',
    'America/St_Vincent': 'Saint Vincent and the Grenadines',
    'America/Grenada': 'Grenada',
    'America/Toronto': 'Canada',
    'America/Vancouver': 'Canada',
    'America/Halifax': 'Canada',
    'America/St_Johns': 'Canada',
    'America/Edmonton': 'Canada',
    'America/Winnipeg': 'Canada',
    'America/Regina': 'Canada',
    'America/Montreal': 'Canada',
    'Indian/Mauritius': 'Mauritius',
    'Indian/Reunion': 'Reunion',
    'Indian/Maldives': 'Maldives',
    'Indian/Seychelles': 'Seychelles',
    'Indian/Mayotte': 'Mayotte',
    'Indian/Comoro': 'Comoros',
    'Indian/Antananarivo': 'Madagascar',
    'Indian/Chagos': 'British Indian Ocean Territory',
    'Indian/Kerguelen': 'French Southern Territories',
    'Africa/Windhoek': 'Namibia',
    'Africa/Gaborone': 'Botswana',
    'Africa/Harare': 'Zimbabwe',
    'Africa/Lusaka': 'Zambia',
    'Africa/Blantyre': 'Malawi',
    'Africa/Kampala': 'Uganda',
    'Africa/Kigali': 'Rwanda',
    'Africa/Bujumbura': 'Burundi',
    'Europe/Zagreb': 'Croatia',
    'Europe/Ljubljana': 'Slovenia',
    'Europe/Belgrade': 'Serbia',
    'Europe/Podgorica': 'Montenegro',
    'Europe/Sarajevo': 'Bosnia and Herzegovina',
    'Europe/Skopje': 'North Macedonia',
    'Europe/Tirana': 'Albania',
    'Europe/Bucharest': 'Romania',
    'Europe/Sofia': 'Bulgaria',
    'Europe/Budapest': 'Hungary',
    'Europe/Kiev': 'Ukraine',
    'Europe/Kyiv': 'Ukraine',
    'Europe/Minsk': 'Belarus',
    'Europe/Riga': 'Latvia',
    'Europe/Vilnius': 'Lithuania',
    'Europe/Tallinn': 'Estonia',
    'Europe/Gibraltar': 'Gibraltar',
    'Europe/Monaco': 'Monaco',
    'Europe/Malta': 'Malta',
    'Asia/Nicosia': 'Cyprus',
    'Pacific/Wallis': 'Wallis and Futuna',
    'Pacific/Fakaofo': 'Tokelau',
    'Pacific/Niue': 'Niue',
    'Pacific/Pitcairn': 'Pitcairn Islands',
    'Pacific/Easter': 'Chile',
    'Pacific/Galapagos': 'Ecuador',
    'Pacific/Marquesas': 'French Polynesia',
    'Pacific/Gambier': 'French Polynesia',
    'Atlantic/Bermuda': 'Bermuda',
    'Atlantic/South_Georgia': 'South Georgia',
    'Atlantic/Stanley': 'Falkland Islands',
    'Atlantic/Faroe': 'Faroe Islands',
    'Arctic/Longyearbyen': 'Norway',
    'America/Godthab': 'Greenland',
    'America/Nuuk': 'Greenland',
    'America/Miquelon': 'Saint Pierre and Miquelon',
}

# Known country names that appear in station names (includes variations and abbreviations)
KNOWN_COUNTRIES = [
    'United Kingdom', 'UK', 'U.K.', 'England', 'Scotland', 'Wales', 'Northern Ireland',
    'Ireland', 'France', 'Germany', 'Netherlands', 'Belgium', 'Denmark', 'Norge',
    'Norway', 'Sweden', 'Finland', 'Portugal', 'Spain', 'Italy', 'Greece', 'Croatia',
    'Slovenia', 'Serbia', 'Montenegro', 'Albania', 'Bosnia', 'Herzegovina', 'Macedonia',
    'Turkey', 'Russia', 'Poland', 'Czech Republic', 'Austria', 'Switzerland',
    'Hungary', 'Romania', 'Bulgaria', 'Ukraine', 'Belarus', 'Latvia', 'Lithuania', 'Estonia',
    'Japan', 'South Korea', 'Korea', 'China', 'Taiwan', 'Philippines',
    'Singapore', 'Indonesia', 'Thailand', 'Malaysia', 'Myanmar', 'Burma',
    'India', 'Sri Lanka', 'Pakistan', 'Bangladesh', 'Nepal',
    'United Arab Emirates', 'UAE', 'U.A.E.', 'Oman', 'Qatar', 'Bahrain', 'Kuwait',
    'Saudi Arabia', 'Yemen', 'Iran', 'Iraq', 'Israel', 'Lebanon', 'Syria',
    'Jordan', 'Brunei', 'Cambodia', 'Laos', 'Vietnam',
    "Cote D'Ivoire", 'Ivory Coast', 'Nigeria', 'Ghana', 'Senegal', 'Morocco',
    'Egypt', 'South Africa', 'Kenya', 'Tanzania', 'Mozambique', 'Angola',
    'Cameroon', 'Gabon', 'Congo', 'Tunisia', 'Algeria', 'Libya', 'Ethiopia',
    'Somalia', 'Djibouti', 'Eritrea', 'Mauritania', 'Sierra Leone', 'Liberia',
    'Guinea', 'Guinea-Bissau', 'Gambia', 'Togo', 'Benin', 'Namibia', 'Botswana',
    'Zimbabwe', 'Zambia', 'Malawi', 'Uganda', 'Rwanda', 'Burundi',
    'Iceland', 'Cape Verde', 'Saint Helena', 'Western Sahara',
    'Australia', 'New Zealand', 'Fiji', 'New Caledonia', 'French Polynesia',
    'Cook Islands', 'Samoa', 'Tonga', 'Papua New Guinea', 'Guam',
    'Palau', 'Marshall Islands', 'Micronesia', 'Kiribati', 'Nauru', 'Tuvalu',
    'Vanuatu', 'Solomon Islands', 'Wallis', 'Futuna',
    'Argentina', 'Brazil', 'Brasil', 'Peru', 'Colombia', 'Venezuela', 'Chile',
    'Uruguay', 'Paraguay', 'Bolivia', 'Ecuador', 'Suriname', 'French Guiana',
    'Guyana', 'Mexico', 'Panama', 'Costa Rica', 'Guatemala', 'Honduras',
    'Nicaragua', 'El Salvador', 'Belize', 'Cuba', 'Jamaica', 'Haiti',
    'Dominican Republic', 'Puerto Rico', 'Martinique', 'Guadeloupe',
    'Barbados', 'Trinidad and Tobago', 'Curacao', 'Curaao', 'Aruba', 'Bahamas',
    'Canada', 'Mauritius', 'Reunion', 'Maldives', 'Seychelles', 'Madagascar',
    'Antarctica', 'Greenland', 'Faroe Islands', 'Svalbard', 'Spitsbergen',
    'Canary Islands', 'Madeira', 'Azores',
    'Hong Kong', 'Macau',
    'Antigua', 'Barbuda', 'St. Lucia', 'Saint Lucia', 'Grenada', 'Dominica',
    'St. Vincent', 'Saint Vincent', 'The Grenadines', 'Grenadines',
    'St. Kitts', 'Saint Kitts', 'Nevis', 'Montserrat', 'Anguilla',
    'British Virgin Islands', 'Turks and Caicos', 'Cayman Islands',
    'Gibraltar', 'Monaco', 'Malta', 'Cyprus', 'Luxembourg', 'Liechtenstein',
    'San Marino', 'Vatican', 'Andorra',
    'Sao Tome', 'Principe', 'Cabo Verde', 'Equatorial Guinea',
    'Austral Islands', 'Marquesas', 'Tuamotu', 'Society Islands',
    'Bonaire', 'Sint Maarten', 'Caribisch Nederland',
]

# Region/city to country mappings for common patterns
REGION_TO_COUNTRY = {
    'Wales': 'United Kingdom',
    'England': 'United Kingdom',
    'Scotland': 'United Kingdom',
    'Northern Ireland': 'United Kingdom',
    'Cornwall': 'United Kingdom',
    'Devon': 'United Kingdom',
    'Kent': 'United Kingdom',
    'Sussex': 'United Kingdom',
    'Essex': 'United Kingdom',
    'Suffolk': 'United Kingdom',
    'Norfolk': 'United Kingdom',
    'Lincolnshire': 'United Kingdom',
    'Yorkshire': 'United Kingdom',
    'Lancashire': 'United Kingdom',
    'Cumbria': 'United Kingdom',
    'Northumberland': 'United Kingdom',
    'Orkney': 'United Kingdom',
    'Shetland': 'United Kingdom',
    'Hebrides': 'United Kingdom',
    'Isle of Man': 'United Kingdom',
    'Channel Islands': 'United Kingdom',
    'Jersey': 'United Kingdom',
    'Guernsey': 'United Kingdom',
    'Brittany': 'France',
    'Bretagne': 'France',
    'Normandy': 'France',
    'Normandie': 'France',
    'Provence': 'France',
    'Aquitaine': 'France',
    'Bavaria': 'Germany',
    'Bayern': 'Germany',
    'Schleswig-Holstein': 'Germany',
    'Niedersachsen': 'Germany',
    'Friesland': 'Netherlands',
    'Zeeland': 'Netherlands',
    'Noord-Holland': 'Netherlands',
    'Zuid-Holland': 'Netherlands',
    'Galicia': 'Spain',
    'Catalonia': 'Spain',
    'Catalunya': 'Spain',
    'Andalucia': 'Spain',
    'Basque Country': 'Spain',
    'Sicily': 'Italy',
    'Sicilia': 'Italy',
    'Sardinia': 'Italy',
    'Sardegna': 'Italy',
    'Hokkaido': 'Japan',
    'Honshu': 'Japan',
    'Kyushu': 'Japan',
    'Shikoku': 'Japan',
    'Okinawa': 'Japan',
    'Sumatra': 'Indonesia',
    'Java': 'Indonesia',
    'Borneo': 'Indonesia',
    'Kalimantan': 'Indonesia',
    'Sulawesi': 'Indonesia',
    'Celebes': 'Indonesia',
    'Irian': 'Indonesia',
    'Papua': 'Indonesia',
    'Bali': 'Indonesia',
    'Lombok': 'Indonesia',
    'Flores': 'Indonesia',
    'Timor': 'Indonesia',
    'Moluccas': 'Indonesia',
    'Maluku': 'Indonesia',
    'Luzon': 'Philippines',
    'Visayas': 'Philippines',
    'Mindanao': 'Philippines',
    'Palawan': 'Philippines',
    'Sabah': 'Malaysia',
    'Sarawak': 'Malaysia',
    'Penang': 'Malaysia',
    'Perak': 'Malaysia',
    'Johor': 'Malaysia',
    'Queensland': 'Australia',
    'New South Wales': 'Australia',
    'NSW': 'Australia',
    'Victoria': 'Australia',
    'Tasmania': 'Australia',
    'South Australia': 'Australia',
    'Western Australia': 'Australia',
    'Northern Territory': 'Australia',
    'North Island': 'New Zealand',
    'South Island': 'New Zealand',
    'Patagonia': 'Argentina',
    'Tierra del Fuego': 'Argentina',
    'British Columbia': 'Canada',
    'BC': 'Canada',
    'Nova Scotia': 'Canada',
    'New Brunswick': 'Canada',
    'Newfoundland': 'Canada',
    'Labrador': 'Canada',
    'Quebec': 'Canada',
    'Ontario': 'Canada',
    'Manitoba': 'Canada',
    'Saskatchewan': 'Canada',
    'Alberta': 'Canada',
    'Yukon': 'Canada',
    'Northwest Territories': 'Canada',
    'Nunavut': 'Canada',
}

def has_country_name(station_name):
    """Check if station name already contains a country name."""
    name_upper = station_name.upper()
    for country in KNOWN_COUNTRIES:
        if country.upper() in name_upper:
            return True
    return False

def get_country_from_timezone(timezone):
    """Get country name from timezone."""
    # Extract timezone name from format like "+03:00 :Asia/Qatar"
    if ':' in timezone:
        parts = timezone.split(':')
        if len(parts) >= 3:
            tz_name = parts[2].strip()
            return TIMEZONE_TO_COUNTRY.get(tz_name, None)
    return None

def get_country_from_region(station_name):
    """Try to get country from region names in station name."""
    for region, country in REGION_TO_COUNTRY.items():
        if region.lower() in station_name.lower():
            return country
    return None

def get_country_from_coordinates(lat, lon):
    """Rough country estimation based on coordinates."""
    # This is a simplified version - in real usage you'd use a geocoding service

    # Europe
    if 35 <= lat <= 71 and -10 <= lon <= 30:
        if 49 <= lat <= 61 and -8 <= lon <= 2:
            return 'United Kingdom'
        elif 51 <= lat <= 56 and 3 <= lon <= 15:
            return 'Germany'
        elif 41 <= lat <= 51 and -5 <= lon <= 10:
            return 'France'
        elif 36 <= lat <= 44 and -10 <= lon <= -6:
            return 'Portugal'
        elif 36 <= lat <= 44 and -6 <= lon <= 4:
            return 'Spain'
        elif 36 <= lat <= 47 and 6 <= lon <= 19:
            return 'Italy'
        elif 35 <= lat <= 42 and 19 <= lon <= 30:
            return 'Greece'

    # Asia
    if 0 <= lat <= 50 and 60 <= lon <= 150:
        if 30 <= lat <= 46 and 129 <= lon <= 146:
            return 'Japan'
        if 20 <= lat <= 40 and 100 <= lon <= 125:
            return 'China'
        if -10 <= lat <= 10 and 95 <= lon <= 141:
            return 'Indonesia'
        if 4 <= lat <= 20 and 117 <= lon <= 127:
            return 'Philippines'
        if 1 <= lat <= 7 and 100 <= lon <= 120:
            return 'Malaysia'
        if 5 <= lat <= 21 and 97 <= lon <= 106:
            return 'Thailand'

    # Australia/NZ
    if -50 <= lat <= -10 and 110 <= lon <= 180:
        if -45 <= lat <= -10 and 112 <= lon <= 154:
            return 'Australia'
        if -48 <= lat <= -34 and 166 <= lon <= 179:
            return 'New Zealand'

    # Africa
    if -35 <= lat <= 37 and -20 <= lon <= 55:
        if 27 <= lat <= 37 and -13 <= lon <= -1:
            return 'Morocco'
        if 22 <= lat <= 32 and 25 <= lon <= 37:
            return 'Egypt'
        if -35 <= lat <= -22 and 16 <= lon <= 33:
            return 'South Africa'

    # South America
    if -60 <= lat <= 15 and -85 <= lon <= -30:
        if -55 <= lat <= -22 and -73 <= lon <= -53:
            return 'Argentina'
        if -34 <= lat <= 5 and -74 <= lon <= -34:
            return 'Brazil'
        if -56 <= lat <= -17 and -76 <= lon <= -66:
            return 'Chile'

    return None

def process_harmonics_file(input_file, output_file):
    """Process harmonics file and add country names where missing."""

    with open(input_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    modified_lines = []
    i = 0
    stations_modified = 0
    stations_total = 0

    current_longitude = None
    current_latitude = None
    current_timezone = None

    while i < len(lines):
        line = lines[i]

        # Track longitude and latitude from comments
        if line.startswith('# !longitude:'):
            current_longitude = float(line.split(':')[1].strip())
        elif line.startswith('# !latitude:'):
            current_latitude = float(line.split(':')[1].strip())

        # Check if this is a station name line
        # Station names come after # !latitude: and before timezone line
        # They start with a capital letter and don't start with # or x or +/-
        if (i > 0 and
            lines[i-1].startswith('# !latitude:') and
            line.strip() and
            not line.startswith('#') and
            not line.startswith('x ') and
            not line.startswith('+') and
            not line.startswith('-') and
            line[0].isalpha()):

            station_name = line.strip()
            stations_total += 1

            # Get timezone from next line
            if i + 1 < len(lines):
                current_timezone = lines[i + 1].strip()

            # Check if country name is missing
            if not has_country_name(station_name):
                country = None

                # Try to get country from region in name
                country = get_country_from_region(station_name)

                # Try timezone
                if not country and current_timezone:
                    country = get_country_from_timezone(current_timezone)

                # Try coordinates
                if not country and current_latitude and current_longitude:
                    country = get_country_from_coordinates(current_latitude, current_longitude)

                if country:
                    # Add country to station name
                    new_station_name = f"{station_name}, {country}\n"
                    modified_lines.append(new_station_name)
                    stations_modified += 1
                    print(f"Modified: '{station_name}' -> '{station_name}, {country}'")
                    i += 1
                    continue
                else:
                    print(f"Could not determine country for: '{station_name}' (lat={current_latitude}, lon={current_longitude}, tz={current_timezone})")

        modified_lines.append(line)
        i += 1

    # Write output
    with open(output_file, 'w', encoding='latin-1') as f:
        f.writelines(modified_lines)

    print(f"\nTotal stations: {stations_total}")
    print(f"Stations modified: {stations_modified}")
    print(f"Output written to: {output_file}")

if __name__ == '__main__':
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3_with_countries.txt'

    process_harmonics_file(input_file, output_file)
