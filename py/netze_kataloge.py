#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stationsverzeichnisse weiterer offener Windnetze fuer die Karte (Oliver 26.11.2026, Punkte 1-3 der Netzliste).

Schreibt je Netz quellen/thermik/spotsuche/stationen_<netz>.csv (netz,id,name,lat,lon,alt); py/spotsuche.py nimmt
alle stationen_*.csv in stationen_alle.csv auf, py/stationsnetz.py daraus die Kartenebene "National networks".
Rohdateien unter quellen/thermik/spotsuche/roh/.

    venv/bin/python py/netze_kataloge.py [netz,netz,...]     (ohne Angabe: alle)

Netze (nur Stationen mit Windmessung, soweit das Verzeichnis es sagt):
  ndbc        NOAA NDBC activestations.xml, met=y, ohne NOS/CO-OPS (stehen schon als coops drin)
  aemet       AEMET OpenData: Positionen aus den Stundendateien des Sammlers (quellen/thermik/aemet), nur mit vv
  fmi         FMI open data WFS fmi::ef::stations, Netze "Automaattinen saeaasema" + Mastohavaintoasema
  imgw        IMGW-PIB danepubliczne /api/data/meteo (automatische Stationen; nur mit Windwert)
  lhmt        Litauen api.meteo.lt/v1/stations (AMS = automatische Wetterstationen)
  ee          Estland Keskkonnaagentuur observations.php (nur Stationen mit Windwert)
  meteocat    Katalonien XEMA, Socrata-Datensatz yqwd-vj5e, nur operativ
  socib       Balearen SOCIB THREDDS mooring/weather_station (Bojen + Kuestenstationen), Position aus OPeNDAP
  lombardia   ARPA Lombardia Sensoren "Velocita Vento", aktiv (lokal: quellen/thermik/lomb_sensori.json)
  suedtirol   Landeswetterdienst Suedtirol, Stationen mit Sensor WG
  frost       MET Norway Frost API (Client-ID ~/.config/frost_client_id), Quellen mit laufender wind_speed-Reihe
  ispra_rmn   ISPRA Rete Mareografica Nazionale, aus dem Kartenskript von mareografico.it
  venezia     Comune di Venezia CPSM, Windstationen der Lagune (dati.venezia.it vento.json)
  snpa_mare   Rete Mareografica SNPA (ARPA FVG, ARPAE), aus dem Kartenskript von mareografico.it
  puertos     Puertos del Estado PORTUS, Echtzeit-Windstationen (ohne fremde EXTERNOS-Bojen)
  arpav       ARPA Veneto, REST meteo_meteogrammi coordcd=12 (Wind)
  arpal       ARPAL Liguria, OMIRL REST stations/Vento
  arpae       ARPAE Emilia-Romagna, Echtzeitdatei realtime.jsonl (Stationen mit Wind)
  dwd_poi     DWD weather_reports/poi (aktuelle Stundenwerte), Koordinaten aus dem MOSMIX-Stationskatalog
  dwd_strasse DWD-Strassenwetterstationen (BUFR je Region), nur mit Windmessung
  midas       UK Met Office MIDAS Open (CEDA, Token ~/.config/ceda_token), Winddatensatz, nur letzter Jahrgang
  meteotrentino  Meteotrentino listaStazioni, alle laufenden Stationen (ohne Sensorangabe)
