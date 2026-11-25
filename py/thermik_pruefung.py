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

# name, zeitzone, quelle, kennung, lat, lon, bemerkung
REVIERE = [
    ('Silvaplana/Sils (Segl-Maria)', 'Europe/Zurich', 'meteoschweiz', 'SIA', 46.432331, 9.762325, 'Malojawind'),
    ('Reschensee (St. Valentin)', 'Europe/Rome', 'suedtirol', '02200MS', 46.7759, 10.5289, 'Talwind Vinschgau'),
    ('Comer See Nord (Colico)', 'Europe/Rome', 'lombardia', '19109:6008', 46.13814, 9.38469, 'Breva'),
    ('Gardasee Nord (Limone)', 'Europe/Rome', 'lombardia', '14065:14066', 45.80683, 10.79006, 'Ora/Peler'),
    ('Tarifa', 'Europe/Madrid', 'synop', '0-724-0-458', None, None, 'Levante/Poniente'),
    ('Talamone (Grosseto)', 'Europe/Rome', 'synop', '0-380-0-206', None, None, 'Station 20 km'),
    # Cap Pertusato (0-250-0-770) im IEM-Archiv kaputt: Wind ~2 kn, Richtung nie ueber 94 Grad
    ('Porto Pollo (Figari)', 'Europe/Rome', 'metar', 'LFKF', None, None, 'Station 39 km, Suedkorsika'),
    ('Porto Pollo (Olbia)', 'Europe/Rome', 'metar', 'LIEO', None, None, 'Station 36 km'),
    ('Hyères (Flughafen, METAR)', 'Europe/Paris', 'metar', 'LFTH', None, None, ''),
    ('Lo Stagnone (Trapani-Birgi)', 'Europe/Rome', 'synop', '0-380-0-429', None, None, ''),
    ('Rhodos (Flughafen)', 'Europe/Athens', 'synop', '0-300-0-749', None, None, 'Meltemi, Ialysos'),
    ('Kos (Flughafen)', 'Europe/Athens', 'synop', '0-300-0-742', None, None, 'Meltemi, Marmari'),
    ('Karpathos (Flughafen)', 'Europe/Athens', 'synop', '0-300-0-765', None, None, 'Meltemi, Gun Bay'),
    ('Naxos (Flughafen)', 'Europe/Athens', 'metar', 'LGNX', None, None, 'Meltemi; SYNOP 0-300-0-732 im IEM-Archiv leer'),
    ('Paros (Flughafen)', 'Europe/Athens', 'synop', '0-300-0-766', None, None, 'Meltemi'),
    # franzoesische SYNOP-Stationen im IEM-Archiv kaputt (Hyeres 1,7 kn, Leucate 2,1 kn Mittel) -> METAR
    ('Leucate (Perpignan)', 'Europe/Paris', 'metar', 'LFMP', None, None, 'Tramontane, Station 24 km'),
    ('Sylt (List)', 'Europe/Berlin', 'synop', '0-276-0-20', None, None, ''),
    ('Fehmarn', 'Europe/Berlin', 'synop', '0-276-0-55', None, None, ''),
    ('Neusiedler See', 'Europe/Vienna', 'synop', '0-40-0-72', None, None, ''),
    ('Neusiedler See (Podersdorf Strandbad)', 'Europe/Vienna', 'geosphere', 'gs7912', 47.86611, 16.83444, 'GeoSphere, am Spot'),
    ('Wolfgangsee (St. Wolfgang)', 'Europe/Vienna', 'geosphere', 'gs9512', 47.74028, 13.44194, 'GeoSphere, Ufer'),
    ('Traunsee (Altmünster)', 'Europe/Vienna', 'geosphere', 'gs6621', 47.87917, 13.77333, 'GeoSphere, Nordende'),
    ('Achensee (Achenkirch)', 'Europe/Vienna', 'geosphere', 'gs8806', 47.49944, 11.70667, 'GeoSphere, Nordende'),
    ('Hyères Almanarre (La Capte)', 'Europe/Paris', 'pioupiou', 'pp2133', None, None, 'Pioupiou, Segelschule'),
    ('Gruissan (Étang de Mateille)', 'Europe/Paris', 'pioupiou', 'pp602', None, None, 'Pioupiou, am Spot'),
    ('Leucate (Aéromodélisme)', 'Europe/Paris', 'pioupiou', 'pp1538', None, None, 'Pioupiou, Plateau'),
    # Genfer See Windbird 1652 (Lausanne, 4 km landein): Mittel 2 kn, windgeschuetzt -> nicht repraesentativ
    ('Dakhla (Flughafen)', 'Africa/El_Aaiun', 'metar', 'GMMH', None, None, 'Passat, Lagune ~5 km; WMO 60096 auch in OGIMET'),
    ('Essaouira', 'Africa/Casablanca', 'ogimet', '60220', 31.51, -9.78, 'Alizé; WMO 60220 aus OGIMET (IEM nur bis 11.06.2026), 3-stündlich'),
    ('Hurghada/El Gouna', 'Africa/Cairo', 'synop', '0-818-0-463', None, None, ''),
    # Dahab (0-818-0-467) und Morro Jable (0-724-0-34): im IEM-Archiv keine Meldungen Mai-Sep 2026
    ('Sal (Flughafen)', 'Atlantic/Cape_Verde', 'metar', 'GVAC', None, None, 'Passat, Winter; SYNOP 0-132-0-594 im IEM-Archiv lueckenhaft'),
    ('Kroatien Bol/Brac (Hvar)', 'Europe/Zagreb', 'synop', '0-705-0-447', None, None, 'Maestral'),
    ('Kroatien Split (Marjan)', 'Europe/Zagreb', 'synop', '0-705-0-445', None, None, 'Maestral, Station 122 m'),
    ('Bodensee (Konstanz)', 'Europe/Berlin', 'synop', '0-276-0-929', None, None, ''),
    ('Bodensee (Guettingen)', 'Europe/Zurich', 'meteoschweiz', 'GUT', 47.601733, 9.279428, ''),
    ('Genfer See (Pully)', 'Europe/Zurich', 'meteoschweiz', 'PUY', 46.512283, 6.667517, 'Station am Hang'),
    ('Lago Maggiore (Magadino)', 'Europe/Zurich', 'meteoschweiz', 'MAG', 46.160025, 8.933672, 'Ebene am Nordende'),
    ('Teneriffa El Medano (Flughafen Sur)', 'Atlantic/Canary', 'metar', 'GCTS', None, None, 'Passat'),
    ('Gran Canaria Pozo (Gando)', 'Atlantic/Canary', 'metar', 'GCLP', None, None, 'Passat'),
    ('Cumbuco (Fortaleza)', 'America/Fortaleza', 'metar', 'SBFZ', None, None, 'Passat, Station 25 km'),
    ('Kapstadt (Flughafen)', 'Africa/Johannesburg', 'metar', 'FACT', None, None, 'Winter, Station 22 km landein'),
    ('Mauritius (Plaisance)', 'Indian/Mauritius', 'metar', 'FIMP', None, None, 'Winter = Passatsaison'),
    ('Perth (Flughafen)', 'Australia/Perth', 'metar', 'YPPH', None, None, 'Winter, Station 15 km landein'),
    ('Sydney (Botany Bay)', 'Australia/Sydney', 'metar', 'YSSY', None, None, 'Winter'),
    ('Columbia Gorge (Hood River)', 'America/Los_Angeles', 'metar', '4S2', None, None, 'Duesenwind'),
    ('San Francisco Bay (SFO)', 'America/Los_Angeles', 'metar', 'KSFO', None, None, 'Seewind'),
    ('Chesapeake Bay (Annapolis)', 'America/New_York', 'metar', 'NAK', None, None, ''),
    ('Chesapeake Bay (Thomas Point Leuchtturm)', 'America/New_York', 'ndbc', 'tplm2', 38.899, -76.436, 'NDBC'),
    ('San Francisco Bay (Fort Point)', 'America/Los_Angeles', 'ndbc', 'ftpc1', 37.806, -122.466, 'NDBC, Golden Gate'),
    ('San Francisco Bay (Alameda)', 'America/Los_Angeles', 'ndbc', 'aamc1', 37.772, -122.300, 'NDBC'),
    ('Suisun Bay/Delta (Port Chicago)', 'America/Los_Angeles', 'ndbc', 'pcoc1', 38.056, -122.039, 'NDBC, 25 km vor Sherman Isl.'),
    ('Miami (Virginia Key)', 'America/New_York', 'ndbc', 'vakf1', 25.731, -80.162, 'NDBC'),
    ('Hood River (HOXO, Wasser)', 'America/Los_Angeles', 'mesowest', 'HOXO', None, None, 'MesoWest'),
    ('Sherman Island (Bridgehead)', 'America/Los_Angeles', 'mesowest', '519PG', 38.00533, -121.76035, 'MesoWest PG&E, 4 km'),
    ('Delta (Twitchell Island)', 'America/Los_Angeles', 'mesowest', 'TCICA', 38.1, -121.65, 'MesoWest'),
    ('Crissy Field (Golden Gate Bridge)', 'America/Los_Angeles', 'mesowest', 'GGBC1', None, None, 'MesoWest, 82 m hoch'),
    ('Annapolis (Boje 44063)', 'America/New_York', 'mesowest', 'NDBC44063', None, None, 'MesoWest'),
    ('Annapolis (Pegel APAM2)', 'America/New_York', 'mesowest', 'APAM2', None, None, 'MesoWest'),
    ('Miami (Rosenstiel, Virginia Key)', 'America/New_York', 'mesowest', '0234W', None, None, 'MesoWest'),
    ('Miami', 'America/New_York', 'metar', 'KMIA', None, None, 'Station 10 km landein'),
    ('Barbados', 'America/Barbados', 'metar', 'TBPB', None, None, 'Passat'),
    ('Barcelona (El Prat)', 'Europe/Madrid', 'metar', 'LEBL', None, None, 'Seewind'),
    ('Mallorca Bucht von Palma', 'Europe/Madrid', 'metar', 'LEPA', None, None, 'Embat (Seewind)'),
    ('Solent (Southampton)', 'Europe/London', 'metar', 'EGHI', None, None, 'Station 10 km landein'),
    ('Ammersee/Starnberger See (Oberpfaffenhofen)', 'Europe/Berlin', 'metar', 'EDMO', None, None, 'Station zwischen den Seen'),
    ('Bodensee (Friedrichshafen)', 'Europe/Berlin', 'metar', 'EDNY', None, None, ''),
]


