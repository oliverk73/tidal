#!/usr/bin/env python3
"""
Add # province: lines to all stations in harmonics_ticon4_worldwide.txt.

Determines province from:
1. Station name (if it contains province/state/region)
2. Coordinates (for countries where province is not in the name)

Always reads/writes ISO-8859-1.
"""

import re
import sys

INPUT_FILE = '/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt'
OUTPUT_FILE = INPUT_FILE  # overwrite in place


# ─── Province from station name ─────────────────────────────────────────

def province_from_name(name, country, lat, lon):
    """Try to extract province/state/region from the station name.
    Returns province string or None."""

    # Remove trailing " (N)" numbering like "Station, Country (2)"
    clean = re.sub(r'\s*\(\d+\)\s*$', '', name)
    # Remove ", Current" suffix
    clean = re.sub(r',\s*Current\s*$', '', clean)

    # ── UK overseas territories and special cases ──
    if country == 'United Kingdom':
        # Overseas territories - identified by NOT ending with "United Kingdom"
        if 'Bermuda' in clean:
            return 'Bermuda'
        if 'Ascension Island' in clean:
            return 'Ascension Island'
        if 'Diego Garcia' in clean:
            return 'British Indian Ocean Territory'
        if 'Gibraltar' in clean:
            return 'Gibraltar'
        if 'Falkland' in clean or 'Stanley' in clean and lat < -50:
            return 'Falkland Islands'
        if 'King Edward' in clean and lat < -50:
            return 'South Georgia'
        if 'Rothera' in clean:
            return 'British Antarctic Territory'
        if 'North Cormorant' in clean:
            return 'Scotland'  # North Sea oil platform off Scotland
        if 'Isle of Man' in clean or 'Port Erin' in clean:
            return 'Isle of Man'
        if 'Channel Islands' in clean or 'Jersey' in clean:
            return 'Channel Islands'
        if 'Isles of Scilly' in clean:
            return 'England'

        # Standard UK: "City, Region, United Kingdom"
        parts = [p.strip() for p in clean.split(',')]
        if len(parts) >= 3 and parts[-1].strip() == 'United Kingdom':
            return parts[-2].strip()
        # Two-part names for UK
        if len(parts) == 2 and parts[-1].strip() == 'United Kingdom':
            return None  # Can't determine from name alone

    # ── France overseas territories ──
    if country == 'France':
        if 'New Caledonia' in clean or 'Nouvelle-Cal' in clean:
            return 'New Caledonia'
        if 'Tahiti' in clean:
            return 'French Polynesia'
        if 'French Polynesia' in clean or 'Polyneisa' in clean:
            return 'French Polynesia'
        if 'Marquesas' in clean:
            return 'French Polynesia'
        if 'Tuamotu' in clean or 'Tuamoto' in clean:
            return 'French Polynesia'
        if 'Gambier' in clean or 'Mangareva' in clean:
            return 'French Polynesia'
        if 'Austral Islands' in clean:
            return 'French Polynesia'
        if 'Huahine' in clean:
            return 'French Polynesia'
        if 'Makemo' in clean:
            return 'French Polynesia'
        if 'Rangiroa' in clean:
            return 'French Polynesia'
        if 'Mayotte' in clean:
            return 'Mayotte'
        if 'union' in clean.lower() or 'R\xe9union' in clean:
            return 'La R\xe9union'
        if 'Kerguelen' in clean:
            return 'French Southern Territories'
        if 'Crozet' in clean:
            return 'French Southern Territories'
        if 'Saint Martin' in clean:
            return 'Saint Martin'
        if 'French Guiana' in clean or 'Guyane' in clean:
            return 'French Guiana'
        if 'Guiana' in clean or 'Salut' in clean:
            return 'French Guiana'
        if 'Robert' in clean and lat > 14:
            return 'Martinique'
        if 'Ile Saint' in clean and lat < -30:
            return 'French Southern Territories'
        if 'Ilet La' in clean and lat > 0 and lon < -50:
            return 'French Guiana'
        if 'Monaco' in clean:
            return 'Provence-Alpes-C\xf4te d\'Azur'

    # ── Denmark overseas territories ──
    if country == 'Denmark':
        if 'Greenland' in clean:
            return 'Greenland'
        # Greenland stations by coordinates (lat > 60 and lon < -20)
        if lat > 60 and lon < -10:
            return 'Greenland'
        if 'Spitsbergen' in clean:
            return None  # That's Norway actually

    # ── Countries with "City, Province, Country" pattern ──
    if country in ('Canada', 'Australia', 'Japan', 'Mexico', 'New Zealand',
                    'Ireland', 'South Africa', 'China', 'Malaysia', 'Indonesia',
                    'India', 'Philippines', 'Chile', 'Brazil', 'Argentina',
                    'Peru', 'Colombia', 'Thailand', 'Vietnam', 'Myanmar',
                    'Bangladesh', 'Pakistan', 'Sri Lanka', 'Papua New Guinea',
                    'Spain', 'Portugal', 'Greece', 'Croatia', 'Turkey',
                    'Russia', 'Poland', 'Estonia', 'Finland', 'Bulgaria',
                    'Belgium', 'Honduras', 'Guatemala', 'Costa Rica',
                    'El Salvador', 'Panama', 'Ecuador', 'Venezuela',
                    'Trinidad and Tobago', 'Dominican Republic', 'Cuba',
                    'Jamaica', 'Haiti', 'Grenada', 'Bahamas',
                    'Kenya', 'Tanzania', 'Mozambique', 'Nigeria', 'Ghana',
                    'Angola', 'Senegal', 'Mauritania',
                    'Egypt', 'Iran', 'Oman', 'Yemen', 'Bahrain',
                    'Fiji', 'Samoa', 'Tonga', 'Vanuatu', 'Solomon Islands',
                    'Kiribati', 'Nauru', 'Tuvalu', 'Niue', 'Cook Islands',
                    'Maldives', 'Mauritius', 'Seychelles', 'Madagascar',
                    'Cape Verde', 'St. Helena', 'Hong Kong', 'Singapore',
                    'Taiwan', 'Iceland'):
        parts = [p.strip() for p in clean.split(',')]
        if len(parts) >= 3:
            # Last part is country, second-to-last is province
            return parts[-2].strip()

    # ── Canada special cases without comma before province ──
    if country == 'Canada':
        parts = [p.strip() for p in clean.split(',')]
        if len(parts) == 2 and parts[-1].strip() == 'Canada':
            city = parts[0]
            # Check for province name embedded in city without comma
            ca_provinces = [
                'Ontario', 'British Columbia', 'Quebec', 'Qu\xe9bec',
                'Nova Scotia', 'New Brunswick', 'Manitoba', 'Saskatchewan',
                'Alberta', 'Newfoundland', 'Labrador',
                'Prince Edward Island', 'Nunavut', 'Northwest Territories',
                'N.W.T.'
            ]
            for prov in ca_provinces:
                if prov in city:
                    return prov.replace('N.W.T.', 'Northwest Territories')

    return None