"""
import csv
import glob
import gzip
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'quellen', 'thermik', 'spotsuche')
ROH = os.path.join(S, 'roh')
UA = {'User-Agent': 'weather-tides/1.0'}


def holen(url, datei, timeout=120, **kw):
    os.makedirs(ROH, exist_ok=True)
    p = os.path.join(ROH, datei)
    r = requests.get(url, headers=dict(UA, **kw.pop('headers', {})), timeout=timeout, **kw)
    r.raise_for_status()
    open(p, 'wb').write(r.content)
    return p


def schreiben(netz, zeilen):
    p = os.path.join(S, 'stationen_%s.csv' % netz)
    gesehen = set()
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['netz', 'id', 'name', 'lat', 'lon', 'alt'])
        for i, name, la, lo, alt in zeilen:
            if i in gesehen or la is None or lo is None or (abs(la) < 0.01 and abs(lo) < 0.01):
                continue
            gesehen.add(i)
            w.writerow([netz, i, ' '.join(str(name).split()), round(la, 5), round(lo, 5), '' if alt in (None, '') else alt])
    print('%-10s %4d Stationen -> %s' % (netz, len(gesehen), os.path.relpath(p, ROOT)))


def ndbc():
    r = ET.parse(holen('https://www.ndbc.noaa.gov/activestations.xml', 'ndbc_activestations.xml')).getroot()
    # NOS-Stationen stehen schon als coops drin, auch wenn NDBC sie unter IOOS/NERRS/TCOON fuehrt (Nummer im Namen
    # oder dieselbe Position, La Jolla LJPC1 = 9410230)
    co = json.load(open(os.path.join(S, 'coops_met.json')))['stations']
    co_id = {str(c['id']) for c in co}
    co_pos = [(c['lat'], c['lng']) for c in co]
    z = []
    for x in r:
        a = x.attrib
        if a.get('met') != 'y' or a.get('pgm') == 'NOS/CO-OPS':
            continue
        if set(re.findall(r'\b\d{7}\b', a.get('name', ''))) & co_id:
            continue
        la, lo = float(a['lat']), float(a['lon'])
        if any(abs(la - c[0]) < 0.0015 and abs(lo - c[1]) < 0.002 for c in co_pos):
            continue
        if True:
            z.append((a['id'].upper(), a.get('name') or a['id'], float(a['lat']), float(a['lon']), a.get('elev')))
    schreiben('ndbc', z)


def aemet():
    pos = {}
    for p in sorted(glob.glob(os.path.join(ROOT, 'quellen', 'thermik', 'aemet', '*', '*.csv.gz'))):
        for z in csv.DictReader(gzip.open(p, 'rt', encoding='utf-8')):
            if z.get('vv') not in (None, '') and z.get('lat'):
                pos[z['idema']] = (z['idema'], z['ubi'].title(), float(z['lat']), float(z['lon']), z.get('alt'))
    schreiben('aemet', pos.values())


def fmi():
    p = holen('https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::ef::stations',
              'fmi_stations.xml', timeout=300)
    x = open(p, encoding='utf-8').read()
    z = []
    for f in x.split('<ef:EnvironmentalMonitoringFacility')[1:]:
        netze = re.findall(r'<ef:belongsTo xlink:title="([^"]*)"', f)
        if not any(n in ('Automaattinen sääasema', 'Mastohavaintoasema') for n in netze):
            continue
        i = re.search(r'<gml:identifier[^>]*>(\d+)</gml:identifier>', f)
        nm = re.search(r'<gml:name[^>]*>([^<]*)</gml:name>', f)
        pos = re.search(r'<gml:pos>([-\d.]+) ([-\d.]+)</gml:pos>', f)
        if i and pos:
            z.append((i.group(1), nm.group(1) if nm else i.group(1), float(pos.group(1)), float(pos.group(2)), None))
    schreiben('fmi', z)


def imgw():
    d = json.load(open(holen('https://danepubliczne.imgw.pl/api/data/meteo/', 'imgw_meteo.json')))
    z = [(s['kod_stacji'], s['nazwa_stacji'].title(), float(s['lat']), float(s['lon']), s.get('wysokosc_npm'))
         for s in d if s.get('lat') and (s.get('wiatr_srednia_predkosc') is not None or s.get('wiatr_poryw_10min') is not None)]
    schreiben('imgw', z)


def lhmt():
    d = json.load(open(holen('https://api.meteo.lt/v1/stations', 'lhmt_stations.json')))
    schreiben('lhmt', [(s['code'], s['name'], s['coordinates']['latitude'], s['coordinates']['longitude'], None) for s in d])


def ee():
    r = ET.parse(holen('https://www.ilmateenistus.ee/ilma_andmed/xml/observations.php', 'ee_observations.xml')).getroot()
    z = []
    for s in r.findall('station'):
        g = lambda t: (s.findtext(t) or '').strip()
        if g('windspeed') and g('latitude'):
            z.append((g('wmocode') or g('name'), g('name'), float(g('latitude')), float(g('longitude')), None))
    schreiben('ee', z)


def meteocat():
    d = json.load(open(holen('https://analisi.transparenciacatalunya.cat/resource/yqwd-vj5e.json?$limit=5000', 'meteocat_xema.json')))
    schreiben('meteocat', [(s['codi_estacio'], s['nom_estacio'], float(s['latitud']), float(s['longitud']), s.get('altitud'))
                           for s in d if s.get('nom_estat_ema') == 'Operativa' and s.get('latitud')])


def socib():
    base = 'https://thredds.socib.es/thredds/'
    kat = requests.get(base + 'catalog/mooring/weather_station/catalog.xml', headers=UA, timeout=120).text
    z = []
    for st in re.findall(r'catalogRef xlink:href="([^"/]+)/catalog.xml"', kat):
        try:
            k1 = requests.get(base + 'catalog/mooring/weather_station/%s/L1/catalog.xml' % st, headers=UA, timeout=120).text
            pfade = sorted(re.findall(r'urlPath="([^"]*_latest\.nc)"', k1), reverse=True)
            if not pfade:
                continue
            a = requests.get(base + 'dodsC/%s.ascii?LAT,LON' % pfade[0], headers=UA, timeout=120).text
            w = re.findall(r'^(?:LAT|LON)[^\n]*\n([-\d.]+)', a, re.M) or re.findall(r'(?:LAT|LON), ([-\d.]+)', a)
            if len(w) < 2:
                continue
            ort = st.split('_', 1)[1].rsplit('-', 1)[0]
            art = 'buoy' if st.startswith('buoy') else 'station'
            name = '%s %s' % (ort.replace('de', ' de ').replace('  ', ' ').title().replace(' De ', ' de '), 'Buoy' if art == 'buoy' else '')
            z.append(('%s' % st.split('_', 1)[1].rsplit('-', 1)[0] + '-' + art, name.strip(), float(w[0]), float(w[1]), None))
        except requests.RequestException as e:
            print('  socib', st, e)
    # SOCIB-Stationen, die PORTUS auch fuehrt (mit Live-Wert), dort lassen: <= 1 km zu einem PORTUS-Eintrag "SOCIB"
    pp = os.path.join(S, 'stationen_puertos.csv')
    if os.path.exists(pp):
        po = [(float(r['lat']), float(r['lon'])) for r in csv.DictReader(open(pp, encoding='utf-8')) if 'SOCIB' in r['name']]
        n = len(z)
        z = [x for x in z if not any(abs(x[2] - a) < 0.009 and abs(x[3] - b) < 0.012 for a, b in po)]
        print('  socib: %d schon bei PORTUS' % (n - len(z)))
    schreiben('socib', z)


def lombardia():
    d = json.load(open(os.path.join(ROOT, 'quellen', 'thermik', 'lomb_sensori.json')))
    schreiben('lombardia', [(s['idstazione'], s['nomestazione'], float(s['lat']), float(s['lng']), s.get('quota'))
                            for s in d if s.get('tipologia') == 'Velocità Vento' and s.get('storico') == 'N' and s.get('lat')])


def suedtirol():
    sen = json.load(open(holen('https://geoservices.buergernetz.bz.it/services/meteo/v1/sensors', 'bz_sensors.json')))
    wind = {s['SCODE'] for s in sen if s['TYPE'] == 'WG'}
    st = json.load(open(holen('https://geoservices.buergernetz.bz.it/services/meteo/v1/stations', 'bz_stations_wgs.json')))
    z = []
    for f in st['features']:
        p = f['properties']
        if p['SCODE'] in wind and p.get('LAT') is not None:
            z.append((p['SCODE'], p.get('NAME_D') or p['SCODE'], float(p['LAT']), float(p['LONG']), p.get('ALT')))
    schreiben('suedtirol', z)


def meteotrentino():
    """Alle laufenden Wetterstationen (Oliver 26.11.: die Liste sagt nicht, wer Wind misst -> alle; fine leer)."""
    r = ET.parse(holen('https://dati.meteotrentino.it/service.asmx/listaStazioni', 'meteotrentino_stazioni.xml')).getroot()
    ns = {'m': 'http://www.meteotrentino.it/'}
    z = []
    for a in r.findall('m:anagrafica', ns):
        g = lambda t: (a.findtext('m:' + t, default='', namespaces=ns) or '').strip()
        if g('fine') or not g('latitudine'):
            continue
        z.append((g('codice'), g('nome'), float(g('latitudine')), float(g('longitudine')), g('quota')))
    schreiben('meteotrentino', z)


def frost_id():
    return open(os.path.expanduser('~/.config/frost_client_id')).readline().strip()


def frost():
    """MET Norway Frost (CC BY 4.0, Client-ID in ~/.config/frost_client_id): Quellen mit laufender wind_speed-Reihe."""
    au = (frost_id(), '')
    ts = requests.get('https://frost.met.no/observations/availableTimeSeries/v0.jsonld', params={'elements': 'wind_speed'},
                      auth=au, headers=UA, timeout=300).json()['data']
    aktiv = {x['sourceId'].split(':')[0] for x in ts if not x.get('validTo')}
    src = requests.get('https://frost.met.no/sources/v0.jsonld', auth=au, headers=UA, timeout=300,
                       params={'types': 'SensorSystem', 'fields': 'id,name,shortName,geometry,masl'}).json()['data']
    z = []
    for q in src:
        g = q.get('geometry') or {}
        # SN >= 100000 = fremde Stationen (WMO-basiert, z.B. Sodankyla = FMI), stehen schon in ihrem eigenen Netz
        if q['id'] in aktiv and g.get('coordinates') and int(q['id'][2:]) < 100000:
            nm = (q.get('name') or q['id']).title()
            z.append((q['id'], nm, g['coordinates'][1], g['coordinates'][0], q.get('masl')))
    schreiben('frost', z)


def ispra_rmn():
    """ISPRA Rete Mareografica Nazionale (41 Pegel mit Wetterstation). Keine Liste als Datei: die Startseite von
    mareografico.it traegt die Karte als Skript (La/Lo/Nw-Felder + Popups mit SetS(<id>)); Nw = 1 ist die RMN.
    Die Seite verlangt erst ein Cookie mit der Bildschirmgroesse. Zitierwunsch: DOI 10.83182/ispra-rmn."""
    r = requests.get('https://www.mareografico.it/', headers=UA, timeout=120, cookies={'A4IxScreenSize': '1920@1080@1@it'})
    r.raise_for_status()
    s = r.text
    open(os.path.join(ROH, 'mareografico_home.html'), 'w', encoding='utf-8').write(s)
    feld = lambda n: json.loads(re.search(r'var %s=(\[[^\]]*\]);' % n, s).group(1).replace("'", '"'))
    la, lo, nw = feld('La'), feld('Lo'), feld('Nw')
    pop = {int(i): (stz, sid) for i, stz, sid in re.findall(
        r"St\[(\d+)\]\.bindPopup\(\"<div class='infohome'><p class='popup-network'>RETE MAREOGRAFICA NAZIONALE</p>"
        r"<p class='popup-station'>([^<]*)</p>.*?SetS\((\d+)\)", s)}
    z = [(pop[i][1], pop[i][0].title(), la[i], lo[i], None) for i in range(1, len(la)) if nw[i] == 1 and i in pop]
    schreiben('ispra_rmn', z)


VENEZIA = 'https://dati.venezia.it/sites/default/files/dataset/opendata/%s.json'


def venezia():
    """Comune di Venezia, Centro Previsioni e Segnalazioni Maree (CPSM; betreibt seit 2019 auch die frueheren
    ISPRA-Lagunenpegel): vento.json hat keine Koordinaten -> aus den anderen Dateien derselben Stationsnummer.
    1038 Diga Sud Lido Faro steht in keiner Datei mit Position und bleibt weg (Position nicht raten)."""
    v = json.load(open(holen(VENEZIA % 'vento', 'venezia_vento.json', headers={'User-Agent': 'Mozilla/5.0'})))
    pos = {}
    for f in ('livello', 'umidita', 'pressione', 'onde', 'radiazione'):
        try:
            for x in json.load(open(holen(VENEZIA % f, 'venezia_%s.json' % f, headers={'User-Agent': 'Mozilla/5.0'}))):
                if x.get('latDDN'):
                    pos.setdefault(x['ID_stazione'], (float(x['latDDN']), float(x['lonDDE'])))
        except (requests.RequestException, ValueError):
            pass
    z = [(x['ID_stazione'], x['stazione'], pos[x['ID_stazione']][0], pos[x['ID_stazione']][1], None)
         for x in v if x['ID_stazione'] in pos]
    weg = [x['stazione'] for x in v if x['ID_stazione'] not in pos]
    if weg:
        print('  venezia ohne Position:', ', '.join(weg))
    schreiben('venezia', z)


def snpa_mare():
    """Rete Mareografica SNPA (ARPA FVG, ARPAE) aus dem Kartenskript von mareografico.it (Nw = 11)."""
    r = requests.get('https://www.mareografico.it/', headers=UA, timeout=120, cookies={'A4IxScreenSize': '1920@1080@1@it'})
    r.raise_for_status()
    s = r.text
    feld = lambda n: json.loads(re.search(r'var %s=(\[[^\]]*\]);' % n, s).group(1).replace("'", '"'))
    la, lo, nw = feld('La'), feld('Lo'), feld('Nw')
    z = []
    for i, stz, rest in re.findall(r"St\[(\d+)\]\.bindPopup\(\"<div class='infohome'><p class='popup-network'>RETE MAREOGRAFICA SNPA</p>"
                                   r"<p class='popup-station'>([^<]*)</p>(.*?)\"\);", s):
        i = int(i)
        if nw[i] != 11:
            continue
        ag = 'fvg' if 'meteo.fvg.it' in rest else 'arpae' if 'arpae.it' in rest else 'snpa'
        z.append(('%s-%s' % (ag, re.sub(r'[^a-z0-9]+', '-', stz.lower()).strip('-')), stz.title(), la[i], lo[i], None))
    schreiben('snpa_mare', z)


def puertos():
    """Puertos del Estado, PORTUS (portus.puertos.es/portussvr/api, die Schnittstelle der eigenen Karte):
    estaciones/rt/WIND = alle Echtzeit-Windstationen (Hafenwetterstationen, Pegel, REDEXT/REDCOS-Bojen).
    Ohne EXTERNOS (UKMO-, Marine-Institute-, IHP-, MeteoGalicia-Bojen = fremde Netze, K1 steht schon bei NDBC).
    Das Feld incidencia ("Sin trasmision") stimmt oft nicht (Tarifa sendet) -> alle aufnehmen."""
    d = json.load(open(holen('https://portus.puertos.es/portussvr/api/estaciones/rt/WIND?locale=es', 'puertos_rt_wind.json')))
    z = []
    for x in d:
        if (x.get('red') or {}).get('tipoRed') == 'EXTERNOS' or (x.get('red') or {}).get('nombre') == 'EXTERNOS':
            continue
        nm = re.sub(r'^(Estaci[oó]n|Estac\.|Est\.) Meteor[oó]l[oó]gica( de| del)? ', '', x['nombre'], flags=re.I)
        z.append((str(x['id']), nm, x['latitud'], x['longitud'], None))
    schreiben('puertos', z)


ARPAV = 'https://api.arpa.veneto.it/REST/v1/meteo_meteogrammi?orario=0&rete=MGRAMMI&coordcd=12'
OMIRL = 'https://omirl.regione.liguria.it/Omirl/rest/stations/Vento'
ARPAE = 'https://dati-simc.arpae.it/opendata/osservati/meteo/realtime/realtime.jsonl'


def arpav():
    """ARPA Veneto: REST der Seite 'dati in diretta', coordcd 12 = Wind (alle Windstationen mit Koordinaten)."""
    d = json.load(open(holen(ARPAV, 'arpav_vento.json')))['data']
    schreiben('arpav', [(str(x['codseqst']), x['nome_stazione'], x['latitudine'], x['longitudine'],
                         None if x.get('quota') in (None, -1.0) else x['quota']) for x in d])


def arpal():
    """ARPAL Liguria, OMIRL: REST der eigenen Karte, stations/Vento."""
    d = json.load(open(holen(OMIRL, 'omirl_vento.json', headers={'User-Agent': 'Mozilla/5.0'})))
    schreiben('arpal', [(x['shortCode'], x['name'], x['lat'], x['lon'], x.get('alt')) for x in d])


def arpae():
    """ARPAE Emilia-Romagna, offene Echtzeitdatei (JSON-Zeilen, BUFR-Codes, 48 h): Stationen mit Wind B11002."""
    p = holen(ARPAE, 'arpae_realtime.jsonl', timeout=300)
    st, wind = {}, set()
    for l in open(p, encoding='utf-8'):
        d = json.loads(l)
        v = d['data'][0]['vars']
        k = '%s:%s:%s' % (d['network'], d['lon'], d['lat'])
        st[k] = (v.get('B01019', {}).get('v') or k, d['lat'] / 1e5, d['lon'] / 1e5, v.get('B07030', {}).get('v'))
        if any('B11002' in x.get('vars', {}) for x in d['data'][1:]):
            wind.add(k)
    schreiben('arpae', [(k, st[k][0], st[k][1], st[k][2], st[k][3]) for k in sorted(wind)])


def dwd_poi():
    """DWD opendata/weather/weather_reports/poi: aktuelle Stundenwerte je Station (<id>-BEOB.csv, ~970 Stationen weltweit,
    WMO-Nummern + DWD-eigene Kennungen wie A191_). Koordinaten aus dem MOSMIX-Stationskatalog (Grad.Minuten!)."""
    liste = requests.get('https://opendata.dwd.de/weather/weather_reports/poi/', headers=UA, timeout=120).text
    ids = re.findall(r'href="([A-Za-z0-9_]+)-BEOB\.csv"', liste)
    kat = {}
    gm = lambda x: (abs(x) // 1 + round(abs(x) % 1 * 100) / 60) * (1 if x >= 0 else -1)      # Grad.Minuten -> Grad
    for l in open(holen('https://www.dwd.de/DE/leistungen/met_verfahren_mosmix/mosmix_stationskatalog.cfg?view=nasPublication',
                        'mosmix_stationskatalog.cfg'), encoding='latin1'):
        m = re.match(r'^\s*(\S+)\s+(\S+)\s+(.*?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+)\s*$', l)
        if m:
            kat[m.group(1)] = (m.group(3), gm(float(m.group(4))), gm(float(m.group(5))), m.group(6))
    # nur Stationen, die Wind melden (viele DWD-eigene Kennungen sind Nebenstationen ohne Windmesser)
    from concurrent.futures import ThreadPoolExecutor

    def hat_wind(i):
        try:
            z_ = [l.split(';') for l in requests.get('https://opendata.dwd.de/weather/weather_reports/poi/%s-BEOB.csv' % i,
                                                      headers=UA, timeout=60).content.decode('latin1').splitlines()]
            c = z_[2].index('Windgeschwindigkeit')
            return any(len(d) > c and d[c] not in ('---', '') for d in z_[3:])
        except Exception:                                         # noqa: BLE001
            return False
    with ThreadPoolExecutor(6) as ex:
        wind = dict(zip(ids, ex.map(hat_wind, ids)))
    print('  dwd_poi: %d von %d melden Wind' % (sum(wind.values()), len(ids)))
    z = []
    for i in ids:
        k = kat.get(i.rstrip('_'))
        if k and wind.get(i):
            z.append((i, k[0].title(), k[1], k[2], k[3] or None))
    schreiben('dwd_poi', z)


def dwd_strasse():
    """DWD-Strassenwetterstationen (weather_reports/road_weather_stations, BUFR je Region, eccodes): nur Stationen,
    die in der neuesten Meldung Wind haben, ohne kaputte Koordinaten (Laenge 0)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import station_live
    reg = re.findall(r'href="([A-Z]{2})/"', requests.get(station_live.STRASSE, headers=UA, timeout=60).text)
    z = []
    for r in reg:
        for k, x in station_live.strasse_region(r).items():
            if x['ff'] is not None and x['lat'] and x['lon'] and abs(x['lon']) > 0.5 and 47 < x['lat'] < 56:
                nm = re.sub(r'^GMA\s+', '', x['name'], flags=re.I)        # Glaettemeldeanlage, kein Ortsname
                z.append(('%s-%s' % (r, k), nm if not nm.isupper() else nm.title(), x['lat'], x['lon'], None))
    schreiben('dwd_strasse', z)


