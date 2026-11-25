#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windvorhersage an Thermik- und Surfrevieren gegen Messungen (24.11.2026).

Vergleicht die alten Vorhersagelaeufe (Open-Meteo Historical Forecast API: je Stunde der juengste Lauf, also kurze
Vorlaufzeit) aller verfuegbaren Modelle mit gemessenem Wind am Revier, Mai-September 2026, und prueft, wie viel eine
statistische Korrektur je Revier bringt (Kreuzvalidierung ueber Monate: Korrektur aus vier Monaten, Test am fuenften).

Messquellen (quellen/thermik/):
  synop/<wmo-id>.jsonl   IEM-Archiv der WMO-SYNOP/BUFR-Meldungen (UTC, Wind in kn) - quellen/thermik/synop_laden.py
  meteoschweiz/          MeteoSchweiz Open Data SwissMetNet, Stundenmittel (UTC, m/s)
  lombardia/<id>.json    ARPA Lombardia (dati.lombardia.it 647i-nhxk), 10-min-Werte (m/s, Zeit = MEZ ohne Sommerzeit)
  suedtirol/             Landeswetterdienst Suedtirol (geoservices.buergernetz.bz.it/services/meteo/v1), 10 min (m/s)
  geosphere/<id>.csv     GeoSphere Austria Data Hub klima-v2-10min (CC BY 4.0), ffam/dd, UTC - geosphere_laden.py
  meteotrentino/         Meteotrentino-Archiv (storico.meteotrentino.it, Hydstra), 10 min, m/s, MEZ ohne Sommerzeit
                         (geprueft: Strahlungsschwerpunkt + Kreuzkorrelation mit Limone) - meteotrentino_laden.py
  pioupiou/<id>.csv      Pioupiou/OpenWindMap-Archiv (km/h, ~5 min, UTC) - pioupiou_laden.py; Anemometer oft niedrig
  (Stationen am Spot ueber iwind.at/map gefunden; iWind selbst sperrt Abrufe, Daten daher bei der Originalquelle)

  venv/bin/python py/thermik_pruefung.py [revier,...]
      -> harmonics/help/thermik_pruefung.csv (je Revier und Modell)