# ─── Province from coordinates ───────────────────────────────────────────

def province_from_coords_germany(name, lat, lon):
    """Determine German Bundesland from station name and coordinates."""

    # Baltic coast detection
    is_baltic = lon > 10.5 and lat > 53.5

    # ── Known station hints from river names ──
    name_upper = name.upper()

    # Specific stations that need to be checked before generic river rules
    if 'GEESTHACHT' in name_upper:
        return 'Schleswig-Holstein'
    if 'L\xdcHORT' in name_upper or 'LUHORT' in name_upper:
        return 'Niedersachsen'  # South bank of Elbe
    if 'SCHARH' in name_upper and 'RN' in name_upper:
        return 'Hamburg'  # Island belongs to Hamburg

    # Hamburg: Elbe stations in Hamburg area
    if ('ELBE' in name_upper or 'ESTE' in name_upper) and 9.7 <= lon <= 10.35 and 53.4 <= lat <= 53.6:
        return 'Hamburg'

    # Specific Hamburg stations
    if 'CRANZ' in name_upper or 'ALTENGAMME' in name_upper:
        return 'Hamburg'

    # Bremen area
    if 'WESERWEHR' in name_upper or 'GROSSE WESERB' in name_upper:
        return 'Bremen'
    if ('WESER' in name_upper or 'HAMME' in name_upper or 'LESUM' in name_upper) and 53.0 <= lat <= 53.2 and 8.5 <= lon <= 8.9:
        return 'Bremen'
    if 'BREMERHAVEN' in name_upper:
        return 'Bremen'
    if 'BORGFELD' in name_upper or 'RITTERHUDE' in name_upper or 'WASSERHORST' in name_upper:
        return 'Bremen'

    # Niedersachsen: Weser stations outside Bremen
    if 'WESER' in name_upper and not ('BREMERHAVEN' in name_upper):
        if lat > 53.2 or lon < 8.5 or lon > 8.9:
            # Weser stations outside Bremen
            if lat > 53.5:
                return 'Niedersachsen'  # Lower Weser towards North Sea
            return 'Niedersachsen'

    # Ems river → Niedersachsen
    if 'EMS' in name_upper or 'DORTMUND-EMS' in name_upper:
        return 'Niedersachsen'
    if 'EMDEN' in name_upper or 'LEDA' in name_upper:
        return 'Niedersachsen'

    # Oste river
    if 'OSTE' in name_upper:
        if lon < 9.3:
            return 'Niedersachsen'
        return 'Niedersachsen'  # Oste is in Niedersachsen

    # Stör river → Schleswig-Holstein
    if 'ST\xd6R' in name_upper or 'STOR' in name_upper:
        return 'Schleswig-Holstein'
    if 'ITZEHOE' in name_upper:
        return 'Schleswig-Holstein'

    # Krückau → Schleswig-Holstein
    if 'KR\xdcCKAU' in name_upper or 'KRUCKAU' in name_upper:
        return 'Schleswig-Holstein'

    # Pinnau → Schleswig-Holstein
    if 'PINNAU' in name_upper:
        return 'Schleswig-Holstein'

    # Elmshorn → Schleswig-Holstein
    if 'ELMSHORN' in name_upper:
        return 'Schleswig-Holstein'

    # Ilmenau river → Niedersachsen
    if 'ILMENAU' in name_upper or 'FAHRENHOLZ' in name_upper:
        return 'Niedersachsen'

    # Wümme → Bremen (Borgfeld already caught above)
    if 'W\xdcMME' in name_upper or 'WUMME' in name_upper:
        return 'Bremen'

    # Eider → Schleswig-Holstein
    if 'EIDER' in name_upper:
        return 'Schleswig-Holstein'

    # Heiligenhafen is in Schleswig-Holstein (lon 11.006, on the border)
    if 'HEILIGENHAFEN' in name_upper:
        return 'Schleswig-Holstein'
    # Marienleuchte (Fehmarn) is also Schleswig-Holstein
    if 'MARIENLEUCHTE' in name_upper:
        return 'Schleswig-Holstein'

    # ── Baltic coast ──
    if is_baltic:
        if lon >= 11.1:
            return 'Mecklenburg-Vorpommern'
        else:
            return 'Schleswig-Holstein'

    # ── Specific well-known stations ──
    if 'OTTERNDORF' in name_upper:
        return 'Niedersachsen'  # South bank of Elbe
    if 'OSTERIFF' in name_upper:
        return 'Niedersachsen'  # Elbe mouth, Niedersachsen side
    if 'SCHARH\xd6RN' in name_upper or 'SCHARHORN' in name_upper:
        return 'Hamburg'  # Island belongs to Hamburg
    if 'HELGOLAND' in name_upper:
        return 'Schleswig-Holstein'
    if 'CUXHAVEN' in name_upper:
        return 'Niedersachsen'
    if 'B\xdcSUM' in name_upper or 'BUSUM' in name_upper:
        return 'Schleswig-Holstein'
    if 'HUSUM' in name_upper:
        return 'Schleswig-Holstein'
    if 'DAGEB\xdcLL' in name_upper or 'DAGEBULL' in name_upper:
        return 'Schleswig-Holstein'
    if 'FLENSBURG' in name_upper:
        return 'Schleswig-Holstein'
    if 'LIST' in name_upper and 'SYLT' in name_upper:
        return 'Schleswig-Holstein'
    if 'H\xd6RNUM' in name_upper or 'HORNUM' in name_upper:
        return 'Schleswig-Holstein'
    if 'WITTD\xdcN' in name_upper or 'WITTDUN' in name_upper:
        return 'Schleswig-Holstein'
    if 'PELLWORM' in name_upper:
        return 'Schleswig-Holstein'
    if 'BRUNSB\xdcTTEL' in name_upper or 'BRUNSBUTTEL' in name_upper:
        return 'Schleswig-Holstein'
    if 'BORKUM' in name_upper:
        return 'Niedersachsen'
    if 'NORDERNEY' in name_upper:
        return 'Niedersachsen'
    if 'WANGEROOGE' in name_upper:
        return 'Niedersachsen'
    if 'WILHELMSHAVEN' in name_upper:
        return 'Niedersachsen'
    if 'SCHILLIG' in name_upper:
        return 'Niedersachsen'
    if 'MELLUMPLATE' in name_upper:
        return 'Niedersachsen'
    if 'HOOKSIEL' in name_upper:
        return 'Niedersachsen'
    if 'DUKEGAT' in name_upper:
        return 'Niedersachsen'

    # ── Coordinate-based fallback ──
    # North Sea Schleswig-Holstein coast
    if lat > 53.8 and lon < 9.5 and lon > 7.5:
        return 'Schleswig-Holstein'
    # Schleswig-Holstein: Kiel area, east side
    if lat > 54.0 and 9.5 <= lon <= 10.8:
        return 'Schleswig-Holstein'
    # Schleswig-Holstein islands (North Sea)
    if lat > 54.5 and lon < 9.0:
        return 'Schleswig-Holstein'

    # Niedersachsen: North Sea coast
    if 53.0 <= lat <= 53.8 and lon < 8.5:
        return 'Niedersachsen'

    # Niedersachsen: Jade/Weser area
    if 53.3 <= lat <= 53.8 and 7.8 <= lon <= 8.6:
        return 'Niedersachsen'

    # Remaining Elbe stations
    if 'ELBE' in name_upper:
        if lon > 10.0:
            return 'Schleswig-Holstein'  # Upper Elbe/S-H side
        if lat > 53.6:
            return 'Niedersachsen'  # Elbe mouth, Niedersachsen side
        return 'Niedersachsen'

    # Wehr Geesthacht - Schleswig-Holstein (border but traditionally S-H)
    if 'GEESTHACHT' in name_upper:
        return 'Schleswig-Holstein'

    # Scharhörn - Hamburg (island belongs to Hamburg)
    if 'SCHARH\xd6RN' in name_upper or 'SCHARHORN' in name_upper:
        return 'Hamburg'

    # Bake A (North Sea, near Schleswig-Holstein/Niedersachsen border)
    if 'BAKE A' in name_upper:
        if lat > 53.9:
            return 'Schleswig-Holstein'
        return 'Niedersachsen'

    # Lühort (Elbe) - Schleswig-Holstein side
    if 'L\xdcHORT' in name_upper or 'LUHORT' in name_upper:
        return 'Schleswig-Holstein'

    # Grauerort (Elbe) - Niedersachsen side
    if 'GRAUERORT' in name_upper:
        return 'Niedersachsen'

    # Osteriff, Otterndorf (Elbe) - Niedersachsen
    if 'OSTERIFF' in name_upper or 'OTTERNDORF' in name_upper:
        return 'Niedersachsen'

    # Robbensüdsteert (Weser) - Niedersachsen
    if 'ROBBENS' in name_upper:
        return 'Niedersachsen'

    # Dwarsgat (Weser) - Niedersachsen
    if 'DWARSGAT' in name_upper:
        return 'Niedersachsen'

    # Remaining: use simple coordinate rules
    if lon < 9.0 and lat < 53.8:
        return 'Niedersachsen'
    if lon > 9.5 and lat > 53.5:
        return 'Schleswig-Holstein'

    return None


