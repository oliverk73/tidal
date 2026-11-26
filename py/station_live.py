# -*- coding: utf-8 -*-
"""Aktueller Wind EINER Station eines nationalen/regionalen Netzes, nur auf Klick im Kartenpopup (Oliver 26.11.2026:
"Daten nur beim Anklicken fuer die jeweilige Station, Last minimal"). app.py /api/station_live?netz=&id= ruft hole()
und haelt das Ergebnis 5 min vor; Netze, deren Schnittstelle nur alle Stationen auf einmal liefert (MeteoSchweiz,
Estland), werden hier 10 min als Ganzes vorgehalten.

Ergebnis: {"zeit": ISO-UTC, "kn": Mittel, "boe_kn": Boe, "richtung": Grad (woher), "hinweis": optional} oder
{"fehler": "..."}; Netze ohne offene Einzelabfrage -> {"fehler": "no live access"}.
"""
import csv
import io
import json
import os
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {'User-Agent': 'weather-tides/1.0'}
MS = 1.943844        # m/s -> kn
KMH = 1 / 1.852
_GANZ = {}           # netz -> (zeit, daten)


def _get(url, **kw):
    r = requests.get(url, headers=dict(UA, **kw.pop('headers', {})), timeout=kw.pop('timeout', 25), **kw)
    r.raise_for_status()
    return r


