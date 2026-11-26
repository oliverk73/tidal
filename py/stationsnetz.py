#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Amtliche Wetterstationen fuer die Karte: METAR-Flughaefen + WMO-SYNOP-Stationen (25.11.2026, Oliver).

Quellen (amtlich, frei):
  METAR  NOAA Aviation Weather Center, https://aviationweather.gov/data/cache/stations.cache.json.gz
         (siteType enthaelt 'METAR')
  SYNOP  WMO OSCAR/Surface, https://oscar.wmo.int/surface/rest/api/search/station?stationClass=synopLand
         (nur Stationen mit klassischer WMO-Nummer 0-20000-0-NNNNN, Status operational/partlyOperational/unknown)
Beide Listen werden ueber die WMO-Nummer verbunden (aviationweather.gov fuehrt sie bei ~3900 Flughaefen).
Belege fuer "SYNOP-Station = Flughafen" (26.11.2026): WMO-Nummer im AWC-Katalog, sonst NOAA ISD isd-history.csv
und NOAA GHCNh ghcnh-station-list.csv (je Station WMO + ICAO; nur als Beweis FUER eine Verbindung, alte Codes dort
beweisen keine Verschiedenheit). Erst danach per Position: <= 2 km, bis 5 km nur mit Flughafenwort im SYNOP-Namen.

    venv/bin/python py/stationsnetz.py [--laden]
      -> static/wind_stations/stationsnetz.json
Spalten je Station: [lat, lon, name, icao, wmo, hoehe_m, art, wdqms]
  art: 1 = METAR, 2 = SYNOP, 3 = beides;  wdqms: WMO-Bewertung, ob Meldungen tatsaechlich ankommen (o/p/n/u)