def province_from_coords_japan(name, lat, lon):
    """Determine Japanese region from coordinates."""
    if lat < 27:
        return 'Okinawa'
    if lat > 41.5:
        return 'Hokkaido'
    if lat >= 38 and lon > 139:
        return 'Tohoku'
    if 38 <= lat and lon <= 139:
        return 'Chubu'  # Sea of Japan side of Tohoku/Chubu
    if 35 <= lat < 38 and lon >= 139:
        return 'Kanto'
    if 35 <= lat < 38 and 136 <= lon < 139:
        return 'Chubu'
    if 33.5 <= lat < 35.5 and 134 <= lon < 136:
        return 'Kinki'
    if 33.5 <= lat < 35.5 and 130.5 <= lon < 134:
        return 'Chugoku'
    if 32.5 <= lat < 34.5 and 132 <= lon < 134.5:
        return 'Shikoku'
    if lat < 34 and 129 <= lon < 132:
        return 'Kyushu'
    if lat < 33.5 and lon < 132:
        return 'Kyushu'
    # Overlap areas - use more refined rules
    if 34 <= lat < 35 and lon < 134:
        return 'Shikoku'
    if 34 <= lat < 35 and 134 <= lon < 136:
        return 'Kinki'
    if lat < 34 and 132 <= lon < 134:
        return 'Shikoku'
    if 33 <= lat < 34 and lon >= 134:
        return 'Shikoku'
    if lat < 33 and lon >= 130:
        return 'Kyushu'
    # Sea of Japan coast
    if lat >= 35 and lon < 136:
        return 'Chubu'
    return 'Kanto'  # fallback