def _f(v, faktor=1.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else round(x * faktor, 1)


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _lokal(text, fmt, stunden):
    """Lokalzeit mit fester Abweichung -> UTC-ISO."""
    return _iso(datetime.strptime(text, fmt).replace(tzinfo=timezone(timedelta(hours=stunden))))


def _ganz(netz, laden, sekunden=600):
    c = _GANZ.get(netz)
    if c and time.time() - c[0] < sekunden:
        return c[1]
    d = laden()
    _GANZ[netz] = (time.time(), d)
    return d


def _mez():
    """Offset Mitteleuropa (Sommerzeit Ende Maerz - Ende Oktober) fuer Quellen mit Ortszeit."""
    import zoneinfo
    return datetime.now(zoneinfo.ZoneInfo('Europe/Rome')).utcoffset().total_seconds() / 3600


# ---------------------------------------------------------------- Netze
def ndbc(i):
    for z in _get('https://www.ndbc.noaa.gov/data/realtime2/%s.txt' % i.upper()).text.splitlines():
        if z.startswith('#'):
            continue
        f = z.split()
        return dict(zeit=_iso(datetime(*map(int, f[:5]), tzinfo=timezone.utc)), richtung=_f(f[5]), kn=_f(f[6], MS), boe_kn=_f(f[7], MS))
    return dict(fehler='no data')


def coops(i):
    j = _get('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter', params=dict(
        station=i, product='wind', date='latest', units='english', time_zone='gmt', format='json', application='weather-tides')).json()
    if not j.get('data'):
        return dict(fehler='station reports no wind')
    d = j['data'][-1]
    return dict(zeit=_lokal(d['t'], '%Y-%m-%d %H:%M', 0), kn=_f(d['s']), boe_kn=_f(d['g']), richtung=_f(d['d']))


def fmi(i):
    x = _get('https://opendata.fmi.fi/wfs', params=dict(service='WFS', version='2.0.0', request='getFeature',
             storedquery_id='fmi::observations::weather::simple', fmisid=i, parameters='ws_10min,wg_10min,wd_10min',
             starttime=_iso(datetime.now(timezone.utc) - timedelta(hours=3)))).text
    w = {}
    for t, p, v in re.findall(r'<BsWfs:Time>([^<]*)</BsWfs:Time>\s*<BsWfs:ParameterName>([^<]*)</BsWfs:ParameterName>\s*'
                              r'<BsWfs:ParameterValue>([^<]*)</BsWfs:ParameterValue>', x):
        if _f(v) is not None:
            w[p] = (t, v)
    if 'ws_10min' not in w:
        return dict(fehler='no data in the last 3 h')
    return dict(zeit=w['ws_10min'][0], kn=_f(w['ws_10min'][1], MS), boe_kn=_f(w.get('wg_10min', (0, None))[1], MS),
                richtung=_f(w.get('wd_10min', (0, None))[1]))


def imgw(i):
    j = _get('https://danepubliczne.imgw.pl/api/data/meteo/id/%s' % i).json()
    s = j[0] if isinstance(j, list) and j else j
    if not s or s.get('wiatr_srednia_predkosc') is None:
        return dict(fehler='no wind reading')
    return dict(zeit=_lokal(s['wiatr_srednia_predkosc_data'], '%Y-%m-%d %H:%M:%S', 0), kn=_f(s['wiatr_srednia_predkosc'], MS),
                boe_kn=_f(s.get('wiatr_poryw_10min'), MS), richtung=_f(s.get('wiatr_kierunek')))


def lhmt(i):
    o = [x for x in _get('https://api.meteo.lt/v1/stations/%s/observations/latest' % i).json().get('observations') or []
         if x.get('windSpeed') is not None]
    if not o:
        return dict(fehler='no data')
    d = o[-1]
    return dict(zeit=_lokal(d['observationTimeUtc'], '%Y-%m-%d %H:%M:%S', 0), kn=_f(d.get('windSpeed'), MS),
                boe_kn=_f(d.get('windGust'), MS), richtung=_f(d.get('windDirection')))


def ee(i):
    import xml.etree.ElementTree as ET

    def laden():
        r = ET.fromstring(_get('https://www.ilmateenistus.ee/ilma_andmed/xml/observations.php').content)
        return r.get('timestamp'), {(s.findtext('wmocode') or '').strip() or (s.findtext('name') or '').strip(): s for s in r.findall('station')}
    ts, st = _ganz('ee', laden)
    s = st.get(i)
    if s is None or not (s.findtext('windspeed') or '').strip():
        return dict(fehler='no wind reading')
    return dict(zeit=_iso(datetime.fromtimestamp(int(ts), timezone.utc)), kn=_f(s.findtext('windspeed'), MS),
                boe_kn=_f(s.findtext('windspeedmax'), MS), richtung=_f(s.findtext('winddirection')))


def meteocat(i):
    j = _get('https://analisi.transparenciacatalunya.cat/resource/nzvn-apee.json', timeout=50, params={
        'codi_estacio': i, '$order': 'data_lectura DESC', '$limit': 12, '$where': "codi_variable in('30','31','50') AND data_lectura > '%s'"
        % (datetime.now(timezone.utc) - timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S')}).json()
    w = {}
    for d in j:
        w.setdefault(d['codi_variable'], d)
    if '30' not in w:
        return dict(fehler='no wind reading')
    return dict(zeit=_lokal(w['30']['data_lectura'][:19], '%Y-%m-%dT%H:%M:%S', 0), kn=_f(w['30']['valor_lectura'], MS),
                boe_kn=_f(w.get('50', {}).get('valor_lectura'), MS), richtung=_f(w.get('31', {}).get('valor_lectura')))


def lombardia(i):
    sen = _ganz('lomb_sens', lambda: json.load(open(os.path.join(ROOT, 'quellen', 'thermik', 'lomb_sensori.json'))), 1e9)
    vv = [s['idsensore'] for s in sen if s['idstazione'] == i and s.get('tipologia') == 'Velocità Vento']
    dv = [s['idsensore'] for s in sen if s['idstazione'] == i and s.get('tipologia') == 'Direzione Vento']
    if not vv:
        return dict(fehler='no wind sensor')
    j = _get('https://www.dati.lombardia.it/resource/647i-nhxk.json', params={
        'idsensore': vv[0], '$order': 'data DESC', '$limit': 4}).json()
    mit = [d for d in j if d.get('idoperatore') == '1']
    boe = [d for d in j if d.get('idoperatore') == '3']
    if not mit:
        return dict(fehler='no data')
    r = dict(zeit=_lokal(mit[0]['data'][:19], '%Y-%m-%dT%H:%M:%S', _mez()), kn=_f(mit[0]['valore'], MS),
             boe_kn=_f(boe[0]['valore'], MS) if boe else None, richtung=None, hinweis='ARPA publishes with a delay of several hours')
    if dv:
        d = _get('https://www.dati.lombardia.it/resource/647i-nhxk.json', params={
            'idsensore': dv[0], '$order': 'data DESC', '$limit': 1}).json()
        r['richtung'] = _f(d[0]['valore']) if d else None
    return r


def suedtirol(i):
    j = _get('https://geoservices.buergernetz.bz.it/services/meteo/v1/sensors', params={'station_code': i}).json()
    w = {d['TYPE']: d for d in j}
    if 'WG' not in w:
        return dict(fehler='no wind reading')
    t = w['WG']['DATE']
    off = 2 if t.endswith('CEST') else 1
    return dict(zeit=_lokal(re.sub(r'C?E?S?T$', '', t), '%Y-%m-%dT%H:%M:%S', off), kn=_f(w['WG']['VALUE'], MS),
                boe_kn=_f(w.get('WG.BOE', {}).get('VALUE'), MS), richtung=_f(w.get('WR', {}).get('VALUE')))


def meteotrentino(i):
    import xml.etree.ElementTree as ET
    ns = {'m': 'http://www.meteotrentino.it/'}
    r = ET.fromstring(_get('https://dati.meteotrentino.it/service.asmx/ultimiDatiStazione', params={'codice': i}).content)
    v = r.findall('.//m:vento_al_suolo', ns)
    if not v:
        return dict(fehler='this station does not measure wind')
    d = v[-1]
    g = lambda t: d.findtext('m:' + t, namespaces=ns)
    return dict(zeit=_lokal(g('data'), '%Y-%m-%dT%H:%M:%S', 1), kn=_f(g('v'), MS), boe_kn=_f(g('vmax'), MS), richtung=_f(g('d')))


def aemet(i):
    k = open(os.path.expanduser('~/.config/aemet_key')).read().strip()
    j = _get('https://opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/%s' % i, headers={'api_key': k}).json()
    if not j.get('datos'):
        return dict(fehler=j.get('descripcion') or 'no data')
    d = [x for x in _get(j['datos']).json() if x.get('vv') is not None]
    if not d:
        return dict(fehler='no wind reading')
    d = d[-1]
    return dict(zeit=_lokal(d['fint'][:19], '%Y-%m-%dT%H:%M:%S', 0), kn=_f(d['vv'], MS), boe_kn=_f(d.get('vmax'), MS),
                richtung=_f(d.get('dv')))


def _dwd_zip(url):
    z = zipfile.ZipFile(io.BytesIO(_get(url).content))
    zeilen = list(csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding='latin1'), delimiter=';'))
    kopf = [k.strip() for k in zeilen[0]]
    return [dict(zip(kopf, [x.strip() for x in z_])) for z_ in zeilen[1:] if len(z_) >= len(kopf) - 1]


def dwd(i):
    base = 'https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/'
    try:
        w = [z for z in _dwd_zip(base + 'wind/now/10minutenwerte_wind_%s_now.zip' % i.zfill(5)) if _f(z.get('FF_10')) not in (None, -999)]
    except requests.HTTPError:
        return dict(fehler='no current 10-min file')
    if not w:
        return dict(fehler='no data')
    z = w[-1]
    r = dict(zeit=_lokal(z['MESS_DATUM'], '%Y%m%d%H%M', 0), kn=_f(z['FF_10'], MS), richtung=_f(z.get('DD_10')), boe_kn=None)
    try:
        x = [e for e in _dwd_zip(base + 'extreme_wind/now/10minutenwerte_extrema_wind_%s_now.zip' % i.zfill(5))
             if e.get('MESS_DATUM') == z['MESS_DATUM']]
        if x and _f(x[0].get('FX_10')) not in (None, -999):
            r['boe_kn'] = _f(x[0]['FX_10'], MS)
    except requests.HTTPError:
        pass
    return r


def dmi(i):
    j = _get('https://opendataapi.dmi.dk/v2/metObs/collections/observation/items', params={
        'stationId': i, 'datetime': _iso(datetime.now(timezone.utc) - timedelta(hours=3)) + '/..', 'limit': 1000}).json()
    w = {}
    for f in j.get('features', []):
        p = f['properties']
        if p['parameterId'] in ('wind_speed', 'wind_dir', 'wind_max') and (p['parameterId'] not in w or p['observed'] > w[p['parameterId']]['observed']):
            w[p['parameterId']] = p
    if 'wind_speed' not in w:
        return dict(fehler='no wind in the last 3 h')
    return dict(zeit=w['wind_speed']['observed'], kn=_f(w['wind_speed']['value'], MS),
                boe_kn=_f(w.get('wind_max', {}).get('value'), MS), richtung=_f(w.get('wind_dir', {}).get('value')))


def geosphere(i):
    # Katalog = Archiv-Nummern (klima-v2-10min, z.B. 500 Litschau); live (tawes) hat eigene -> per Position (<= 1 km)
    def laden():
        alt = {str(s['id']): (s['lat'], s['lon']) for s in json.load(open(os.path.join(
            ROOT, 'quellen', 'thermik', 'geosphere', 'meta_10min.json')))['stations']}
        neu = [(s['id'], s['lat'], s['lon']) for s in _get(
            'https://dataset.api.hub.geosphere.at/v1/station/current/tawes-v1-10min/metadata').json()['stations'] if s['is_active']]
        return alt, neu
    alt, neu = _ganz('geosphere_meta', laden, 86400)
    if i not in alt:
        return dict(fehler='unknown station')
    la, lo = alt[i]
    best = min(neu, key=lambda n: (n[1] - la) ** 2 + ((n[2] - lo) * 0.67) ** 2)
    if ((best[1] - la) ** 2 + ((best[2] - lo) * 0.67) ** 2) ** 0.5 * 111 > 1:
        return dict(fehler='no live station at this site')
    j = _get('https://dataset.api.hub.geosphere.at/v1/station/current/tawes-v1-10min',
             params={'parameters': 'FF,DD,FFX', 'station_ids': best[0]}).json()
    p = j['features'][0]['properties']['parameters']
    return dict(zeit=j['timestamps'][-1].replace('+00:00', 'Z'), kn=_f(p['FF']['data'][-1], MS),
                boe_kn=_f(p['FFX']['data'][-1], MS), richtung=_f(p['DD']['data'][-1]))


def meteoschweiz(i):
    def laden():
        u = 'https://data.geo.admin.ch/ch.meteoschweiz.messwerte-%s-10min/ch.meteoschweiz.messwerte-%s-10min_en.json'
        ff = {f['id']: f['properties'] for f in _get(u % ('windgeschwindigkeit-kmh', 'windgeschwindigkeit-kmh')).json()['features']}
        fx = {f['id']: f['properties'] for f in _get(u % ('wind-boeenspitze-kmh', 'wind-boeenspitze-kmh')).json()['features']}
        return ff, fx
    ff, fx = _ganz('meteoschweiz', laden)
    p = ff.get(i)
    if not p or p.get('value') is None:
        return dict(fehler='no wind reading')
    return dict(zeit=p['reference_ts'], kn=_f(p['value'], KMH), boe_kn=_f((fx.get(i) or {}).get('value'), KMH),
                richtung=_f(p.get('wind_direction')))


def smhi(i):
    w = {}
    for par, k in ((4, 'kn'), (21, 'boe_kn'), (3, 'richtung')):
        try:
            v = _get('https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/%d/station/%s/period/latest-hour/data.json'
                     % (par, i)).json().get('value') or []
        except requests.HTTPError:
            v = []
        if v:
            w[k] = (v[-1]['date'], v[-1]['value'])
    if 'kn' not in w:
        return dict(fehler='no wind in the last hour')
    return dict(zeit=_iso(datetime.fromtimestamp(w['kn'][0] / 1000, timezone.utc)), kn=_f(w['kn'][1], MS),
                boe_kn=_f(w.get('boe_kn', (0, None))[1], MS), richtung=_f(w.get('richtung', (0, None))[1]))


def frost(i):
    k = open(os.path.expanduser('~/.config/frost_client_id')).readline().strip()
    r = requests.get('https://frost.met.no/observations/v0.jsonld', auth=(k, ''), headers=UA, timeout=25, params={
        'sources': i, 'referencetime': 'latest', 'maxage': 'PT3H',
        'elements': 'wind_speed,wind_from_direction,max(wind_speed_of_gust PT10M),max(wind_speed_of_gust PT1H)'})
    if r.status_code == 404:
        return dict(fehler='no wind in the last 3 h')
    r.raise_for_status()
    w, zeit = {}, None
    for d in r.json().get('data', []):
        for o in d['observations']:
            if o['elementId'] not in w:
                w[o['elementId']] = o['value']
                if o['elementId'] == 'wind_speed':
                    zeit = d['referenceTime'].replace('.000Z', 'Z')
    if 'wind_speed' not in w:
        return dict(fehler='no wind in the last 3 h')
    boe = w.get('max(wind_speed_of_gust PT10M)', w.get('max(wind_speed_of_gust PT1H)'))
    return dict(zeit=zeit, kn=_f(w['wind_speed'], MS), boe_kn=_f(boe, MS), richtung=_f(w.get('wind_from_direction')))


def pioupiou(i):
    d = _get('https://api.pioupiou.fr/v1/live/%s' % i).json().get('data') or {}
    m = d.get('measurements') or {}
    if m.get('wind_speed_avg') is None:
        return dict(fehler='no measurement')
    return dict(zeit=m['date'].replace('.000Z', 'Z'), kn=_f(m['wind_speed_avg'], KMH), boe_kn=_f(m.get('wind_speed_max'), KMH),
                richtung=_f(m.get('wind_heading')))


_RMN = {'sitzung': None, 'zeit': 0}
import threading
_RMN_LOCK = threading.Lock()


def ispra_rmn(i):
    """mareografico.it hat keine Datenschnittstelle: die Stationsseite (Station steht im Cookie MG<PHPSESSID>)
    nennt den letzten Messwert. Sitzung 20 min wiederverwendet -> ein Seitenabruf je Klick."""
    import html as _h
    with _RMN_LOCK:
        if not _RMN['sitzung'] or time.time() - _RMN['zeit'] > 1200:
            se = requests.Session()
            se.headers.update(UA)
            se.cookies.set('A4IxScreenSize', '1920@1080@1@it', domain='www.mareografico.it')
            se.get('https://www.mareografico.it/', timeout=30).raise_for_status()
            _RMN.update(sitzung=se, zeit=time.time())
        se = _RMN['sitzung']
        sid = se.cookies.get('PHPSESSID', domain='www.mareografico.it') or se.cookies.get('PHPSESSID')
        se.cookies.set('MG' + sid, 'STAZ][1][%s][0][][][][][][1][1' % int(i), domain='www.mareografico.it', path='/')
        r = se.get('https://www.mareografico.it/it/stazioni.html', timeout=30)
        r.raise_for_status()
    t = re.sub(r'\s+', ' ', _h.unescape(re.sub(r'<[^>]+>', ' ', r.text)))
    titel = re.search(r'STAZIONE DI\s+([A-Z][A-Z \'.-]+?) (?:DATI|RETE|STAZIONE|SELEZIONA)', t)
    stazione = titel.group(1).strip() if titel else ''
    z = re.search(r'ULTIMO RILEVAMENTO (\d\d/\d\d/\d{4} \d\d:\d\d)', t)
    v = re.search(r'VELOCIT. VENTO ([\d.]+) m/s', t)
    d = re.search(r'DIREZIONE VENTO ([\d.]+)', t)
    namen = _ganz('rmn_namen', lambda: {z_['id']: z_['name'].upper() for z_ in csv.DictReader(open(os.path.join(
        ROOT, 'quellen', 'thermik', 'spotsuche', 'stationen_ispra_rmn.csv'), encoding='utf-8'))}, 1e9)
    if namen.get(str(i)) and not stazione.startswith(namen[str(i)]):
        _RMN['sitzung'] = None                                   # Seite zeigt eine andere Station: nichts ausgeben
        return dict(fehler='site returned another station (%s)' % stazione[:40])
    if not z or not v:
        return dict(fehler='no current wind reading')
    return dict(zeit=_lokal(z.group(1), '%d/%m/%Y %H:%M', 0), kn=_f(v.group(1), MS), boe_kn=None,
                richtung=_f(d.group(1)) if d else None)


def venezia(i):
    v = _ganz('venezia', lambda: _get('https://dati.venezia.it/sites/default/files/dataset/opendata/vento.json',
                                      headers={'User-Agent': 'Mozilla/5.0'}).json())
    x = [x for x in v if x['ID_stazione'] == i]
    if not x:
        return dict(fehler='station not in the current file')
    w = re.match(r'\s*([\d.]+) gradi, ([\d.]+) m/s, ([\d.]+) m/s', x[0].get('valore') or '')
    if not w:
        return dict(fehler='no wind reading')
    return dict(zeit=_lokal(x[0]['data'], '%Y-%m-%d %H:%M:%S', _mez()), richtung=_f(w.group(1)), kn=_f(w.group(2), MS),
                boe_kn=_f(w.group(3), MS))


def puertos(i):
    """PORTUS lastData: Werte als ganze Zahlen mit 'factor' (Wert/factor = m/s), Zeit UTC."""
    r = requests.post('https://portus.puertos.es/portussvr/api/lastData/station/%s' % int(i), params={'locale': 'es'},
                      json=['WIND'], headers=UA, timeout=25)
    r.raise_for_status()
    j = r.json() or {}
    w = {x['paramEseoo']: _f(x['valor'], 1 / x['factor'] if x.get('factor') else 1) for x in j.get('datos') or []}
    if w.get('WindSpeed') is None:
        return dict(fehler='no wind reading')
    return dict(zeit=_lokal(j['fecha'][:19], '%Y-%m-%d %H:%M:%S', 0), kn=round(w['WindSpeed'] * MS, 1),
                boe_kn=round(w['WindSpeedMax'] * MS, 1) if w.get('WindSpeedMax') is not None else None,
                richtung=w.get('WindDir'))


def arpav(i):
    d = _ganz('arpav', lambda: _get('https://api.arpa.veneto.it/REST/v1/meteo_meteogrammi',
                                    params={'orario': 0, 'rete': 'MGRAMMI', 'coordcd': 12}).json()['data'])
    x = [x for x in d if str(x['codseqst']) == i]
    if not x:
        return dict(fehler='no current reading')
    w = json.loads(x[0]['valore']) if isinstance(x[0]['valore'], str) else x[0]['valore']
    if not w or w.get('VELOCITA') is None:
        return dict(fehler='no current reading')
    return dict(zeit=_lokal(x[0]['dataora'][:19], '%Y-%m-%dT%H:%M:%S', _mez()), kn=_f(w.get('VELOCITA'), MS), boe_kn=None,
                richtung=_f(w.get('DIREZIONE')), hinweis='sensor at %s' % x[0]['tipo'].replace('VVENTO', '').lower())


def arpal(i):
    d = _ganz('arpal', lambda: _get('https://omirl.regione.liguria.it/Omirl/rest/stations/Vento',
                                    headers={'User-Agent': 'Mozilla/5.0'}).json())
    x = [x for x in d if x.get('shortCode') == i]
    if not x or x[0].get('value') is None:
        return dict(fehler='no current reading')
    return dict(zeit=_lokal(x[0]['refDate'][:19], '%Y-%m-%dT%H:%M:%S', 0), kn=_f(x[0]['value'], KMH), boe_kn=None, richtung=None)


def arpae(i):
    """Echtzeitdatei aller Stationen (8 MB, 48 h) -> 10 min vorgehalten, je Station nur der letzte Windwert."""
    def laden():
        w = {}
        for l in _get('https://dati-simc.arpae.it/opendata/osservati/meteo/realtime/realtime.jsonl', timeout=120).text.splitlines():
            if 'B11002' not in l:
                continue
            d = json.loads(l)
            k = '%s:%s:%s' % (d['network'], d['lon'], d['lat'])
            r = {}
            for x in d['data'][1:]:
                v = x.get('vars', {})
                if 'B11002' in v and (x.get('timerange') or [None])[0] in (254, 0):
                    r['ff'], r['dd'] = v['B11002']['v'], (v.get('B11001') or {}).get('v')
                if 'B11041' in v:
                    r['fx'] = v['B11041']['v']
            if 'ff' in r and (k not in w or d['date'] > w[k][0]):
                w[k] = (d['date'], r)
        return w
    w = _ganz('arpae', laden)
    if i not in w:
        return dict(fehler='no wind in the last 48 h')
    t, r = w[i]
    return dict(zeit=t, kn=_f(r['ff'], MS), boe_kn=_f(r.get('fx'), MS), richtung=_f(r.get('dd')))


NETZE = dict(arpav=arpav, arpal=arpal, arpae=arpae, puertos=puertos, venezia=venezia, ispra_rmn=ispra_rmn, pioupiou=pioupiou, ndbc=ndbc, coops=coops, fmi=fmi, imgw=imgw, lhmt=lhmt, ee=ee, meteocat=meteocat, lombardia=lombardia,
             suedtirol=suedtirol, meteotrentino=meteotrentino, aemet=aemet, dwd=dwd, dmi=dmi,
             geosphere=geosphere, meteoschweiz=meteoschweiz, smhi=smhi, frost=frost)


def hole(netz, i):
    f = NETZE.get(netz)
    if not f:
        return dict(fehler='no live access')
    try:
        return f(i)
    except Exception as e:                                        # noqa: BLE001
        return dict(fehler=str(e)[:200])
