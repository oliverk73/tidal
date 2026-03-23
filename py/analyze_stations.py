#!/usr/bin/env python3
"""
Analyze station names to find those without a proper country name at the end.
"""

import re

# Full list of recognized country names that should appear at the end
RECOGNIZED_COUNTRIES = {
    # Europe
    'United Kingdom', 'Ireland', 'France', 'Germany', 'Netherlands', 'Belgium',
    'Denmark', 'Norway', 'Sweden', 'Finland', 'Portugal', 'Spain', 'Italy',
    'Greece', 'Turkey', 'Russia', 'Poland', 'Czech Republic', 'Austria',
    'Switzerland', 'Croatia', 'Slovenia', 'Serbia', 'Montenegro', 'Albania',
    'Bosnia and Herzegovina', 'North Macedonia', 'Hungary', 'Romania', 'Bulgaria',
    'Ukraine', 'Belarus', 'Latvia', 'Lithuania', 'Estonia', 'Iceland', 'Monaco',
    'Malta', 'Cyprus', 'Luxembourg', 'Liechtenstein', 'San Marino', 'Andorra',
    'Gibraltar',

    # Asia
    'Japan', 'South Korea', 'North Korea', 'China', 'Taiwan', 'Philippines',
    'Singapore', 'Indonesia', 'Thailand', 'Malaysia', 'Myanmar', 'Vietnam',
    'Cambodia', 'Laos', 'Brunei', 'Timor-Leste', 'India', 'Sri Lanka', 'Pakistan',
    'Bangladesh', 'Nepal', 'Bhutan', 'Afghanistan', 'Iran', 'Iraq', 'Israel',
    'Lebanon', 'Syria', 'Jordan', 'Saudi Arabia', 'Kuwait', 'Bahrain', 'Qatar',
    'United Arab Emirates', 'Oman', 'Yemen', 'Turkmenistan', 'Uzbekistan',
    'Kazakhstan', 'Kyrgyzstan', 'Tajikistan', 'Mongolia', 'Hong Kong', 'Macau',

    # Africa
    'Morocco', 'Algeria', 'Tunisia', 'Libya', 'Egypt', 'Sudan', 'South Sudan',
    'Ethiopia', 'Eritrea', 'Djibouti', 'Somalia', 'Kenya', 'Uganda', 'Tanzania',
    'Rwanda', 'Burundi', 'Democratic Republic of the Congo', 'Republic of the Congo',
    'Central African Republic', 'Cameroon', 'Nigeria', 'Niger', 'Chad', 'Mali',
    'Burkina Faso', 'Mauritania', 'Senegal', 'Gambia', 'Guinea-Bissau', 'Guinea',
    'Sierra Leone', 'Liberia', "Cote D'Ivoire", 'Ivory Coast', 'Ghana', 'Togo',
    'Benin', 'Equatorial Guinea', 'Gabon', 'Sao Tome and Principe',
    'Angola', 'Namibia', 'Botswana', 'Zimbabwe', 'Zambia', 'Malawi', 'Mozambique',
    'Madagascar', 'Mauritius', 'Seychelles', 'Comoros', 'South Africa', 'Lesotho',
    'Eswatini', 'Cape Verde', 'Western Sahara',

    # Americas
    'Canada', 'Mexico', 'Guatemala', 'Belize', 'Honduras', 'El Salvador',
    'Nicaragua', 'Costa Rica', 'Panama', 'Cuba', 'Jamaica', 'Haiti',
    'Dominican Republic', 'Puerto Rico', 'Bahamas', 'Trinidad and Tobago',
    'Barbados', 'Saint Lucia', 'Saint Vincent and the Grenadines', 'Grenada',
    'Dominica', 'Antigua and Barbuda', 'Saint Kitts and Nevis', 'Martinique',
    'Guadeloupe', 'Aruba', 'Curacao', 'Colombia', 'Venezuela', 'Guyana',
    'Suriname', 'French Guiana', 'Brazil', 'Ecuador', 'Peru', 'Bolivia',
    'Chile', 'Argentina', 'Uruguay', 'Paraguay', 'Falkland Islands', 'Bermuda',
    'Cayman Islands', 'British Virgin Islands', 'U.S. Virgin Islands',
    'Turks and Caicos Islands', 'Anguilla', 'Montserrat', 'Greenland',
    'Saint Pierre and Miquelon',

    # Oceania
    'Australia', 'New Zealand', 'Papua New Guinea', 'Fiji', 'Solomon Islands',
    'Vanuatu', 'New Caledonia', 'Samoa', 'American Samoa', 'Tonga', 'Kiribati',
    'Tuvalu', 'Nauru', 'Marshall Islands', 'Palau', 'Micronesia',
    'French Polynesia', 'Cook Islands', 'Niue', 'Tokelau', 'Wallis and Futuna',
    'Pitcairn Islands', 'Guam', 'Northern Mariana Islands', 'Norfolk Island',

    # Other territories
    'Faroe Islands', 'Svalbard', 'Antarctica', 'Saint Helena', 'South Georgia',
    'British Indian Ocean Territory', 'Reunion', 'Mayotte', 'Maldives',
    'Christmas Island', 'Cocos Islands',
}

def get_last_part(station_name):
    """Get the last part after the last comma."""
    parts = station_name.split(',')
    if len(parts) > 1:
        return parts[-1].strip()
    return station_name.strip()

def is_country_name(text):
    """Check if text is a recognized country name."""
    # Remove parenthetical suffixes like (2), (UK), etc.
    text = re.sub(r'\s*\([^)]*\)\s*$', '', text).strip()
    return text in RECOGNIZED_COUNTRIES

def extract_stations(input_file):
    """Extract all station names from the harmonics file."""
    with open(input_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    stations = []
    current_info = {}

    for i, line in enumerate(lines):
        if line.startswith('# !longitude:'):
            current_info['longitude'] = line.split(':')[1].strip()
        elif line.startswith('# !latitude:'):
            current_info['latitude'] = line.split(':')[1].strip()
        elif (i > 0 and
              lines[i-1].startswith('# !latitude:') and
              line.strip() and
              not line.startswith('#') and
              not line.startswith('x ') and
              not line.startswith('+') and
              not line.startswith('-') and
              line[0].isalpha()):

            station_name = line.strip()
            timezone = lines[i + 1].strip() if i + 1 < len(lines) else ''

            stations.append({
                'name': station_name,
                'line_number': i + 1,
                'timezone': timezone,
                'latitude': current_info.get('latitude'),
                'longitude': current_info.get('longitude'),
            })

    return stations

def analyze_stations(input_file):
    """Analyze stations and print those without proper country names."""
    stations = extract_stations(input_file)

    print(f"Total stations: {len(stations)}")
    print("\n" + "="*80)
    print("Stations without recognized country name at the end:")
    print("="*80 + "\n")

    missing_country = []

    for station in stations:
        name = station['name']
        last_part = get_last_part(name)

        if not is_country_name(last_part):
            missing_country.append(station)
            print(f"Line {station['line_number']}: {name}")
            print(f"   Last part: '{last_part}'")
            print(f"   Timezone: {station['timezone']}")
            print(f"   Coordinates: {station['latitude']}, {station['longitude']}")
            print()

    print("\n" + "="*80)
    print(f"Total stations without proper country name: {len(missing_country)}")
    print("="*80)

    return missing_country

if __name__ == '__main__':
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    analyze_stations(input_file)