def province_from_coords_netherlands(name, lat, lon):
    """Determine Dutch province from coordinates."""
    # Offshore platforms
    if lat > 55:
        return 'North Sea'
    if lat > 53.5 and lon < 5:
        return 'North Sea'
    if lat > 52 and lon < 3.5:
        return 'North Sea'

    # Zeeland
    if lat < 51.7 and lon < 4.2:
        return 'Zeeland'
    # Zuid-Holland
    if 51.6 <= lat < 52.2 and lon < 4.7:
        return 'Zuid-Holland'
    # Some Zuid-Holland river stations
    if 51.7 <= lat < 52.0 and 4.0 <= lon < 5.3:
        return 'Zuid-Holland'
    # Noord-Holland
    if 52.2 <= lat < 53.0 and lon < 5.0:
        return 'Noord-Holland'
    # Friesland
    if lat >= 53.0 and lon < 6.0:
        return 'Friesland'
    # Groningen
    if lat >= 53.0 and lon >= 6.0:
        return 'Groningen'
    # Flevoland (IJsselmeer area)
    if 52.0 <= lat < 53.0 and 5.0 <= lon < 6.0:
        return 'Gelderland'  # River area
    # Texel area
    if 52.8 <= lat < 53.2 and lon < 5.0:
        return 'Noord-Holland'

    return 'Zuid-Holland'  # fallback for river stations


def province_from_coords_denmark(name, lat, lon):
    """Determine Danish region from coordinates."""
    # Already handled Greenland in province_from_name

    # Bornholm
    if lon > 14:
        return 'Bornholm'
    # Zealand (Sjælland) - eastern Denmark
    if lon > 11.0 and lat < 56.3:
        return 'Sj\xe6lland'
    # Copenhagen area
    if 12.0 <= lon <= 13.0 and 55.5 <= lat <= 56.0:
        return 'Sj\xe6lland'
    # Funen (Fyn)
    if 9.7 <= lon <= 11.0 and lat < 55.7:
        return 'Fyn'
    # Lolland-Falster
    if lon > 11.0 and lat < 55.0:
        return 'Lolland-Falster'
    # Northern Jutland
    if lat > 57:
        return 'Nordjylland'
    # Central Jutland
    if 56.0 <= lat <= 57 and lon < 11.0:
        return 'Midtjylland'
    # Southern Jutland
    if lat < 56.0 and lon < 9.7:
        return 'Syddanmark'
    # Als and Sønderborg area
    if 54.8 <= lat <= 55.2 and 9.5 <= lon <= 10.2:
        return 'Syddanmark'

    return 'Jylland'


def province_from_coords_france(name, lat, lon):
    """Determine French region from coordinates."""
    # Overseas already handled in province_from_name

    # Corsica
    if 41.0 <= lat <= 43.1 and lon > 8.0:
        return 'Corse'
    # Mediterranean coast
    if lat < 44 and 2.0 <= lon <= 7.5:
        return 'Occitanie' if lon < 4.5 else 'Provence-Alpes-C\xf4te d\'Azur'
    # Brittany
    if lon < -1.0 and 47.0 <= lat <= 49.0:
        return 'Bretagne'
    # Normandy (including Cherbourg at lon -1.6)
    if -2.0 <= lon <= 1.8 and lat > 48.5:
        return 'Normandie'
    # Pays de la Loire / Loire-Atlantique
    if -2.5 <= lon < -1.0 and 46.5 <= lat < 47.5:
        return 'Pays de la Loire'
    # Atlantic coast - Nouvelle-Aquitaine
    if lon < -0.5 and 43.0 <= lat < 47.0:
        return 'Nouvelle-Aquitaine'
    # Hauts-de-France (Channel)
    if lat > 50 and lon > 1.5:
        return 'Hauts-de-France'

    return None