def _metar(icao):
    d = pd.read_csv(os.path.join(Q, 'metar', icao + '.csv'), comment='#')
    d['t'] = pd.to_datetime(d['valid'], utc=True)
    return d


def _synop_ort(sid):
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
        a = a[a['stato'] == 'VA'].set_index('data')['valore'].astype(float)
        b = b[b['stato'] == 'VA'].set_index('data')['valore'].astype(float)
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
    name, tz, quelle, kenn, la, lo, bem = r
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
               'geosphere': 'GeoSphere Austria', 'pioupiou': 'Pioupiou / OpenWindMap'}


def _quell_link(quelle, kenn):
    if quelle == 'metar':
        return 'https://mesonet.agron.iastate.edu/sites/site.php?station=%s&network=' % kenn
    if quelle == 'ndbc':
        return 'https://www.ndbc.noaa.gov/station_page.php?station=%s' % kenn
    if quelle == 'mesowest':
        return 'https://mesowest.utah.edu/cgi-bin/droman/meso_base_dyn.cgi?stn=%s' % kenn
    if quelle == 'pioupiou':
        return 'https://www.openwindmap.org/PP%s' % kenn[2:]
    if quelle == 'geosphere':
        return 'https://data.hub.geosphere.at/dataset/klima-v2-10min'
    if quelle == 'meteoschweiz':
        return 'https://www.meteoswiss.admin.ch/services-and-publications/applications/measurement-values-and-measuring-networks.html'
    return ''


def stations_karte(alle, orte, wahl):
    """Stationsliste fuer die Karte (static/wind_stations/wind_stations.json); Teil-Laeufe ergaenzen die alte Liste."""
    st = {}
    if os.path.exists(KARTE) and len(wahl) < len(REVIERE):
        st = {x['name']: x for x in json.load(open(KARTE))['stations']}
    df = pd.DataFrame(alle)
    for r in wahl:
        name, tz, quelle, kenn, _, _, bem = r
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
            name=name, lat=round(float(la), 5), lon=round(float(lo), 5), source=QUELLE_TEXT.get(quelle, quelle),
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
            neu = pd.concat([alt[~alt['revier'].isin([r[0] for r in wahl])], neu], ignore_index=True)
        neu.to_csv(AUS, index=False)
        print('\n->', os.path.relpath(AUS, ROOT))
    stations_karte(alle, orte, wahl)


if __name__ == '__main__':
    main(sys.argv[1:])
