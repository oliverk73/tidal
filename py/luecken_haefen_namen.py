#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Namen, Region, Land und Zeitzone fuer die Hafen-Lueckensaetze (Oliver 13.11.2026: alle 243 Vorschlaege als
FES-Saetze anlegen, in fremder Schrift transliteriert; was nicht gebraucht wird, loescht Oliver).

Eingabe harmonics/help/luecken_haefen_vorschlag_20261113.csv (py/luecken_haefen.py), Ausgabe eine Auswahl-CSV im
Format von py/fes_neu_geeicht.py --welt (Position = OSM-Hafen, dort mit --exakt anlegen).
  * Name: OSM-Name ohne Hafen-Typwoerter (Pelabuhan, Port of, ferjekai ...); fremde Schrift -> name:en bzw.
    Transliteration (Japanisch pykakasi, sonst unidecode). Bleibt nur ein Gattungswort uebrig ("Water Taxi Stop"),
    gilt der Ort aus der Nominatim-Rueckwaertssuche. Insel aus der Adresse als Klammer, wenn nicht schon im Namen.
  * Region/Land: Nominatim reverse zoom 10 einmal in Landessprache, einmal englisch; lateinische Landesform bevorzugt
    (Maluku Utara, Islas Canarias), Land immer englisch, USA nur Bundesstaat.
  * Zeitzone: timezonefinder.
Cache: water_levels/luecken_schlau_cache.json (wie py/luecken_schlau.py).