def province_from_coords_italy(name, lat, lon):
    """Determine Italian region from coordinates."""
    # Sardinia
    if 38.5 <= lat <= 41.5 and 8.0 <= lon <= 10.0:
        return 'Sardegna'
    # Sicily
    if lat < 38.5 and lon < 16:
        return 'Sicilia'
    # Lampedusa
    if lat < 36:
        return 'Sicilia'
    # Liguria
    if 43.5 <= lat <= 44.5 and 7.5 <= lon <= 10.0:
        return 'Liguria'
    # Tuscany
    if 42.5 <= lat <= 43.6 and 9.5 <= lon <= 12.0:
        return 'Toscana'
    # Emilia-Romagna (Adriatic coast)
    if 44.0 <= lat <= 45.0 and 12.0 <= lon <= 13.0:
        return 'Emilia-Romagna'
    # Veneto
    if 45.0 <= lat <= 45.7 and 12.0 <= lon <= 13.0:
        return 'Veneto'
    # Friuli-Venezia Giulia
    if lat > 45.5 and lon > 13.0:
        return 'Friuli Venezia Giulia'
    # Marche
    if 42.5 <= lat <= 44.0 and 13.0 <= lon <= 14.5:
        return 'Marche'
    # Abruzzo
    if 42.0 <= lat <= 42.5 and 13.5 <= lon <= 15.0:
        return 'Abruzzo'
    # Lazio (including Gaeta at 41.21/13.59 and Rmn at 40.9/12.97)
    if 40.5 <= lat <= 42.5 and 11.5 <= lon <= 14.0:
        return 'Lazio'
    # Campania
    if 40.0 <= lat <= 41.2 and 14.0 <= lon <= 15.5:
        return 'Campania'
    # Puglia (Adriatic coast, including Isole Tremiti at 42.1/15.5)
    if 39.5 <= lat <= 42.5 and 15.0 <= lon <= 19.0:
        return 'Puglia'
    # Puglia (Taranto)
    if 40.0 <= lat <= 41.0 and 17.0 <= lon <= 18.5:
        return 'Puglia'
    # Calabria (Crotone at 39.08, 17.14)
    if lat < 39.5 and lon > 15.0:
        return 'Calabria'
    # Stromboli area
    if 38.5 <= lat <= 39.0 and 15.0 <= lon <= 15.7:
        return 'Sicilia'

    return None


def province_from_coords_sweden(name, lat, lon):
    """Determine Swedish region."""
    # West coast (Västra Götaland)
    if lon < 12.5 and lat < 59:
        return 'V\xe4stra G\xf6taland'
    # Skåne (south)
    if lat < 56.3 and lon > 12.5:
        return 'Sk\xe5ne'
    # Halland (including Halmstad at 56.65, 12.84)
    if 56.3 <= lat < 57.5 and lon < 13.0:
        return 'Halland'
    # Stockholm area
    if 59.0 <= lat <= 59.5 and lon > 17:
        return 'Stockholm'
    # Södermanland
    if 58.5 <= lat < 59.0 and lon > 16:
        return 'S\xf6dermanland'
    # Östergötland
    if 58.0 <= lat < 59.0 and 15.5 <= lon <= 17:
        return '\xd6sterg\xf6tland'
    # Bohuslän (north of Gothenburg, west coast)
    if lat >= 58.0 and lon < 12.0:
        return 'V\xe4stra G\xf6taland'

    return None


def province_from_coords_norway(name, lat, lon):
    """Determine Norwegian region."""
    if lat > 74:
        return 'Svalbard'
    if lat > 69:
        return 'Troms og Finnmark'
    if 67 <= lat <= 69:
        return 'Nordland'
    if 64 <= lat < 67:
        return 'Tr\xf8ndelag'
    if 62 <= lat < 64:
        return 'M\xf8re og Romsdal'
    if 60 <= lat < 62:
        return 'Vestland'
    if 58.5 <= lat < 60:
        if lon > 9:
            return 'Vestfold og Telemark'
        return 'Rogaland'
    if 57 <= lat < 58.5:
        return 'Agder'
    return 'Vestland'


def province_from_coords_mexico(name, lat, lon):
    """Determine Mexican state from coordinates."""
    # Pacific coast
    if lon < -105:
        if lat > 30:
            return 'Baja California'
        if lat > 23:
            return 'Baja California Sur'
        if lat > 20:
            return 'Jalisco'
        if lat > 16:
            return 'Guerrero'
        return 'Oaxaca'
    # Gulf coast
    if lon > -98:
        if lat > 23:
            return 'Tamaulipas'
        if lat > 19:
            return 'Veracruz'
        if lat > 18:
            return 'Tabasco'
        return 'Campeche'
    # Sea of Cortez / intermediate
    if lat > 28:
        return 'Sonora'
    if lat > 23:
        return 'Sinaloa'
    return 'Guerrero'