"""
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, 'quellen', 'thermik')
AUS = os.path.join(ROOT, 'harmonics', 'help', 'thermik_pruefung.csv')
KARTE = os.path.join(ROOT, 'static', 'wind_stations', 'wind_stations.json')   # Karte: Menue + Marker
VON, BIS = '2026-05-01', '2026-09-30'
MS_KN = 1.943844

MODELLE = ['icon_d2', 'icon_eu', 'meteoswiss_icon_ch1', 'meteoswiss_icon_ch2', 'meteofrance_arome_france_hd',
           'meteofrance_arome_france', 'italia_meteo_arpae_icon_2i', 'knmi_harmonie_arome_europe',
           'dmi_harmonie_arome_europe', 'ukmo_uk_deterministic_2km', 'metno_nordic', 'ecmwf_ifs',
           'ukmo_global_deterministic_10km', 'gfs_global', 'gfs_hrrr', 'ncep_nbm_conus', 'bom_access_global', 'best_match']
KURZ = {'icon_d2': 'ICON-D2 2,2', 'icon_eu': 'ICON-EU 7', 'meteoswiss_icon_ch1': 'ICON-CH1 1',
        'meteoswiss_icon_ch2': 'ICON-CH2 2', 'meteofrance_arome_france_hd': 'AROME-HD 1,3',
        'meteofrance_arome_france': 'AROME 2,5', 'italia_meteo_arpae_icon_2i': 'ICON-2I 2,2',
        'knmi_harmonie_arome_europe': 'HARMONIE-KNMI 5,5', 'dmi_harmonie_arome_europe': 'HARMONIE-DMI 2',
        'ukmo_uk_deterministic_2km': 'UKV 2', 'metno_nordic': 'MET-Nordic 1', 'ecmwf_ifs': 'ECMWF 9',
        'ukmo_global_deterministic_10km': 'UKMO 10', 'gfs_global': 'GFS 13', 'gfs_hrrr': 'HRRR 3', 'ncep_nbm_conus': 'NBM 2,5 (NOAA-Korrektur)', 'bom_access_global': 'BOM ACCESS 12', 'best_match': 'Open-Meteo best_match'}

# station (echter Name), zeitzone, quelle, kennung, lat, lon, bemerkung, spot (Revier, auf das sie sich bezieht)
# 25.11.2026 (Oliver): nur Stationen AM Spot; ferne Ersatzstationen entfernt, weil sie den Spotwind nicht zeigen:
#   Grosseto (Talamone, 20 km), Figari + Olbia (Porto Pollo, 36-39 km), Perpignan (Leucate, 24 km -> LEUCATE),
#   Hvar (Bol, 10+ km), Split Marjan (122 m), Sal Flughafen (Santa Maria 15 km), Fortaleza (Cumbuco 25 km),
#   Kapstadt Flughafen (22 km landein), Perth Flughafen (15 km landein), Miami KMIA (10 km landein),
#   Southampton EGHI (10 km landein), Oberpfaffenhofen (zwischen den Seen), 4S2 Hood River (nicht repraesentativ).
#   Kaum Gleitwind gemessen (< 5 h >= 12 kn Mai-Sep 2026, Station sieht den Spotwind nicht): Colico, Costa Volpino,
#   Laveno-Mombello, Pully, St. Wolfgang, Altmuenster.
#   Leer gebliebene MesoWest-Stationen (519PG, TCICA, GGBC1, NDBC44063, APAM2, 0234W) ebenfalls entfernt.
# Kennungen der CSV-Netze: Praefix + Stations-ID (mf/dwd/knmi/dmi/coops), Daten quellen/thermik/<netz>/<id>.csv
REVIERE = [
    # --- Alpen & Seen
    ('Segl-Maria', 'Europe/Zurich', 'meteoschweiz', 'SIA', 46.432331, 9.762325, 'MeteoSchweiz', 'Silvaplana/Sils (Malojawind)'),
    ('St. Valentin auf der Haide', 'Europe/Rome', 'suedtirol', '02200MS', 46.7759, 10.5289, 'Wetterdienst Südtirol', 'Reschensee'),
    ('Torbole (Belvedere)', 'Europe/Rome', 'meteotrentino', 'T0193', 45.870095, 10.877355, 'Meteotrentino, 90 m', 'Gardasee Nord (Torbole)'),
    ('Limone sul Garda', 'Europe/Rome', 'lombardia', '14065:14066', 45.80683, 10.79006, 'ARPA Lombardia', 'Gardasee Nord (Limone)'),
    ('Toscolano-Maderno', 'Europe/Rome', 'lombardia', '14099:14100', 45.6364, 10.6169, 'ARPA Lombardia', 'Gardasee West (Toscolano/Campione)'),
    ('Manerba del Garda Dusano', 'Europe/Rome', 'lombardia', '14783:14782', 45.5437, 10.5666, 'ARPA Lombardia', 'Gardasee Süd-West (Manerba)'),
    ('Tavernola Bergamasca Gallinarga', 'Europe/Rome', 'lombardia', '17454:17456', 45.6963, 10.0542, 'ARPA Lombardia', 'Iseosee'),
    ('Magadino/Cadenazzo', 'Europe/Zurich', 'meteoschweiz', 'MAG', 46.160025, 8.933672, 'MeteoSchweiz, Ebene am Nordende', 'Lago Maggiore Nord'),
    ('Güttingen', 'Europe/Zurich', 'meteoschweiz', 'GUT', 47.601733, 9.279428, 'MeteoSchweiz', 'Bodensee'),
    ('Konstanz', 'Europe/Berlin', 'dwd', 'dwd02712', 47.6952, 9.1307, 'DWD 10 min', 'Bodensee (Konstanz)'),
    ('Friedrichshafen', 'Europe/Berlin', 'dwd', 'dwd01490', 47.6454, 9.4795, 'DWD 10 min', 'Bodensee (Friedrichshafen)'),
    ('Lindau', 'Europe/Berlin', 'dwd', 'dwd06102', 47.5396, 9.6843, 'DWD 10 min', 'Bodensee (Lindau)'),
    ('Chieming', 'Europe/Berlin', 'dwd', 'dwd00856', 47.8843, 12.5404, 'DWD 10 min', 'Chiemsee'),
    ('Altmühlsee', 'Europe/Berlin', 'dwd', 'dwd06096', 49.1423, 10.7301, 'DWD 10 min', 'Altmühlsee'),
    ('Waren (Müritz)', 'Europe/Berlin', 'dwd', 'dwd05349', 53.5196, 12.6654, 'DWD 10 min', 'Müritz'),
    ('Neusiedl am See', 'Europe/Vienna', 'synop', '0-40-0-72', None, None, 'SYNOP', 'Neusiedler See Nord'),
    ('Podersdorf Strandbad', 'Europe/Vienna', 'geosphere', 'gs7912', 47.86611, 16.83444, 'GeoSphere', 'Neusiedler See (Podersdorf)'),
    ('Achenkirch', 'Europe/Vienna', 'geosphere', 'gs8806', 47.49944, 11.70667, 'GeoSphere, Nordende', 'Achensee'),
    # --- Nordsee & Ostsee
    ('List auf Sylt', 'Europe/Berlin', 'dwd', 'dwd03032', None, None, 'DWD 10 min', 'Sylt'),
    ('Sankt Peter-Ording', 'Europe/Berlin', 'dwd', 'dwd04393', None, None, 'DWD 10 min', 'St. Peter-Ording'),
    ('Büsum', 'Europe/Berlin', 'dwd', 'dwd00788', None, None, 'DWD 10 min', 'Büsum'),
    ('Föhr', 'Europe/Berlin', 'dwd', 'dwd19243', None, None, 'DWD 10 min', 'Föhr'),
    ('Norderney', 'Europe/Berlin', 'dwd', 'dwd03631', None, None, 'DWD 10 min', 'Norderney'),
    ('Borkum-Süderstraße', 'Europe/Berlin', 'dwd', 'dwd00619', None, None, 'DWD 10 min', 'Borkum'),
    ('Fehmarn', 'Europe/Berlin', 'dwd', 'dwd05516', None, None, 'DWD 10 min (Westermarkelsdorf)', 'Fehmarn Nord'),
    ('Putlos', 'Europe/Berlin', 'dwd', 'dwd05877', None, None, 'DWD 10 min', 'Heiligenhafen/Graswarder'),
    ('Schönhagen (Ostseebad)', 'Europe/Berlin', 'dwd', 'dwd05930', None, None, 'DWD 10 min', 'Schönhagen/Damp'),
    ('Pelzerhaken', 'Europe/Berlin', 'dwd', 'dwd03897', None, None, 'DWD 10 min', 'Neustädter Bucht'),
    ('Boltenhagen', 'Europe/Berlin', 'dwd', 'dwd00596', None, None, 'DWD 10 min', 'Boltenhagen'),
    ('Rostock-Warnemünde', 'Europe/Berlin', 'dwd', 'dwd04271', None, None, 'DWD 10 min', 'Warnemünde'),
    ('IJmuiden', 'Europe/Amsterdam', 'knmi', 'knmi225', None, None, 'KNMI', 'IJmuiden'),
    ('Hoek van Holland', 'Europe/Amsterdam', 'knmi', 'knmi330', None, None, 'KNMI', 'Hoek van Holland'),
    ('Cadzand', 'Europe/Amsterdam', 'knmi', 'knmi308', None, None, 'KNMI', 'Cadzand'),
    ('Vlissingen', 'Europe/Amsterdam', 'knmi', 'knmi310', None, None, 'KNMI', 'Vlissingen'),
    ('Stavenisse', 'Europe/Amsterdam', 'knmi', 'knmi324', None, None, 'KNMI', 'Oosterschelde'),
    ('Stavoren', 'Europe/Amsterdam', 'knmi', 'knmi267', None, None, 'KNMI', 'IJsselmeer (Stavoren)'),
    ('Houtribdijk', 'Europe/Amsterdam', 'knmi', 'knmi258', None, None, 'KNMI, Damm', 'Markermeer/IJsselmeer (Lelystad)'),
    ('Lauwersoog', 'Europe/Amsterdam', 'knmi', 'knmi277', None, None, 'KNMI', 'Lauwersoog'),
    ('Hoorn (Terschelling)', 'Europe/Amsterdam', 'knmi', 'knmi251', None, None, 'KNMI', 'Terschelling'),
    ('Torsminde', 'Europe/Copenhagen', 'dmi', 'dmi06055', None, None, 'DMI 10 min', 'Torsminde'),
    ('Hvide Sande', 'Europe/Copenhagen', 'dmi', 'dmi06058', None, None, 'DMI 10 min', 'Hvide Sande/Ringkøbing Fjord'),
    ('Kegnæs Fyr', 'Europe/Copenhagen', 'dmi', 'dmi06119', None, None, 'DMI 10 min', 'Kegnæs/Sydals'),
    ('Skagen Fyr', 'Europe/Copenhagen', 'dmi', 'dmi06041', None, None, 'DMI 10 min', 'Skagen'),
    ('Københavns Lufthavn', 'Europe/Copenhagen', 'dmi', 'dmi06180', None, None, 'DMI 10 min', 'Amager Strand'),
    # --- Frankreich (Météo-France, stündlich)
    ('Dunkerque', 'Europe/Paris', 'meteofrance', 'mf59183001', None, None, 'Météo-France', 'Dunkerque'),
    ('Cap Gris-Nez', 'Europe/Paris', 'meteofrance', 'mf62054001', None, None, 'Météo-France, 48 m', 'Wissant'),
    ('Granville', 'Europe/Paris', 'meteofrance', 'mf50218001', None, None, 'Météo-France', 'Granville'),
    ('Gouville', 'Europe/Paris', 'meteofrance', 'mf50215002', None, None, 'Météo-France', 'Gouville-sur-Mer'),
    ('Brignogan', 'Europe/Paris', 'meteofrance', 'mf29021001', None, None, 'Météo-France', 'Brignogan-Plages'),
    ('Plougonvelin', 'Europe/Paris', 'meteofrance', 'mf29190001', None, None, 'Météo-France', 'Trez Hir'),
    ('Pointe de Penmarc\'h', 'Europe/Paris', 'meteofrance', 'mf29158001', None, None, 'Météo-France', 'La Torche'),
    ('Quiberon (Flugplatz)', 'Europe/Paris', 'meteofrance', 'mf56186003', None, None, 'Météo-France', 'Quiberon/Penthièvre'),
    ('Saint-Clément-des-Baleines', 'Europe/Paris', 'meteofrance', 'mf17318001', None, None, 'Météo-France', 'Île de Ré Nord'),
    ('Royan-Médis', 'Europe/Paris', 'meteofrance', 'mf17306004', None, None, 'Météo-France', 'Royan'),
    ('Leucate', 'Europe/Paris', 'meteofrance', 'mf11202001', None, None, 'Météo-France, 42 m', 'Leucate (La Franqui)'),
    ('Leucate Aéromodélisme', 'Europe/Paris', 'pioupiou', 'pp1538', None, None, 'Pioupiou, Plateau', 'Leucate'),
    ('Gruissan Étang de Mateille', 'Europe/Paris', 'pioupiou', 'pp602', None, None, 'Pioupiou', 'Gruissan'),
    ('L\'Espiguette', 'Europe/Paris', 'meteofrance', 'mf30133005', None, None, 'Météo-France', 'Port-Camargue/Espiguette'),
    ('Cap Couronne', 'Europe/Paris', 'meteofrance', 'mf13056002', None, None, 'Météo-France', 'Carro/La Couronne'),
    ('Hyères Le Palyvestre (Flughafen)', 'Europe/Paris', 'metar', 'LFTH', None, None, 'METAR', 'Hyères'),
    ('La Capte (CAPT\'ain NAUTIC)', 'Europe/Paris', 'pioupiou', 'pp2133', None, None, 'Pioupiou', 'Hyères Almanarre'),
    ('Fréjus', 'Europe/Paris', 'meteofrance', 'mf83061001', None, None, 'Météo-France', 'Fréjus'),
    ('Vauclin', 'America/Martinique', 'meteofrance', 'mf97232003', None, None, 'Météo-France', 'Martinique: Le Vauclin/Pointe Faula'),
    # Saint-François Flugplatz (Guadeloupe, mf97125011): im Passat Mittel 5,6 kn, max 13,6 -> abgeschirmt/defekt, raus
    ('Pierrefonds (Flughafen)', 'Indian/Reunion', 'meteofrance', 'mf97416463', None, None, 'Météo-France', 'Réunion: Saint-Pierre'),
    # --- Mittelmeer (sonst)
    ('Tarifa', 'Europe/Madrid', 'synop', '0-724-0-458', None, None, 'SYNOP', 'Tarifa'),
    ('Trapani-Birgi (Flughafen)', 'Europe/Rome', 'synop', '0-380-0-429', None, None, 'SYNOP', 'Lo Stagnone'),
    ('Rhodos Diagoras (Flughafen)', 'Europe/Athens', 'synop', '0-300-0-749', None, None, 'SYNOP', 'Rhodos Ialysos'),
    ('Kos Hippokrates (Flughafen)', 'Europe/Athens', 'synop', '0-300-0-742', None, None, 'SYNOP', 'Kos Marmari'),
    ('Karpathos (Flughafen)', 'Europe/Athens', 'synop', '0-300-0-765', None, None, 'SYNOP', 'Karpathos Gun Bay'),
    ('Naxos (Flughafen)', 'Europe/Athens', 'metar', 'LGNX', None, None, 'METAR; SYNOP 0-300-0-732 im IEM-Archiv leer', 'Naxos Mikri Vigla'),
    ('Paros (Flughafen)', 'Europe/Athens', 'synop', '0-300-0-766', None, None, 'SYNOP', 'Paros'),
    ('Palma Son Sant Joan (Flughafen)', 'Europe/Madrid', 'metar', 'LEPA', None, None, 'METAR', 'Bucht von Palma (Embat)'),
    ('Barcelona El Prat (Flughafen)', 'Europe/Madrid', 'metar', 'LEBL', None, None, 'METAR', 'Barcelona (Seewind)'),
    ('Hurghada (Flughafen)', 'Africa/Cairo', 'synop', '0-818-0-463', None, None, 'SYNOP', 'Hurghada'),
    # --- Atlantik, Afrika, Indik
    ('Dakhla (Flughafen)', 'Africa/El_Aaiun', 'metar', 'GMMH', None, None, 'METAR', 'Dakhla Lagune'),
    ('Essaouira (Mogador)', 'Africa/Casablanca', 'ogimet', '60220', 31.51, -9.78, 'SYNOP aus OGIMET, 3-stündlich', 'Essaouira'),
    ('Boa Vista Rabil (Flughafen)', 'Atlantic/Cape_Verde', 'metar', 'GVBA', None, None, 'METAR, nur 7-19 UTC; Hauptsaison Winter', 'Boa Vista: Sal Rei'),
    ('Teneriffa Süd (Flughafen)', 'Atlantic/Canary', 'metar', 'GCTS', None, None, 'METAR', 'El Médano'),
    ('Gran Canaria (Flughafen Gando)', 'Atlantic/Canary', 'metar', 'GCLP', None, None, 'METAR', 'Pozo Izquierdo'),
    ('Plaisance (Flughafen)', 'Indian/Mauritius', 'metar', 'FIMP', None, None, 'METAR', 'Mauritius: Pointe d\'Esny'),
    ('Sydney Kingsford Smith (Flughafen)', 'Australia/Sydney', 'metar', 'YSSY', None, None, 'METAR', 'Botany Bay'),
    # --- Nordamerika & Karibik
    ('Barbados Grantley Adams (Flughafen)', 'America/Barbados', 'metar', 'TBPB', None, None, 'METAR', 'Barbados Silver Rock'),
    ('San Francisco (Flughafen SFO)', 'America/Los_Angeles', 'metar', 'KSFO', None, None, 'METAR', 'SF-Bucht Coyote Point/3rd Ave'),
    ('Fort Point (FTPC1)', 'America/Los_Angeles', 'ndbc', 'ftpc1', 37.806, -122.466, 'NDBC', 'Golden Gate/Crissy Field'),
    ('Alameda (AAMC1)', 'America/Los_Angeles', 'ndbc', 'aamc1', 37.772, -122.300, 'NDBC', 'Alameda Crown Beach'),
    ('Port Chicago (PCOC1)', 'America/Los_Angeles', 'ndbc', 'pcoc1', 38.056, -122.039, 'NDBC', 'Suisun Bay'),
    ('Hood River (HOXO)', 'America/Los_Angeles', 'mesowest', 'HOXO', None, None, 'MesoWest, Wasser', 'Columbia Gorge Hood River'),
    ('Annapolis (Naval Academy)', 'America/New_York', 'metar', 'NAK', None, None, 'METAR', 'Chesapeake Bay Annapolis'),
    ('Thomas Point Leuchtturm (TPLM2)', 'America/New_York', 'ndbc', 'tplm2', 38.899, -76.436, 'NDBC', 'Chesapeake Bay'),
    ('San Francisco Presidio (CO-OPS 9414290)', 'America/Los_Angeles', 'coops', 'coops9414290', None, None, 'NOAA CO-OPS', 'Crissy Field'),
    ('Angels Gate (CO-OPS 9410647)', 'America/Los_Angeles', 'coops', 'coops9410647', None, None, 'NOAA CO-OPS, Wellenbrecher', 'Cabrillo Beach (San Pedro)'),
    ('Kahului Harbor (CO-OPS 1615680)', 'Pacific/Honolulu', 'coops', 'coops1615680', None, None, 'NOAA CO-OPS', 'Maui: Kanaha'),
    ('S. Bird Island (CO-OPS 8776139)', 'America/Chicago', 'coops', 'coops8776139', None, None, 'NOAA CO-OPS', 'Bird Island Basin (Padre Island)'),
    ('Packery Channel (CO-OPS 8775792)', 'America/Chicago', 'coops', 'coops8775792', None, None, 'NOAA CO-OPS', 'Corpus Christi Packery'),
    ('South Padre Island CG Station (CO-OPS 8779748)', 'America/Chicago', 'coops', 'coops8779748', None, None, 'NOAA CO-OPS', 'South Padre Island'),
    ('Oregon Inlet Marina (CO-OPS 8652587)', 'America/New_York', 'coops', 'coops8652587', None, None, 'NOAA CO-OPS', 'Outer Banks Nord (Pea Island)'),
    ('Duck (CO-OPS 8651370)', 'America/New_York', 'coops', 'coops8651370', None, None, 'NOAA CO-OPS, Pier', 'Outer Banks Duck'),
    ('USCG Station Hatteras (CO-OPS 8654467)', 'America/New_York', 'coops', 'coops8654467', None, None, 'NOAA CO-OPS', 'Hatteras'),
    ('Virginia Key (VAKF1)', 'America/New_York', 'ndbc', 'vakf1', 25.731, -80.162, 'NDBC', 'Miami Virginia Key'),
]


def _metar(icao):
    d = pd.read_csv(os.path.join(Q, 'metar', icao + '.csv'), comment='#')
    d['t'] = pd.to_datetime(d['valid'], utc=True)
    return d


CSV_NETZE = {'meteofrance': 'mf', 'dwd': 'dwd', 'knmi': 'knmi', 'dmi': 'dmi', 'coops': 'coops'}


def _csv_id(quelle, kenn):
    return kenn[len(CSV_NETZE[quelle]):]


def _katalog_ort(quelle, kenn):
    k = pd.read_csv(os.path.join(Q, 'spotsuche', 'stationen_alle.csv'), dtype={'id': str})
    i = _csv_id(quelle, kenn)
    z = k[(k['netz'] == quelle) & ((k['id'] == i) | (k['id'].str.lstrip('0') == i.lstrip('0')))]
    if not len(z) and quelle == 'meteofrance':
        k = pd.read_csv(os.path.join(Q, 'spotsuche', 'stationen_meteofrance.csv'), dtype={'id': str})
        z = k[k['id'] == i]
    return float(z['lat'].iloc[0]), float(z['lon'].iloc[0])


def _synop_ort(sid):
    for q, pre in CSV_NETZE.items():
        if sid.startswith(pre) and os.path.exists(os.path.join(Q, q, sid[len(pre):] + '.csv')):
            return _katalog_ort(q, sid)
    st = json.load(open(os.path.join(Q, 'synoptic_stationen.json')))
    for v in st.values():
        for x in v['stationen']:
            if x['stid'] == sid:
                return x['lat'], x['lon']
    if sid.startswith('pp'):
        d = _pioupiou(sid)
        return float(d['lat'].median()), float(d['lon'].median())
    if not sid.startswith('0-'):
        d = _metar(sid)
        return float(d['lat'].iloc[0]), float(d['lon'].iloc[0])
    for f in json.load(open(os.path.join(Q, 'iem_wmo.json')))['features']:
        if f['properties']['sid'] == sid:
            lo, la = f['geometry']['coordinates']
            return la, lo
    raise KeyError(sid)


def _pioupiou(kenn):
    """Pioupiou-Reihe, nur am letzten Standort (Stationen ziehen um: 602 stand bis 2.5.2026 in Leucate)."""
    d = pd.read_csv(os.path.join(Q, 'pioupiou', kenn[2:] + '.csv'))
    la, lo = d['lat'].iloc[-1], d['lon'].iloc[-1]
    return d[((d['lat'] - la).abs() < 0.01) & ((d['lon'] - lo).abs() < 0.01)]


def _vektor_stunde(t, sp, ri, zentriert=True, mindest=4):
    """10-min-Werte -> Stundenwerte zur vollen Stunde (Mittel aus -30..+30 min), Richtung als Vektor."""
    d = pd.DataFrame({'u': -sp * np.sin(np.radians(ri)), 'v': -sp * np.cos(np.radians(ri)), 'sp': sp}, index=t)
    d.index = d.index + pd.Timedelta(minutes=30 if zentriert else 0)
    h = d.resample('1h', label='left').mean()
    h = h[d['sp'].resample('1h', label='left').count() >= mindest]
    return pd.DataFrame({'sp': h['sp'], 'ri': np.degrees(np.arctan2(-h['u'], -h['v'])) % 360})


def messung(r):
    name, tz, quelle, kenn = r[:4]
    if quelle == 'synop':
        zeilen = []
        for z in open(os.path.join(Q, 'synop', kenn + '.jsonl')):
            for t, sp, ri, _g in json.loads(z)['obs']:
                if sp is not None and t.endswith(':00Z'):
                    zeilen.append((pd.Timestamp(t), sp, ri if ri is not None else np.nan))
        d = pd.DataFrame(zeilen, columns=['t', 'sp', 'ri']).drop_duplicates('t').set_index('t').sort_index()
        d.loc[d['sp'] == 0, 'ri'] = np.nan
        return d
    if quelle == 'ogimet':                                     # OGIMET-SYNOP (ogimet_laden.py), kn
        d = pd.read_csv(os.path.join(Q, 'ogimet', kenn + '.csv'))
        d = pd.DataFrame({'sp': d['kn'].astype(float).values, 'ri': pd.to_numeric(d['grad'], errors='coerce').values},
                         index=pd.to_datetime(d['zeit_utc'], utc=True))
        d.loc[d['sp'] == 0, 'ri'] = np.nan
        return d
    if quelle == 'metar':
        d = _metar(kenn).dropna(subset=['sknt'])
        d['h'] = d['t'].dt.round('1h')
        d['ab'] = (d['t'] - d['h']).abs()
        d = d[d['ab'] <= pd.Timedelta(minutes=15)].sort_values('ab').drop_duplicates('h').set_index('h').sort_index()
        out = pd.DataFrame({'sp': d['sknt'].astype(float), 'ri': pd.to_numeric(d['drct'], errors='coerce')})
        out.loc[out['sp'] == 0, 'ri'] = np.nan
        return out
    if quelle == 'mesowest':
        d = pd.read_csv(os.path.join(Q, 'mesowest', kenn + '.csv'), header=None, names=['t', 'sp', 'ri'],
                        comment='#', dtype=str)
        d = d[d['ri'].notna() & ~d['ri'].str.startswith('#')]
        d['sp'], d['ri'] = pd.to_numeric(d['sp'], errors='coerce'), pd.to_numeric(d['ri'], errors='coerce')
        d = d.dropna()
        d = d[(d['sp'] >= 0) & (d['sp'] < 100) & (d['ri'] >= 0) & (d['ri'] <= 360)]
        t = pd.to_datetime(d['t']).dt.tz_localize('UTC')
        d = d.set_index(t)
        d = d[~d.index.duplicated()].sort_index()
        return _vektor_stunde(d.index, d['sp'].values, d['ri'].values, mindest=2)
    if quelle == 'ndbc':
        d = pd.read_csv(os.path.join(Q, 'ndbc', kenn + '.txt'), sep=r'\s+', header=None, usecols=range(7),
                        names=['Y', 'M', 'D', 'h', 'mi', 'ri', 'sp'])
        d = d[(d['sp'] < 90) & (d['ri'] <= 360)]
        t = pd.to_datetime(dict(year=d['Y'], month=d['M'], day=d['D'], hour=d['h'], minute=d['mi']), utc=True)
        d = d.set_index(t).sort_index()
        d = d[~d.index.duplicated()]
        if pd.Series(d.index).diff().median() >= pd.Timedelta(minutes=30):          # stuendlich (C-MAN)
            d.index = d.index.round('1h')
            return pd.DataFrame({'sp': d['sp'] * MS_KN, 'ri': d['ri'].astype(float)})
        return _vektor_stunde(d.index, d['sp'].values * MS_KN, d['ri'].values)
    if quelle == 'meteoschweiz':
        fs = [os.path.join(Q, 'meteoschweiz', 'ogd-smn_%s_h_%s.csv' % (kenn.lower(), x))
              for x in ('historical_2020-2029', 'recent')]
        d = pd.concat([pd.read_csv(f, sep=';', usecols=['reference_timestamp', 'fkl010h0', 'dkl010h0']) for f in fs])
        d['t'] = pd.to_datetime(d['reference_timestamp'], format='%d.%m.%Y %H:%M', utc=True)
        # Stundenmittel: Zeitstempel = Beginn des Intervalls (MeteoSchweiz OGD) -> Mitte = +30 min, auf volle Stunde
        # gerundet nach dem Lag-Test unten (zeit_lag) entschieden
        d = d.drop_duplicates('t').set_index('t').sort_index()
        return pd.DataFrame({'sp': d['fkl010h0'] * MS_KN, 'ri': d['dkl010h0']})
    if quelle == 'lombardia':
        isp, iri = kenn.split(':')
        a = pd.DataFrame(json.load(open(os.path.join(Q, 'lombardia', isp + '.json'))))
        b = pd.DataFrame(json.load(open(os.path.join(Q, 'lombardia', iri + '.json'))))
        # je Zeitpunkt zwei Zeilen: idoperatore 1 = 10-min-Mittel, 3 = Maximum (Boe); bis 25.11.2026 nahm der Code
        # die jeweils erste Zeile -> ~16 % Boeen in Limone/Colico
        a = a[(a['stato'] == 'VA') & (a['idoperatore'] == '1')].set_index('data')['valore'].astype(float)
        b = b[(b['stato'] == 'VA') & (b['idoperatore'] == '1')].set_index('data')['valore'].astype(float)
        a, b = a[a >= 0], b[(b >= 0) & (b <= 360)]
        a, b = a[~a.index.duplicated()], b[~b.index.duplicated()]
        j = pd.concat([a.rename('sp'), b.rename('ri')], axis=1).dropna()
        t = pd.to_datetime(j.index) - pd.Timedelta(hours=1)          # MEZ (UTC+1, ganzjaehrig) -> UTC
        t = t.tz_localize('UTC')
        return _vektor_stunde(t, j['sp'].values * MS_KN, j['ri'].values)
    if quelle == 'suedtirol':
        sp = pd.DataFrame(json.load(open(os.path.join(Q, 'suedtirol', kenn + '_WG.json'))))
        ri = pd.DataFrame(json.load(open(os.path.join(Q, 'suedtirol', kenn + '_WR.json'))))
        def zeit(s):
            off = s.str.endswith('CEST').map({True: 2, False: 1})
            return pd.to_datetime(s.str.replace('CEST', '').str.replace('CET', '')) - pd.to_timedelta(off, 'h')
        j = pd.concat([sp.assign(t=zeit(sp['DATE'])).set_index('t')['VALUE'].rename('sp'),
                       ri.assign(t=zeit(ri['DATE'])).set_index('t')['VALUE'].rename('ri')], axis=1).dropna()
        j = j[~j.index.duplicated()].sort_index()
        return _vektor_stunde(j.index.tz_localize('UTC'), j['sp'].values * MS_KN, j['ri'].values)
    if quelle == 'geosphere':
        d = pd.read_csv(os.path.join(Q, 'geosphere', kenn[2:] + '.csv')).dropna(subset=['ffam', 'dd'])
        t = pd.to_datetime(d['time'], utc=True)
        # Zeitstempel = Ende des 10-min-Intervalls (GeoSphere-Konvention) -> Mitte 5 min frueher
        return _vektor_stunde(t - pd.Timedelta(minutes=5), d['ffam'].values * MS_KN, d['dd'].values)
    if quelle in CSV_NETZE:                     # einheitliche CSV (py/spotsuche_laden.py): t (UTC, Intervallmitte), kn, grad
        d = pd.read_csv(os.path.join(Q, quelle, _csv_id(quelle, kenn) + '.csv')).dropna()
        d = d[(d['kn'] >= 0) & (d['kn'] < 100) & (d['grad'] >= 0) & (d['grad'] <= 360)]
        t = pd.to_datetime(d['t'].str.rstrip('Z')).dt.tz_localize('UTC')
        d = d.set_index(t)
        d = d[~d.index.duplicated()].sort_index()
        if pd.Series(d.index).diff().median() >= pd.Timedelta(minutes=30):          # stuendlich (MF, KNMI, CO-OPS)
            if (d.index.minute == 30).mean() > 0.5:
                # Stundenmittel mit Mitte HH:30 (KNMI): zwei Nachbarn vektoriell auf die volle Stunde mitteln.
                # (25.11.2026: round('1h') rundet :30 abwechselnd auf/ab -> die Haelfte der Stunden fiel weg)
                u = -d['kn'] * np.sin(np.radians(d['grad'])); v = -d['kn'] * np.cos(np.radians(d['grad']))
                x = pd.DataFrame({'u': u, 'v': v, 'sp': d['kn']}).asfreq('1h')
                x = ((x + x.shift(-1)) / 2).dropna()
                x.index = x.index + pd.Timedelta(minutes=30)
                d = pd.DataFrame({'kn': x['sp'], 'grad': np.degrees(np.arctan2(-x['u'], -x['v'])) % 360})
            else:
                d.index = d.index.round('1h')
                d = d[~d.index.duplicated()]
            out = pd.DataFrame({'sp': d['kn'].astype(float), 'ri': d['grad'].astype(float)})
            out.loc[out['sp'] == 0, 'ri'] = np.nan
            return out
        return _vektor_stunde(d.index, d['kn'].values, d['grad'].values)
    if quelle == 'meteotrentino':
        def lies(var):
            z = []
            for l in open(os.path.join(Q, 'meteotrentino', '%s_%s.csv' % (kenn, var)), encoding='latin1'):
                f = l.split(',')
                if len(f) >= 2 and f[0].count(':') == 2 and '/' in f[0]:
                    try:
                        z.append((pd.to_datetime(f[0].strip(), format='%H:%M:%S %d/%m/%Y'), float(f[1])))
                    except ValueError:
                        pass
            return pd.DataFrame(z, columns=['t', var]).drop_duplicates('t').set_index('t')[var]
        j = pd.concat([lies('515').rename('sp'), lies('500').rename('ri')], axis=1).dropna()
        j = j[(j['sp'] >= 0) & (j['sp'] < 60) & (j['ri'] >= 0) & (j['ri'] <= 360)]
        # MEZ (UTC+1, ganzjaehrig) -> UTC; Stempel = Ende des 10-min-Intervalls -> Mitte 5 min frueher
        t = (j.index - pd.Timedelta(hours=1, minutes=5)).tz_localize('UTC')
        return _vektor_stunde(t, j['sp'].values * MS_KN, j['ri'].values)
    if quelle == 'pioupiou':
        d = _pioupiou(kenn).dropna(subset=['avg', 'heading'])
        d = d[(d['avg'] >= 0) & (d['avg'] < 200)]
        t = pd.to_datetime(d['time'], utc=True)
        return _vektor_stunde(t, d['avg'].values / 1.852, d['heading'].values, mindest=6)
    raise ValueError(quelle)


def modelle(r, la, lo):
    pfad = os.path.join(Q, 'modelle', '%s.json' % r[3].replace(':', '_'))
    if not os.path.exists(pfad):
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        import time
        for _v in range(5):
            js = requests.get('https://historical-forecast-api.open-meteo.com/v1/forecast', timeout=300, params=dict(
                latitude=la, longitude=lo, hourly='wind_speed_10m,wind_direction_10m', models=','.join(MODELLE),
                start_date=VON, end_date=BIS, wind_speed_unit='kn', timezone='GMT', cell_selection='nearest')).json()
            if 'limit exceeded' not in str(js.get('reason', '')):
                break
            time.sleep(65)
        if 'hourly' not in js:
            raise RuntimeError(js)
        json.dump(js, open(pfad, 'w'))
    h = json.load(open(pfad))['hourly']
    t = pd.to_datetime(h['time']).tz_localize('UTC')
    out = {}
    for m in MODELLE:
        sp, ri = h.get('wind_speed_10m_' + m), h.get('wind_direction_10m_' + m)
        if sp is None:
            continue
        d = pd.DataFrame({'sp': np.array(sp, float), 'ri': np.array(ri, float)}, index=t)
        if d['sp'].notna().mean() > 0.8:
            out[m] = d
    return out


def _richtfehler(a, b):
    return np.abs((a - b + 180) % 360 - 180)


def zeit_lag(obs, mod):
    """Bester Zeitversatz (h) zwischen Messung und Modellmittel ueber den Tagesgang (Pruefung der Zeitzone)."""
    mm = pd.concat([d['sp'] for d in mod.values()], axis=1).mean(axis=1)
    best = None
    for lag in range(-3, 4):
        x = pd.concat([obs['sp'], mm.shift(lag)], axis=1, sort=True).dropna()
        if len(x) < 50:
            continue
        c = np.corrcoef(x.iloc[:, 0], x.iloc[:, 1])[0, 1]
        if best is None or c > best[1]:
            best = (lag, c)
    return best[0] if best else 0


def kennzahlen(o, p, ro, rp, schwelle=12.0):
    e = p - o
    m = o >= 6
    gleit_o, gleit_p = o >= schwelle, p >= schwelle
    treffer = (gleit_o & gleit_p).sum()
    return dict(n=len(o), bias_kn=round(e.mean(), 2), mae_kn=round(np.abs(e).mean(), 2),
                r=round(np.corrcoef(o, p)[0, 1], 3) if len(o) > 2 else np.nan,
                richtung_grad=round(np.nanmedian(_richtfehler(ro[m], rp[m])), 0) if m.sum() > 10 else np.nan,
                tage12_mess=int(gleit_o.sum()),
                pod12=round(treffer / max(gleit_o.sum(), 1), 2),            # gemessene Gleitstunden vorhergesagt
                far12=round(1 - treffer / max(gleit_p.sum(), 1), 2))         # vorhergesagte, die nicht kamen


def korrektur_cv(X, y, monat, stunde):
    """Lineare Korrektur y ~ a(Stunde) + X*b, je Monat aus den uebrigen Monaten geschaetzt -> Vorhersage."""
    stunden = sorted(set(stunde))
    H = np.array([[1.0 if s == k else 0.0 for k in stunden] for s in stunde])
    A = np.hstack([H, X])
    out = np.full(len(y), np.nan)
    for mo in sorted(set(monat)):
        tr, te = monat != mo, monat == mo
        if tr.sum() < 50 or not te.any():
            continue
        lam = 1.0 * np.eye(A.shape[1])
        lam[:len(stunden), :len(stunden)] = 0
        b = np.linalg.solve(A[tr].T @ A[tr] + lam, A[tr].T @ y[tr])
        out[te] = A[te] @ b
    return np.clip(out, 0, None)


def auswerten(r):
    name, tz, quelle, kenn, la, lo, bem = r[:7]
    if la is None:
        la, lo = _synop_ort(kenn)
    obs = messung(r)
    obs = obs[(obs.index >= pd.Timestamp(VON, tz='UTC')) & (obs.index <= pd.Timestamp(BIS + ' 23:00', tz='UTC'))]
    mod = modelle(r, la, lo)
    lag = zeit_lag(obs, mod)
    if quelle == 'meteoschweiz' and lag:
        obs.index = obs.index + pd.Timedelta(hours=lag)
    lokal = obs.index.tz_convert(tz)
    tag = (lokal.hour >= 9) & (lokal.hour <= 19)                   # Thermik-/Surfzeit, Ortszeit
    o = obs[tag]
    zeilen = []
    gem = None
    for m, d in mod.items():
        x = pd.concat([o, d.add_prefix('m_')], axis=1, join='inner').dropna(subset=['sp', 'm_sp'])
        if len(x) < 200:
            continue
        k = kennzahlen(x['sp'].values, x['m_sp'].values, x['ri'].values, x['m_ri'].values)
        z = dict(revier=name, modell=KURZ[m], zeitversatz_h=lag, **k)
        # Korrektur je Revier: Stundengang + Faktor (Kreuzvalidierung ueber Monate)
        lk = x.index.tz_convert(tz)
        yk = korrektur_cv(x[['m_sp']].values, x['sp'].values, lk.month.values, lk.hour.values)
        ok = np.isfinite(yk)
        kk = kennzahlen(x['sp'].values[ok], yk[ok], x['ri'].values[ok], x['m_ri'].values[ok])
        z.update(korr_bias_kn=kk['bias_kn'], korr_mae_kn=kk['mae_kn'], korr_pod12=kk['pod12'], korr_far12=kk['far12'])
        zeilen.append(z)
        gem = x[['sp', 'ri']].join(d['sp'].rename(m), how='inner') if gem is None else gem.join(d['sp'].rename(m), how='inner')
    # Mischung aller Modelle (gelernt, Kreuzvalidierung)
    if gem is not None and len(gem.columns) > 3:
        gem = gem.dropna()
        lk = gem.index.tz_convert(tz)
        X = gem.drop(columns=['sp', 'ri']).values
        yk = korrektur_cv(X, gem['sp'].values, lk.month.values, lk.hour.values)
        ok = np.isfinite(yk)
        mi = np.nanmean(X, axis=1)
        k = kennzahlen(gem['sp'].values[ok], mi[ok], gem['ri'].values[ok], gem['ri'].values[ok])
        kk = kennzahlen(gem['sp'].values[ok], yk[ok], gem['ri'].values[ok], gem['ri'].values[ok])
        zeilen.append(dict(revier=name, modell='Mittel aller (%d)' % X.shape[1], zeitversatz_h=lag, **k,
                           korr_bias_kn=kk['bias_kn'], korr_mae_kn=kk['mae_kn'], korr_pod12=kk['pod12'],
                           korr_far12=kk['far12']))
        zeilen[-1]['richtung_grad'] = np.nan
    return zeilen, o, la, lo


QUELLE_TEXT = {'meteoschweiz': 'MeteoSwiss', 'suedtirol': 'Wetterdienst Südtirol', 'lombardia': 'ARPA Lombardia',
               'synop': 'SYNOP (WMO)', 'ogimet': 'SYNOP (WMO, OGIMET)', 'metar': 'METAR', 'ndbc': 'NOAA NDBC', 'mesowest': 'MesoWest',
               'geosphere': 'GeoSphere Austria', 'meteotrentino': 'Meteotrentino',
               'meteofrance': 'Météo-France', 'dwd': 'DWD', 'knmi': 'KNMI', 'dmi': 'DMI', 'coops': 'NOAA CO-OPS', 'pioupiou': 'Pioupiou / OpenWindMap'}


def _quell_link(quelle, kenn):
    if quelle == 'metar':
        return 'https://mesonet.agron.iastate.edu/sites/site.php?station=%s&network=' % kenn
    if quelle == 'ndbc':
        return 'https://www.ndbc.noaa.gov/station_page.php?station=%s' % kenn
    if quelle == 'mesowest':
        return 'https://mesowest.utah.edu/cgi-bin/droman/meso_base_dyn.cgi?stn=%s' % kenn
    if quelle == 'pioupiou':
        return 'https://www.openwindmap.org/PP%s' % kenn[2:]
    if quelle == 'meteotrentino':
        return 'https://www.meteotrentino.it/'
    if quelle == 'meteofrance':
        return 'https://meteo.data.gouv.fr/'
    if quelle == 'dwd':
        return 'https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/wind/'
    if quelle == 'knmi':
        return 'https://www.knmi.nl/nederland-nu/klimatologie/uurgegevens'
    if quelle == 'dmi':
        return 'https://opendatadocs.dmi.govcloud.dk/'
    if quelle == 'coops':
        return 'https://tidesandcurrents.noaa.gov/stationhome.html?id=%s' % kenn[5:]
    if quelle == 'geosphere':
        return 'https://data.hub.geosphere.at/dataset/klima-v2-10min'
    if quelle == 'meteoschweiz':
        return 'https://www.meteoswiss.admin.ch/services-and-publications/applications/measurement-values-and-measuring-networks.html'
    return ''


def stations_karte(alle, orte, wahl):
    """Stationsliste fuer die Karte (static/wind_stations/wind_stations.json); Teil-Laeufe ergaenzen die alte Liste."""
    st = {}
    if os.path.exists(KARTE) and len(wahl) < len(REVIERE):
        gueltig = {r[0] for r in REVIERE}                         # entfernte Reviere nicht weiterschleppen
        st = {x['name']: x for x in json.load(open(KARTE))['stations'] if x['name'] in gueltig}
    df = pd.DataFrame(alle)
    for r in wahl:
        name, tz, quelle, kenn, _, _, bem = r[:7]
        spot = r[7] if len(r) > 7 else ''
        z = df[df['revier'] == name] if len(df) else df
        if not len(z) or name not in orte:
            st.pop(name, None)
            continue
        roh = z[~z['modell'].str.startswith('Mittel') & (z['modell'] != KURZ['best_match'])]
        bm = z[z['modell'] == KURZ['best_match']]
        mix = z[z['modell'].str.startswith('Mittel')]
        bester = roh.sort_values('mae_kn').iloc[0] if len(roh) else None
        korr = (mix if len(mix) else z).sort_values('korr_mae_kn').iloc[0]
        la, lo, mittel, h12 = orte[name]
        st[name] = dict(
            name=name, spot=spot, lat=round(float(la), 5), lon=round(float(lo), 5), source=QUELLE_TEXT.get(quelle, quelle),
            id=kenn, note=bem, tz=tz, link=_quell_link(quelle, kenn), mean_kn=round(mittel, 1), hours12=int(h12),
            n=int(korr['n']), lag_h=int(z['zeitversatz_h'].iloc[0]),
            best_match_mae=None if not len(bm) else float(bm['mae_kn'].iloc[0]),
            best_match_bias=None if not len(bm) else float(bm['bias_kn'].iloc[0]),
            best_model=None if bester is None else bester['modell'],
            best_model_mae=None if bester is None else float(bester['mae_kn']),
            best_model_bias=None if bester is None else float(bester['bias_kn']),
            corr_mae=float(korr['korr_mae_kn']), corr_pod12=float(korr['korr_pod12']),
            corr_far12=float(korr['korr_far12']),
            models=[dict(m=x['modell'], bias=float(x['bias_kn']), mae=float(x['mae_kn']), r=float(x['r']),
                         corr_mae=float(x['korr_mae_kn'])) for _, x in z.sort_values('korr_mae_kn').iterrows()])
    os.makedirs(os.path.dirname(KARTE), exist_ok=True)
    reihe = [r[0] for r in REVIERE]
    aus = sorted(st.values(), key=lambda x: reihe.index(x['name']) if x['name'] in reihe else 999)
    json.dump(dict(period='%s – %s' % (VON, BIS), hours='9–19 local time', stations=aus),
              open(KARTE, 'w'), ensure_ascii=False, indent=0)
    print('->', os.path.relpath(KARTE, ROOT), '(%d Stationen)' % len(aus))


def main(argv):
    wahl = [r for r in REVIERE if not argv or any(a.lower() in r[0].lower() for a in argv[0].split(','))]
    alle, orte = [], {}
    for r in wahl:
        try:
            z, o, la, lo = auswerten(r)
        except FileNotFoundError as e:
            print('%-32s keine Messung (%s)' % (r[0], os.path.basename(str(e.filename))))
            continue
        except Exception as e:                                         # noqa: BLE001
            print('%-32s FEHLER %r' % (r[0], e))
            continue
        alle += z
        if not z:                                                  # nicht still verschwinden lassen (Essaouira/Sal, 24.11.2026)
            print('%-32s WARNUNG: zu wenige Messstunden im Zeitraum (%d) -- andere Quelle suchen' % (r[0], len(o)))
        if z:
            orte[r[0]] = (la, lo, float(o['sp'].mean()), int((o['sp'] >= 12).sum()))
        print('\n%s  (%s; Messmittel 9-19 Uhr %.1f kn, %d h >= 12 kn; Zeitversatz %+d h)'
              % (r[0], r[6] or r[2], o['sp'].mean(), (o['sp'] >= 12).sum(), z[0]['zeitversatz_h'] if z else 0))
        print('  %-24s %6s %6s %5s %6s %5s %5s | korrigiert: %6s %6s %5s %5s'
              % ('Modell', 'Bias', 'MAE', 'r', 'Richt', 'POD', 'FAR', 'Bias', 'MAE', 'POD', 'FAR'))
        for x in sorted(z, key=lambda x: x['korr_mae_kn']):
            print('  %-24s %+6.1f %6.2f %5.2f %5s° %5.2f %5.2f | %+16.1f %6.2f %5.2f %5.2f'
                  % (x['modell'], x['bias_kn'], x['mae_kn'], x['r'],
                     '' if not np.isfinite(x['richtung_grad']) else '%.0f' % x['richtung_grad'],
                     x['pod12'], x['far12'], x['korr_bias_kn'], x['korr_mae_kn'], x['korr_pod12'], x['korr_far12']))
    if alle:
        neu = pd.DataFrame(alle)
        if len(wahl) < len(REVIERE) and os.path.exists(AUS):           # Teil-Lauf: uebrige Reviere behalten
            alt = pd.read_csv(AUS)
            alt = alt[alt['revier'].isin([r[0] for r in REVIERE])]
            neu = pd.concat([alt[~alt['revier'].isin([r[0] for r in wahl])], neu], ignore_index=True)
        neu.to_csv(AUS, index=False)
        print('\n->', os.path.relpath(AUS, ROOT))
    stations_karte(alle, orte, wahl)


if __name__ == '__main__':
    main(sys.argv[1:])