Usage: venv/bin/python py/luecken_haefen_namen.py [--aus CSV]
"""
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EIN = os.path.join(ROOT, 'harmonics/help/luecken_haefen_vorschlag_20261113.csv')
AUS = os.path.join(ROOT, 'harmonics/help/luecken_haefen_auswahl_20261113.csv')
CACHE = os.path.join(ROOT, 'water_levels/luecken_schlau_cache.json')
OSM = os.path.join(ROOT, 'tide_tables/catalogues/osm_haefen')
RAUS = {'Grand Tortue Ahmeyim'}
HAND = {                                   # von Hand nach Durchsicht 13.11.2026 (OSM-Name -> Name)
    'ميناء الضبة النفطي': 'Ad Dabbah (oil terminal)', 'ميناء الزيت': 'Little Aden (oil harbour)', 'Pont': 'Kei Mouth',
    'Nuqui - Termales': 'Termales (Nuqui)', 'MTBS Wharf': 'Bunawan (Davao)', '石岛湾核电大件码头': 'Shidao Bay (Rongcheng)',
    '悪石島': 'Akusekijima (Tokara)', '諏訪之瀬島': 'Suwanosejima (Tokara)', '平島': 'Tairajima (Tokara)',
    '口之島': 'Kuchinoshima (Tokara)', '黒島・片泊': 'Kuroshima (Katadomari)', '黒島': 'Kuroshima (Yaeyama)',
    '長浜港': 'Nagahama (Shimo-Koshikijima)', 'トッピーターミナル': 'Anbo (Yakushima)', '大原港': 'Ohara (Iriomote)',
    '花嶼碼頭': 'Huayu (Penghu)', '青岛': 'Tianheng (Jimo)', '仰口码头': 'Yangkou (Laoshan)', 'EPI Island': 'Lamen Bay (Epi)',
    'Ostricultura': 'Quinchao (Chiloe)', 'Fred. Olsen Express - Benchi Express Terminal': 'Vallehermoso (La Gomera)',
    'MV JR OBETA Ferries': 'Abaokoro (North Tarawa)', 'North Tarawa - South Tarawa': 'Nawerewere (North Tarawa)',
    'Lyngøy båtkai': 'Lyngøy', 'Gardsøya kai Vega': 'Gardsøya (Vega)', 'speed boat arrival (low season)': 'Ko Lipe',
    "Port de N'Diago ميناء نديجو": "N'Diago", 'Buca Bay Charter': 'Buca Bay', 'Korean Wharf': 'Korean Wharf (Taveuni)',
    'Ferry to Bustins Island': 'Bustins Island', 'Eagle Island Cruise': 'Eagle Island',
    'Alaska Marine Highway Terminal Coffman Cove': 'Coffman Cove', 'Duck Harbor Boat Landing': 'Duck Harbor (Isle au Haut)',
    'Hovercraft': 'Tagrin (Lungi)', 'Pantai': 'Bayun', 'Muelle Municipal': 'Golfito', 'Puerto Toro': 'Puerto Toro (Isla Navarino)',
    'Puerto Bonito': 'Puerto Bonito', 'Arrêt / Départ Speedboat Bundhaya sur la plage.': 'Bundhaya beach'}            # Gasplattform vor der Kueste, kein Hafen
VORN = re.compile(r"""^(pelabuhan\s+ferry|pelabuhan\s+feri|pelabuhan\s+desa|pelabuhan\s+penyeberangan|ferry\s+to|pelabuhan\s+laut|pelabuan\s+laut|pelabuhan|pelabuan|dermaga|knmp\s+desa|
    port\s+multifonctions\s+de|port\s+autonome\s+de|port\s+of|port\s+de|port|puerto\s+de\s+la|puerto\s+del|puerto\s+de|puerto|
    porto\s+de\s+pesca\s+de|porto\s+de|porto|muelle\s+de|muelle|embarcadero\s+de|embarcadero|rampa\s+de|rampa|terminal\s+ferry|
    terminal\s+de|terminal|ferry\s+terminal|cais\s+de|cais|ponton|gare\s+maritime\s+de|water\s+taxi\s+stop|water\s+taxi)\s+""", re.I | re.X)
HINTEN = re.compile(r"""\s+(municipal\s+fish\s+port|fishing\s+port|fishing\s+harbou?r|fish\s+port|ferry\s+terminal|ferry\s+wharf|
    ferry\s+port|ferry\s+landing|ferry|port|harbou?r|wharf|jetty|pier|dock|landing|boat\s+ramp|quay|terminal|marina|
    ferjekai|ferjeleie|hurtigb[aå]tkai|b[aå]tkai|kai|water\s+taxi|charter|cruise|ferries|boat|forretningsdrift|havfiske|fisk|gyo\s*ko|gyokou|kou|ko|ma\s*tou|matou)$""", re.I | re.X)


def kern_name(s):
    alt = None
    while alt != s:
        alt = s
        s = VORN.sub('', s).strip(' -,')
        s = HINTEN.sub('', s).strip(' -,')
    return s


STAAT_VORN = re.compile(r'^(Région de|Región de|Región del|Región|Provincia de|Province de|Province of)\s+', re.I)
STAAT_NAME = {'Canarias': 'Islas Canarias'}
GATTUNG = re.compile(r'(?i)\b(municipal|speed\s*boat|arrival|hovercraft|express|arr[eê]t|d[ée]part|ferries|terminal|oil|ostricultura|pantai|taxi|mv\s)\b|\s-\s')
STAAT_WEG = re.compile(r'\s+(Province|Region|Prefecture|Governorate|Municipality|County|fylke|Regency|District)$', re.I)


def lateinisch(s):
    return all(unicodedata.name(c, '').startswith(('LATIN', 'SPACE', 'DIGIT', 'HYPHEN', 'APOSTROPHE', 'FULL STOP',
                                                    'COMMA', 'LEFT PAR', 'RIGHT PAR', 'SOLIDUS', 'AMPERSAND'))
               or not c.isalpha() for c in s)


def translit(s):
    if re.search(r'[぀-ヿ一-鿿]', s) and not re.search(r'[가-힯]', s):
        import pykakasi
        k = pykakasi.kakasi()
        return ' '.join(x['hepburn'].capitalize() for x in k.convert(s) if x['hepburn'].strip())
    from unidecode import unidecode
    return unidecode(s)


def latin1(t):
    return ''.join(c if ord(c) < 256 else unicodedata.normalize('NFKD', c).encode('ascii', 'ignore').decode() for c in t)


def main(argv):
    aus = argv[argv.index('--aus') + 1] if '--aus' in argv else AUS
    tags = {}
    for f in ('ferry_terminal.json', 'industrial_port.json', 'seamark_harbour.json'):
        for e in json.load(open(os.path.join(OSM, f)))['elements']:
            tags['osm:%s/%d' % (e['type'], e['id'])] = e.get('tags', {})
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    letzte = [0.0]

    def hole(url):
        if url in cache:
            return cache[url]
        time.sleep(max(0.0, 1.1 - (time.time() - letzte[0])))
        for v in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'weather-tides/1.0'})
                cache[url] = json.load(urllib.request.urlopen(req, timeout=60))
                break
            except Exception:                                       # noqa: BLE001
                time.sleep(5 * (v + 1))
        letzte[0] = time.time()
        if len(cache) % 25 == 0:
            json.dump(cache, open(CACHE, 'w'))
        return cache.get(url)

    from timezonefinder import TimezoneFinder
    tf = TimezoneFinder()
    Z = list(csv.DictReader(open(EIN, encoding='utf-8')))
    out = []
    for z in Z:
        if z['name'] in RAUS:
            continue
        la, lo = float(z['lat']), float(z['lon'])
        t = tags.get(z['osm'], {})
        q = dict(lat='%.5f' % la, lon='%.5f' % lo, format='jsonv2', zoom=14, addressdetails=1, namedetails=1)
        lokal = hole('https://nominatim.openstreetmap.org/reverse?' + urllib.parse.urlencode(q)) or {}
        en = hole('https://nominatim.openstreetmap.org/reverse?' + urllib.parse.urlencode(dict(q, **{'accept-language': 'en'}))) or {}
        al, ae = lokal.get('address', {}), en.get('address', {})

        def feld(*k):
            for x in k:
                v = al.get(x)
                if v and lateinisch(v):
                    return v
                if ae.get(x):
                    return ae[x] if lateinisch(ae[x]) else translit(ae[x])
            return ''
        land = ae.get('country', '') or z['naechster_satz'].split(', ')[-1]
        land = {'United States of America': 'United States'}.get(land, land)
        if al.get('country_code') == 'ph':
            region = feld('province', 'state')
        elif al.get('country_code') == 'jp':
            region = feld('province', 'state')
        else:
            region = feld('state', 'province', 'region', 'county')
        region = STAAT_NAME.get(region, region)
        region = STAAT_VORN.sub('', STAAT_WEG.sub('', region).replace(' Prefecture', ''))
        ortname = feld('village', 'town', 'city', 'hamlet', 'suburb', 'municipality', 'neighbourhood', 'isolated_dwelling')
        insel = feld('island', 'archipelago')
        # Hafenname
        roh = t.get('name') or z['name']
        if not lateinisch(roh):
            lat_tag = next((t[k] for k in ('name:en', 'name:latin', 'int_name', 'name:ja-Latn', 'name:zh-Latn-pinyin', 'name:ru-Latn')
                            if t.get(k) and lateinisch(t[k])), None)
            if lat_tag:
                roh = lat_tag
            elif re.search(r'[\u0400-\u04ff\u0370-\u03ff\u3040-\u30ff]', roh) or al.get('country_code') == 'jp':     # Kyrillisch, Griechisch, Japanisch
                roh = translit(roh)
            else:                                                         # Arabisch, Chinesisch, Thai ...: Ort aus OSM (englisch)
                roh = ortname or translit(roh)
        roh = re.sub(r'\s+[؀-ۿ].*$', '', roh)              # "Chindini تشينديني"
        kern = kern_name(roh.replace(' - ', ' '))
        if len(re.sub(r'[^A-Za-zÀ-ÿ]', '', kern)) < 3 or re.search(r'(?i)\b(access point|trailhead|stop)\b', kern) or GATTUNG.search(roh):
            kern = ortname or roh
        name = kern
        if insel.startswith(('Kabupaten', 'Kota ', 'Kecamatan')):
            insel = ''
        if insel and insel.lower() not in name.lower() and (not ortname or insel.lower() != ortname.lower()):
            name = '%s (%s)' % (name, insel)
        name = HAND.get(z['name'], name)
        tz = tf.timezone_at(lat=la, lng=lo) or tf.closest_timezone_at(lat=la, lng=lo) or 'UTC'
        tz = tz.replace('America/Argentina/', 'America/')
        if land == 'United States':
            region = ae.get('state', region)
        out.append(dict(land=latin1(land), cc=al.get('country_code', '').upper(), region=latin1(region), name=latin1(name),
                        osm_name=z['name'], osm_typ=z['art'], einwohner=0, urteil='gut', lat=z['lat'], lon=z['lon'],
                        fes_median_pct=z['fes_median_pct'], tz=tz, tranche=z['tranche'], ort=ortname, insel=insel))
    json.dump(cache, open(CACHE, 'w'))
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(len(out), 'Saetze ->', os.path.relpath(aus, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