def province_from_coords_spain(name, lat, lon):
    """Determine Spanish region."""
    # Canary Islands
    if lat < 30:
        return 'Canarias'
    # Balearic Islands
    if lon > 1 and lat < 40.5:
        return 'Illes Balears'
    # Mediterranean (including Alicante at -0.478)
    if lon > -1.0 and lat < 42:
        return 'Comunitat Valenciana'
    # Basque Country / Cantabria / Asturias / Galicia (northern coast)
    if lat > 42:
        if lon < -7:
            return 'Galicia'
        if lon < -4:
            return 'Asturias'
        if lon < -2.5:
            return 'Cantabria'
        return 'Pa\xeds Vasco'
    # Andalusia
    if lat < 37.5 and lon < 0:
        return 'Andaluc\xeda'
    # Catalonia
    if lon > 0 and lat > 40:
        return 'Catalunya'
    return None


def province_from_coords_portugal(name, lat, lon):
    """Determine Portuguese region."""
    # Azores
    if lon < -25:
        return 'A\xe7ores'
    # Madeira
    if lat < 34 and lon < -15:
        return 'Madeira'
    # Northern Portugal
    if lat > 41:
        return 'Norte'
    if lat > 40:
        return 'Centro'
    if lat > 38.5:
        return 'Lisboa'
    return 'Algarve'


def province_from_coords_nz(name, lat, lon):
    """Determine New Zealand region."""
    # Chatham Islands
    if lon < -170 or lon > 176 and lat < -43:
        pass
    if 'Chatham' in name:
        return 'Chatham Islands'
    # Ross Island is Antarctica
    if lat < -60:
        return 'Ross Dependency'
    # Kermadec/subantarctic
    if lat < -29.0 and lat > -30:
        return 'Kermadec Islands'
    # North Island
    if lat > -39.0:
        if lon > 176:
            return 'Gisborne'
        if lat > -37:
            return 'Auckland'
        if lat > -38:
            return 'Waikato'
        return 'Hawke\'s Bay'
    # North Island south
    if -41.0 <= lat < -39.0 and lon > 174:
        return 'Wellington'
    if -39.5 <= lat < -39.0:
        return 'Taranaki'
    # South Island
    if lat < -41:
        if lon < 170:
            return 'West Coast'
        if lat > -44:
            return 'Canterbury'
        if lat > -45:
            return 'Canterbury'
        if lat > -46:
            return 'Otago'
        return 'Southland'
    return None