def midas():
    """UK Met Office MIDAS Open bei CEDA (Token ~/.config/ceda_token, OGL): Stationsliste des Winddatensatzes
    uk-mean-wind-obs, nur Stationen mit Daten im letzten Jahrgang (Archiv, jaehrlich, kein Live).
    Kennung = Stationsordner <grafschaft>/<src_id>_<dateiname> (fuer den Link aufs Archiv)."""
    t = open(os.path.expanduser('~/.config/ceda_token')).readline().strip()
    base = 'https://dap.ceda.ac.uk/badc/ukmo-midas-open/data/uk-mean-wind-obs/'
    dv = sorted(set(re.findall(r'dataset-version-\d+', requests.get(base, headers=UA, timeout=60).text)))[-1]
    r = requests.get('%s%s/midas-open_uk-mean-wind-obs_dv-%s_station-metadata.csv' % (base, dv, dv[16:]),
                     headers=dict(UA, Authorization='Bearer ' + t), timeout=120)
    r.raise_for_status()
    open(os.path.join(ROH, 'midas_wind_station-metadata.csv'), 'wb').write(r.content)
    zeilen = r.content.decode('latin1').splitlines()
    tab = list(csv.DictReader(zeilen[zeilen.index('data') + 1:zeilen.index('end data')]))
    letzt = max(x['last_year'] for x in tab)
    z = [('%s/%s_%s' % (x['historic_county'], x['src_id'], x['station_file_name']), x['station_name'].title(),
          float(x['station_latitude']), float(x['station_longitude']), x['station_elevation'] or None)
         for x in tab if x['last_year'] == letzt]
    print('  midas: %s, letzter Jahrgang %s' % (dv, letzt))
    schreiben('midas', z)


NETZE = dict(ndbc=ndbc, aemet=aemet, fmi=fmi, imgw=imgw, lhmt=lhmt, ee=ee, meteocat=meteocat, socib=socib,
             lombardia=lombardia, suedtirol=suedtirol, meteotrentino=meteotrentino,
             frost=frost, ispra_rmn=ispra_rmn, venezia=venezia, snpa_mare=snpa_mare,
             puertos=puertos, arpav=arpav, arpal=arpal, arpae=arpae,
             dwd_poi=dwd_poi, dwd_strasse=dwd_strasse, midas=midas)

if __name__ == '__main__':
    for n in (sys.argv[1].split(',') if len(sys.argv) > 1 else NETZE):
        try:
            NETZE[n]()
        except Exception as e:                                    # noqa: BLE001
            print('%-10s FEHLER %s' % (n, e))