"""
import gzip
import math
import re
import unicodedata
import json
import os
import sys

import numpy as np
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, 'quellen', 'thermik', 'stationsnetz')
AUS = os.path.join(ROOT, 'static', 'wind_stations', 'stationsnetz.json')
UA = {'User-Agent': 'weather-tides/1.0'}
URL_METAR = 'https://aviationweather.gov/data/cache/stations.cache.json.gz'
URL_SYNOP = 'https://oscar.wmo.int/surface/rest/api/search/station?stationClass=synopLand'
URL_ISD = 'https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv'
URL_GHCNH = 'https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh-station-list.csv'
URL_AKTIV = 'https://aviationweather.gov/data/cache/metars.cache.csv.gz'   # alle METARs der letzten Stunden
DUBL = os.path.join(ROOT, 'harmonics', 'help', 'stationsnetz_dubletten.csv')
WDQMS = {'operational': 'o', 'partlyOperational': 'p', 'silent': 'n'}


def laden():
    os.makedirs(Q, exist_ok=True)
    for url, datei in ((URL_METAR, 'stations.cache.json.gz'), (URL_SYNOP, 'oscar_synop.json'),
                       (URL_AKTIV, 'metars.cache.csv.gz'), (URL_ISD, 'isd-history.csv'),
                       (URL_GHCNH, 'ghcnh-station-list.csv')):
        r = requests.get(url, headers=UA, timeout=600)
        r.raise_for_status()
        open(os.path.join(Q, datei), 'wb').write(r.content)
        print(datei, len(r.content) // 1024, 'KB')


def titel(s):
    """OSCAR-Namen stehen meist in Grossbuchstaben."""
    s = ' '.join((s or '').split())
    return s.title() if s.isupper() else s


ALLGEMEIN = {'airport', 'arpt', 'intl', 'international', 'aeropuerto', 'aeroporto', 'aeroport', 'aerodrome', 'airfield',
             'flughafen', 'flugplatz', 'field', 'base', 'municipal', 'regional', 'county', 'station', 'city', 'mil',
             'heliport', 'lufthavn', 'flygplats', 'lotnisko', 'letiste', 'havaalani', 'north', 'south', 'east', 'west'}


def woerter(name):
    t = unicodedata.normalize('NFKD', name.lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.split(r'[^a-z]+', t) if len(w) >= 4 and w not in ALLGEMEIN}


FLUGHAFENWORT = re.compile(r'airport|arpt|a[eé]rop|aeroporto|aero\b|aero |intl|int\.|internacional|international|airfield|'
                           r'flughafen|flugplatz|havalimani|lufthavn|flygplats|lotnisko|letiste|\b(a|ap|aws|aero)\b', re.I)
WIDER = []          # Positionspaare, denen eine Stationsliste widerspricht


def ortsabgleich(stationen, bel):
    """Flughaefen ohne WMO-Nummer beim AWC (z.B. EDHK) mit der SYNOP-Station am selben Platz verbinden:
    <= 2 km, oder <= 5 km mit gemeinsamem Namenswort; je METAR hoechstens eine SYNOP-Station (die naechste)."""
    alle = [s for k, s in stationen.items() if k[0] == 'm']            # alle METAR-Plaetze, auch schon verbundene
    metar = [(k, s) for k, s in stationen.items() if k[0] == 'm' and s[6] == 1]   # noch ohne SYNOP-Partner
    synop = [(k, s) for k, s in stationen.items() if k[0] == 's']
    if not metar or not synop:
        return 0
    mla = np.radians([s[0] for _, s in metar])
    mlo = np.radians([s[1] for _, s in metar])
    ala = np.radians([s[0] for s in alle])
    alo = np.radians([s[1] for s in alle])

    def km(la, lo, la2, lo2):
        return 12742 * np.arcsin(np.sqrt(np.sin((la2 - la) / 2) ** 2 + math.cos(la) * np.cos(la2) * np.sin((lo2 - lo) / 2) ** 2))
    paare = []
    for k, s in synop:
        la, lo = math.radians(s[0]), math.radians(s[1])
        d = km(la, lo, mla, mlo)
        naechster = float(km(la, lo, ala, alo).min())          # naechster METAR-Platz ueberhaupt
        for i in np.where(d <= 5)[0]:
            if d[i] > 1 and d[i] > naechster + 1e-6:          # ab 1 km nur der naechste Flughafen
                continue
            mname = metar[i][1][2]
            platz = mname.split('/', 1)[1] if '/' in mname else mname      # "San Diego/Montgomery": Platzname zaehlt
            if widerspruch(metar[i][1][3], s[4], bel):
                WIDER.append((metar[i][1][3], s[4], s[2], round(float(d[i]), 2)))
                continue
            # ohne Listenbeleg: <= 2 km, oder <= 5 km mit gemeinsamem Namenswort UND Flughafenwort im SYNOP-Namen
            # (26.11.: Anholt Havn, Edinburgh Gogarbank, Bottoms Wood St. Helena sind eigene Messorte)
            if d[i] <= 2 or (woerter(s[2]) & woerter(platz) and FLUGHAFENWORT.search(s[2])):
                paare.append((float(d[i]), k, i))
    vergeben_m, vergeben_s, n = set(), set(), 0
    for d, k, i in sorted(paare):
        if i in vergeben_m or k in vergeben_s:
            continue
        vergeben_m.add(i)
        vergeben_s.add(k)
        m = metar[i][1]
        syn = stationen.pop(k)
        m[4], m[6], m[7] = syn[4], 3, syn[7]
        n += 1
    return n


RANG = {'o': 0, 'p': 1, 'u': 2, 'n': 3, '': 2}


def belege():
    """Stationslisten mit WMO-Nummer UND ICAO-Code je Station = Beleg, dass SYNOP-Station und Flughafen eins sind
    (Oliver 26.11.2026): NOAA ISD isd-history.csv (USAF = WMO*10, eingefroren 08/2025; Eintraege ab 2010) und
    NOAA GHCNh ghcnh-station-list.csv. Gibt (wmo -> {icao}, icao -> {wmo}) zurueck."""
    import csv
    w2i, i2w = {}, {}

    def dazu(w, i):
        w, i = w.strip(), i.strip().upper()
        if re.fullmatch(r'\d{5}', w) and re.fullmatch(r'[A-Z0-9]{4}', i):
            w2i.setdefault(w, set()).add(i)
            i2w.setdefault(i, set()).add(w)
    pi = os.path.join(Q, 'isd-history.csv')
    if os.path.exists(pi):
        for z in csv.DictReader(open(pi, encoding='latin1')):
            u = z['USAF']
            if z['ICAO'].strip() and len(u) == 6 and u.isdigit() and u.endswith('0') and u[:2] != '99' and z['END'] >= '2010':
                dazu(u[:5], z['ICAO'])
    pg = os.path.join(Q, 'ghcnh-station-list.csv')
    if os.path.exists(pg):
        for z in csv.DictReader(open(pg, encoding='utf-8', errors='replace')):
            if z['WMO_ID'].strip() and z['ICAO'].strip():
                dazu(z['WMO_ID'].strip().zfill(5), z['ICAO'])
    return w2i, i2w


def widerspruch(icao, wmo, bel):
    """True, wenn eine Stationsliste die WMO-Nummer einem ANDEREN, heute noch gefuehrten Flughafen in der Naehe
    (<= 25 km) gibt. Eine abweichende Kennung allein beweist nichts: die Listen fuehren alte Codes (Kiel ETMK,
    Johannesburg FAJS, Funchal LPFU) und alte Nummern (EDDM 10866)."""
    for i in bel[0].get(wmo, ()):
        if i != icao and i in AKTUELL and km_grob(AKTUELL[i], AKTUELL.get(icao)) <= 25:
            return True
    return False


AKTUELL = {}        # icao -> (lat, lon) aller METAR-Plaetze im AWC-Katalog


def km_grob(a, b):
    if not a or not b:
        return 1e9
    dy = (a[0] - b[0]) * 111.2
    dx = (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def nach_beleg(stationen, bel):
    """SYNOP-Station mit dem Flughafen verbinden, den eine Stationsliste fuer ihre WMO-Nummer nennt (<= 25 km)."""
    w2i = bel[0]
    n = 0
    for k in [k for k in stationen if k[0] == 's']:
        syn = stationen[k]
        for icao in sorted(w2i.get(k[1], ())):
            m = stationen.get(('m', icao))
            if not m or m[6] != 1:
                continue
            dy = (m[0] - syn[0]) * 111.2
            dx = (m[1] - syn[1]) * 111.2 * math.cos(math.radians(syn[0]))
            if dx * dx + dy * dy > 25 ** 2:
                continue
            m[4], m[6], m[7] = syn[4], 3, syn[7]
            del stationen[k]
            n += 1
            break
    return n


def positionsdubletten(stationen, bel):
    """Eintraege am selben Punkt (<= 150 m) zusammenfassen (26.11.2026):
    - mehrere ICAO-Kennungen = umbenannter Flughafen (KPBI->KDJT, FVHA->FVRG): die Kennung, die gerade METARs sendet
      (metars.cache), sonst die mit SYNOP-Partner, sonst die erste; eine WMO-Nummer wandert zur behaltenen;
    - reine SYNOP-Stationen daneben (konventionell + automatisch, Brasilien 83xxx/86xxx): die mit dem besten
      WDQMS-Empfang (o > p > u > n), bei Gleichstand die kleinere Nummer; Partner eines METAR-Platzes ohne SYNOP.
    Gibt die entfernten Eintraege zurueck."""
    aktiv = set()
    pa = os.path.join(Q, 'metars.cache.csv.gz')
    if os.path.exists(pa):
        import csv
        for z in csv.reader(l for l in gzip.open(pa, 'rt', errors='replace') if not l.startswith(('No ', 'errors', 'warnings'))):
            if len(z) > 1:
                aktiv.add(z[1])
    print('METAR gerade aktiv:', len(aktiv))
    keys = list(stationen)
    zelle = {}
    for k in keys:
        s = stationen[k]
        zelle.setdefault((round(s[0] * 500), round(s[1] * 500)), []).append(k)
    eltern = {k: k for k in keys}

    def wurzel(k):
        while eltern[k] != k:
            eltern[k] = eltern[eltern[k]]
            k = eltern[k]
        return k
    for (a, b), ks in zelle.items():
        nachbarn = [k2 for da in (-1, 0, 1) for db in (-1, 0, 1) for k2 in zelle.get((a + da, b + db), [])]
        for k in ks:
            s = stationen[k]
            for k2 in nachbarn:
                if k2 <= k:
                    continue
                t = stationen[k2]
                dy = (t[0] - s[0]) * 111.2
                dx = (t[1] - s[1]) * 111.2 * math.cos(math.radians(s[0]))
                if dx * dx + dy * dy <= 0.15 ** 2:
                    eltern[wurzel(k2)] = wurzel(k)
    gruppen = {}
    for k in keys:
        gruppen.setdefault(wurzel(k), []).append(k)
    weg = []
    for ks in gruppen.values():
        if len(ks) < 2:
            continue
        m = [k for k in ks if k[0] == 'm']
        sy = [k for k in ks if k[0] == 's']
        behalten = []
        if m:
            an = [k for k in m if k[1] in aktiv]
            if len(an) > 1:
                behalten = an                                 # beide senden: zwei Plaetze, nichts entfernen
            else:
                kand = an or sorted(m, key=lambda k: (stationen[k][6] != 3, k[1]))[:1]
                k0 = kand[0]
                for k in m:
                    if k != k0 and stationen[k][6] == 3 and stationen[k0][6] == 1:   # SYNOP-Partner uebernehmen
                        stationen[k0][4], stationen[k0][6], stationen[k0][7] = stationen[k][4], 3, stationen[k][7]
                behalten = [k0]
            if sy:
                sy.sort(key=lambda k: (RANG.get(stationen[k][7], 2), k[1]))
                # SYNOP-Eintraege, die laut Stationsliste zu einem anderen Flughafen gehoeren, bleiben eigene Stationen
                for k in list(sy):
                    if any(widerspruch(b[1], k[1], bel) for b in behalten):
                        WIDER.append((behalten[0][1], k[1], stationen[k][2], 0))
                        sy.remove(k)
                        behalten.append(k)
                ziel = [k for k in behalten if k[0] == 'm' and stationen[k][6] == 1]
                if ziel and sy:
                    stationen[ziel[0]][4], stationen[ziel[0]][6], stationen[ziel[0]][7] = sy[0][1], 3, stationen[sy[0]][7]
        else:
            behalten = [sorted(sy, key=lambda k: (RANG.get(stationen[k][7], 2), k[1]))[0]]
        for k in ks:
            if k not in behalten:
                weg.append((stationen[k], [stationen[b] for b in behalten]))
                del stationen[k]
    return weg


def main(argv):
    if '--laden' in argv or not os.path.exists(os.path.join(Q, 'oscar_synop.json')):
        laden()
    stationen = {}
    nach_wmo = {}
    for x in json.load(gzip.open(os.path.join(Q, 'stations.cache.json.gz'))):
        if 'METAR' not in (x.get('siteType') or []) or x.get('lat') is None or abs(x['lat']) > 90 or abs(x['lon']) > 180:
            continue
        icao = x.get('icaoId') or x['id']
        s = [round(x['lat'], 4), round(x['lon'], 4), ' '.join((x.get('site') or icao).split()), icao,
             x.get('wmoId') or '', x.get('elev'), 1, '']
        stationen[('m', icao)] = s
        if x.get('wmoId'):
            nach_wmo[x['wmoId']] = s
    n_synop = 0
    for x in json.load(open(os.path.join(Q, 'oscar_synop.json')))['stationSearchResults']:
        if x.get('stationStatusCode') not in ('operational', 'partlyOperational', 'unknown') or x.get('latitude') is None:
            continue
        wmo = ''
        for w in x.get('wigosStationIdentifiers') or []:
            t = w['wigosStationIdentifier'].split('-')
            if len(t) == 4 and t[1] == '20000' and t[3].isdigit() and len(t[3]) == 5:
                wmo = t[3]
                if w.get('primary'):
                    break
        if not wmo:
            continue
        n_synop += 1
        bew = WDQMS.get(x.get('stationAssessedStatusCode'), 'u')
        if wmo in nach_wmo:                                   # Flughafen mit SYNOP: Position/Name vom AWC
            s = nach_wmo[wmo]
            s[6] = 3
            s[7] = bew
            continue
        stationen[('s', wmo)] = [round(x['latitude'], 4), round(x['longitude'], 4), titel(x['name']), '', wmo,
                                 x.get('elevation'), 2, bew]
    AKTUELL.update({k[1]: (v[0], v[1]) for k, v in stationen.items() if k[0] == 'm'})
    bel = belege()
    print('Belege WMO<->ICAO (NOAA ISD + GHCNh): %d WMO-Nummern' % len(bel[0]))
    print('per Stationsliste verbunden:', nach_beleg(stationen, bel))
    n_ort = ortsabgleich(stationen, bel)
    print('per Position verbunden:', n_ort)
    weg = positionsdubletten(stationen, bel)
    print('Positionspaare verworfen (Liste nennt andere Station):', len(WIDER))
    with open(DUBL, 'w', encoding='utf-8') as f:
        f.write('entfernt_name,entfernt_icao,entfernt_wmo,lat,lon,behalten\n')
        for s, b in weg:
            f.write('"%s",%s,%s,%s,%s,"%s"\n' % (s[2].replace('"', "'"), s[3], s[4], s[0], s[1],
                    ' | '.join('%s %s %s' % (x[2].replace('"', "'"), x[3], x[4]) for x in b)))
    print('am selben Punkt zusammengefasst:', len(weg), '->', os.path.relpath(DUBL, ROOT))
    liste = sorted(stationen.values(), key=lambda s: (s[0], s[1]))
    # Nationale Netze mit freiem Archiv (Kataloge der Spotsuche, py/spotsuche.py -> stationen_alle.csv), Typ 4:
    # [lat, lon, name, '', '', hoehe, 4, '', netz, id]  (z.B. DWD-Sturmwarnnetz Darsser Ort)
    kat = os.path.join(ROOT, 'quellen', 'thermik', 'spotsuche', 'stationen_alle.csv')
    n_nat = 0
    if os.path.exists(kat):
        import csv
        gesehen, orte = set(), set()
        for z in csv.DictReader(open(kat, encoding='utf-8')):
            try:
                la, lo = float(z['lat']), float(z['lon'])
            except (TypeError, ValueError):
                continue
            if (abs(la) < 0.01 and abs(lo) < 0.01) or (z['netz'], z['id']) in gesehen:
                continue
            # dasselbe Netz am selben Punkt (<~50 m): nur der erste Eintrag (Kataloge stehen neueste zuerst)
            punkt = [(z['netz'], round(la * 2000 + dy), round(lo * 2000 * math.cos(math.radians(la)) + dx))
                     for dy in (-0.5, 0.5) for dx in (-0.5, 0.5)]
            if any(q in orte for q in punkt):
                continue
            orte.update(punkt)
            gesehen.add((z['netz'], z['id']))
            alt = round(float(z['alt'])) if z.get('alt') not in (None, '', 'nan') else None
            liste.append([round(la, 4), round(lo, 4), ' '.join((z['name'] or z['id']).split()), '', '', alt, 4, '',
                          z['netz'], z['id']])
            n_nat += 1
    print('nationale Netze:', n_nat)
    for s in liste:
        if isinstance(s[5], float):
            s[5] = round(s[5])
    aus = dict(stand=__import__('datetime').date.today().isoformat(),
               quellen=['NOAA Aviation Weather Center (METAR sites)', 'WMO OSCAR/Surface (synoptic land stations)',
                       'national networks with open archive (py/spotsuche.py)'],
               spalten=['lat', 'lon', 'name', 'icao', 'wmo', 'elev_m', 'type', 'wdqms', 'netz', 'id'],
               stationen=liste)
    with open(AUS, 'w', encoding='utf-8') as f:
        json.dump(aus, f, ensure_ascii=False, separators=(',', ':'))
    art = [s[6] for s in liste]
    print('%d Stationen: %d nur METAR, %d nur SYNOP, %d beides (SYNOP gesamt %d) -> %s, %d KB'
          % (len(liste), art.count(1), art.count(2), art.count(3), n_synop, os.path.relpath(AUS, ROOT),
             os.path.getsize(AUS) // 1024))


if __name__ == '__main__':
    main(sys.argv[1:])