def province_from_coords_generic(name, country, lat, lon):
    """For countries without specific rules, try to assign a basic province."""

    # Small island nations and single-region countries - use country as province
    simple_countries = [
        'Kiribati', 'Nauru', 'Tuvalu', 'Niue', 'Cook Islands',
        'Maldives', 'Mauritius', 'Seychelles', 'Cape Verde',
        'St. Helena', 'Fiji', 'Samoa', 'Tonga', 'Vanuatu',
        'Solomon Islands', 'Hong Kong', 'Singapore', 'Bahrain',
        'Grenada', 'Jamaica', 'Haiti', 'Cuba', 'Bahamas',
        'Trinidad and Tobago', 'Iceland', 'Djibouti',
        'Ivory Coast', 'Senegal', 'Mauritania', 'Madagascar',
        'Republique du Congo', 'Sri Lanka', 'Pakistan',
        'Myanmar', 'Namibia', 'Taiwan',
        'Estonia', 'Poland', 'Finland', 'Bulgaria',
        'Croatia', 'Turkey', 'Russia',
        'Yemen', 'Egypt', 'Venezuela',
        'Nauru', 'Antarctica'
    ]
    if country in simple_countries:
        return country

    # ── Angola ──
    if country == 'Angola':
        return 'Angola'

    # ── Argentina ──
    if country == 'Argentina':
        if lat < -54:
            return 'Tierra del Fuego'
        if lat < -45:
            return 'Santa Cruz'
        if lat < -40:
            return 'Chubut'
        if lat < -36:
            return 'Buenos Aires'  # Mar del Plata area
        if lon > -60:
            return 'Buenos Aires'
        return 'Antarctica'  # Esperanza

    # ── Australia special (overseas/Antarctic) ──
    if country == 'Australia':
        if lat < -60:
            return 'Australian Antarctic Territory'
        if 'Christmas Island' in name:
            return 'Christmas Island'
        if 'Macquarie' in name:
            return 'Tasmania'
        if 'Torres Strait' in name:
            return 'Queensland'
        return None

    # ── Bangladesh ──
    if country == 'Bangladesh':
        return 'Bangladesh'

    # ── Belgium ──
    if country == 'Belgium':
        return 'West-Vlaanderen' if lon < 3.5 else 'Oost-Vlaanderen'

    # ── Canada (remaining without province in name) ──
    if country == 'Canada':
        # Try coordinate-based
        if lat > 60:
            return 'Nunavut'
        if lon is None:
            return None
        if lon < -114:
            return 'British Columbia'
        if -90 < lon < -75 and lat > 42:
            return 'Ontario'
        if -75 < lon < -64 and lat > 46:
            return 'Qu\xe9bec'
        if -67 < lon < -63 and lat < 47:
            return 'New Brunswick'
        if -65 < lon < -59 and lat < 46:
            return 'Nova Scotia'
        return None

    # ── Chile ──
    if country == 'Chile':
        if lon is not None and lon < -78:
            return 'Valpara\xedso'  # offshore islands
        if lat < -55:
            return 'Magallanes'
        if lat < -40:
            return 'Los Lagos'
        if lat < -33:
            return 'Valpara\xedso'
        if lat < -27:
            return 'Atacama'
        if lat < -23:
            return 'Antofagasta'
        return 'Arica y Parinacota'

    # ── China ──
    if country == 'China':
        if lat > 37:
            return 'Liaoning' if lon > 120 else 'Shandong'
        if lat > 34:
            return 'Jiangsu' if lon > 119 else 'Shandong'
        if lat > 30:
            return 'Zhejiang' if lon > 120 else 'Jiangsu'
        if lat > 24:
            return 'Fujian' if lon > 117 else 'Guangdong'
        if lat > 21:
            return 'Guangdong' if lon > 110 else 'Guangxi'
        if lat > 18:
            return 'Hainan'
        return 'Guangdong'

    # ── Colombia ──
    if country == 'Colombia':
        if lon < -78:
            return 'Nari\xf1o' if lat < 4 else 'Valle del Cauca'
        if lon < -76:
            return 'Valle del Cauca' if lat < 5 else 'Choc\xf3'
        if lat > 12:
            return 'San Andr\xe9s y Providencia'
        if lat > 10:
            return 'Bol\xedvar' if lon < -75 else 'Magdalena'
        return 'Bol\xedvar'

    # ── Costa Rica ──
    if country == 'Costa Rica':
        if lon < -85:
            return 'Puntarenas'  # Pacific/Cocos
        if lon < -84:
            return 'Puntarenas'
        return 'Lim\xf3n'

    # ── Curaçao (may have broken encoding) ──
    if 'Cura' in country and 'ao' in country:
        return country

    # ── Dominican Republic ──
    if country == 'Dominican Republic':
        if lat < 16:
            return 'Dominica'  # Actually Dominica, different country
        if lon < -70:
            return 'Puerto Plata'
        return 'La Altagracia'

    # ── Ecuador ──
    if country == 'Ecuador':
        if lon < -89:
            return 'Gal\xe1pagos'
        if lat > 0:
            return 'Esmeraldas'
        return 'Guayas' if lon > -81 else 'Santa Elena'

    # ── El Salvador ──
    if country == 'El Salvador':
        return 'El Salvador'

    # ── Ghana ──
    if country == 'Ghana':
        if lat < 2:
            return 'S\xe3o Tom\xe9 and Pr\xedncipe'
        return 'Ghana'

    # ── Greece ──
    if country == 'Greece':
        if lat > 40:
            return 'Makedonien'
        if lon < 21:
            return 'Ionische Inseln'
        if lat < 36:
            return 'S\xfcd\xe4g\xe4is'
        return 'Mittelgriechenland'

    # ── Guatemala ──
    if country == 'Guatemala':
        return 'Guatemala'

    # ── Honduras ──
    if country == 'Honduras':
        return 'Honduras'

    # ── Indonesia ──
    if country == 'Indonesia':
        if lat > 4:
            return 'Aceh'
        if lon < 100:
            return 'Sumatera'
        return 'Indonesia'

    # ── Iran ──
    if country == 'Iran':
        return 'Iran'

    # ── Kenya ──
    if country == 'Kenya':
        return 'Kenya'

    # ── Malaysia ──
    if country == 'Malaysia':
        if lon > 108:
            return 'Sabah' if lat > 5 else 'Sarawak'
        if lat > 5:
            return 'Kelantan' if lon > 101.5 else 'Kedah'
        if lat < 2:
            return 'Johor'
        if lon > 103:
            return 'Pahang' if lat > 3 else 'Johor'
        return 'Perak' if lat > 3.5 else 'Selangor'

    # ── Mexico (remaining without state in name) ──
    if country == 'Mexico':
        return province_from_coords_mexico(name, lat, lon)

    # ── Mozambique ──
    if country == 'Mozambique':
        if lat < -20:
            return 'Maputo' if lat < -25 else 'Inhambane'
        return 'Cabo Delgado'

    # ── Nigeria ──
    if country == 'Nigeria':
        return 'Lagos'

    # ── Oman ──
    if country == 'Oman':
        if lat < 18:
            return 'Dhofar'
        if lat < 22:
            return 'Al Sharqiyah'
        return 'Muscat'

    # ── Panama ──
    if country == 'Panama':
        if lon < -82:
            return 'Chiriqu\xed'
        if lon < -80:
            return 'Panam\xe1'
        return 'Guna Yala' if lat > 9.3 else 'Panam\xe1'

    # ── Papua New Guinea ──
    if country == 'Papua New Guinea':
        return 'Papua New Guinea'

    # ── Peru ──
    if country == 'Peru':
        if lat < -16:
            return 'Arequipa'
        if lat < -13:
            return 'Ica'
        if lat < -10:
            return 'Lima'
        if lat < -6:
            return 'Piura'
        return 'Piura'

    # ── Philippines ──
    if country == 'Philippines':
        if lat > 16:
            return 'Ilocos'
        if lat > 14:
            return 'Luzon'
        if lat > 10:
            return 'Visayas'
        return 'Mindanao'

    # ── South Africa leftover (Marion Island etc.) ──
    if country == 'South Africa':
        if lat < -40:
            return 'Prince Edward Islands'
        if lon < 20:
            return 'Western Cape'
        if lon < 28:
            return 'Eastern Cape'
        return 'KwaZulu-Natal'

    # ── Tanzania ──
    if country == 'Tanzania':
        return 'Tanzania'

    # ── Thailand ──
    if country == 'Thailand':
        return 'Thailand'

    # ── Vietnam ──
    if country == 'Vietnam':
        if lat > 16:
            return 'Central Vietnam'
        if lat > 10:
            return 'South Central Vietnam'
        return 'Southern Vietnam'

    # ── Sweden leftover ──
    if country == 'Sweden':
        return 'Halland'

    # ── France leftover ──
    if country == 'France':
        return province_from_coords_france(name, lat, lon)

    # ── Italy leftover ──
    if country == 'Italy':
        return province_from_coords_italy(name, lat, lon)

    # ── Spain leftover ──
    if country == 'Spain':
        return province_from_coords_spain(name, lat, lon)

    return None


# ─── Main province determination ─────────────────────────────────────────

def determine_province(name, country, lat, lon):
    """Main dispatcher to determine province."""

    # First try to get it from the station name
    prov = province_from_name(name, country, lat, lon)
    if prov:
        return prov

    # Then try coordinate-based classification
    if country == 'Germany':
        return province_from_coords_germany(name, lat, lon)
    if country == 'Japan':
        # Many Japan stations have prefecture in name
        parts = [p.strip() for p in name.split(',')]
        if len(parts) >= 3:
            return parts[-2].strip()
        return province_from_coords_japan(name, lat, lon)
    if country == 'Netherlands':
        return province_from_coords_netherlands(name, lat, lon)
    if country == 'Denmark':
        return province_from_coords_denmark(name, lat, lon)
    if country == 'France':
        return province_from_coords_france(name, lat, lon)
    if country == 'Italy':
        return province_from_coords_italy(name, lat, lon)
    if country == 'Sweden':
        return province_from_coords_sweden(name, lat, lon)
    if country == 'Norway':
        return province_from_coords_norway(name, lat, lon)
    if country == 'Mexico':
        return province_from_coords_mexico(name, lat, lon)
    if country == 'Spain':
        return province_from_coords_spain(name, lat, lon)
    if country == 'Portugal':
        return province_from_coords_portugal(name, lat, lon)
    if country == 'New Zealand':
        return province_from_coords_nz(name, lat, lon)
    if country == 'South Africa':
        # Coordinate-based for those without province in name
        if lon < 18:
            return 'Western Cape'
        if lon < 26:
            return 'Western Cape'
        if lon < 30:
            return 'Eastern Cape'
        return 'KwaZulu-Natal'
    if country == 'Ireland':
        # Irish stations don't have province in name, use coordinates
        if lat > 53.5:
            return 'Connacht' if lon < -8 else 'Ulster' if lon < -6 else 'Leinster'
        if lon < -8.5:
            return 'Munster' if lat < 52.5 else 'Connacht'
        if lat < 52.5:
            return 'Munster'
        return 'Leinster'

    # For Estonia, Poland, Finland, Bulgaria etc.
    if country == 'Estonia':
        return 'Estonia'
    if country == 'Poland':
        return 'Poland'
    if country == 'Finland':
        return 'Finland'
    if country == 'Bulgaria':
        return 'Bulgaria'
    if country == 'Belgium':
        if lon < 3.5:
            return 'West-Vlaanderen'
        return 'Oost-Vlaanderen'
    if country == 'Croatia':
        return 'Croatia'
    if country == 'Turkey':
        return 'Turkey'
    if country == 'Russia':
        return 'Russia'
    if country == 'Antarctica':
        return 'Antarctica'

    # For remaining countries with few stations
    return province_from_coords_generic(name, country, lat, lon)


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    with open(INPUT_FILE, encoding='iso-8859-1') as f:
        lines = f.readlines()

    # Parse stations and determine provinces
    new_lines = []
    total_stations = 0
    assigned = 0
    unassigned = []

    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)

        # Check if this is a country line
        if line.startswith('# country:'):
            country = line.split(':', 1)[1].strip()

            # Check if next line is already a province line
            if i + 1 < len(lines) and lines[i + 1].startswith('# province:'):
                i += 1
                continue

            # We need to find the station name and coordinates
            # Look ahead to find lat, lon, and station name
            lat = lon = None
            name = None
            j = i + 1
            while j < len(lines):
                l = lines[j]
                if l.startswith('# !latitude:'):
                    try:
                        lat = float(l.split(':', 1)[1].strip())
                    except ValueError:
                        pass
                elif l.startswith('# !longitude:'):
                    try:
                        lon = float(l.split(':', 1)[1].strip())
                    except ValueError:
                        pass
                elif l.strip() and not l.startswith('#') and not l.startswith(' '):
                    name = l.strip()
                    break
                j += 1

            total_stations += 1

            if name and lat is not None:
                prov = determine_province(name, country, lat, lon)
                if prov:
                    new_lines.append(f'# province: {prov}\n')
                    assigned += 1
                else:
                    unassigned.append((name, country, lat, lon))
            else:
                unassigned.append((name or '???', country, lat, lon))

        i += 1

    # Write output
    with open(OUTPUT_FILE, 'w', encoding='iso-8859-1') as f:
        f.writelines(new_lines)

    # Summary
    print(f'Total stations: {total_stations}')
    print(f'Province assigned: {assigned}')
    print(f'Province NOT assigned: {len(unassigned)}')

    if unassigned:
        print(f'\n--- Stations without province ({len(unassigned)}) ---')
        for name, country, lat, lon in sorted(unassigned, key=lambda x: (x[1], x[0] or '')):
            lat_s = f'{lat:.3f}' if lat is not None else '?'
            lon_s = f'{lon:.3f}' if lon is not None else '?'
            print(f'  [{country}] {lat_s}, {lon_s}  {name}')


if __name__ == '__main__':
    main()
