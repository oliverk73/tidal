#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BSH-Gezeitentafeln "Europaeische Gewaesser" 2027 (Ortsverzeichnis) gegen den Bestand abgleichen.

Quelle: tide_tables/germany_bsh/GT27_Inhaltsverzeichnis.pdf (S. 219-230, nur Name + BSH-Nummer, keine Koordinaten).
Die Nummern laufen die Kueste entlang (Groenland/Island 1-100, Spitzbergen ~106-125, Norwegen 346-540,
Deutschland 600-816, NL/BE 820-937, Frankreich Nord 941-1035, GB 1092-1610, Irland 1630-1781,
Biskaya 1800-1934, Iberien 1940-2022, Ceuta, Atlantik-Inseln 2202-2224).
Mehrere Verzeichnisnamen mit derselben Nummer = ein Ort (Aliasse).

Verortung:
  1. 'bsh'   deutsche Orte: Position aus tide_tables/germany_bsh/json (bshnr, 'P' = ohne Buchstaben)
  2. 'saat'  Name im ganzen Europa-Ausschnitt eindeutig im Bestand (alle Treffer <= 30 km beisammen),
             und die Lage passt zu den Nummernnachbarn
  3. 'name'  Name unscharf im Bestand im Umkreis der Nummernnachbarn
  4. 'geo'   Nominatim im Umkreis (Cache water_levels/BSH_GT_nominatim.json, 1/s)
Abdeckung: naechster Wasserstands-Satz zur Position; <= 5 km gedeckt, 5-15 km nah, > 15 km Luecke.
Schreibt harmonics/help/bsh_gt27_abgleich.csv.
Usage: venv/bin/python py/bsh_gt_abgleich.py [--ohne-netz]
"""
import collections
import csv
import difflib
import glob
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import osm_land                                                    # noqa: E402
from ukho_index_abgleich import norm, kern, km, GATTUNG            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'tide_tables/germany_bsh/GT27_Inhaltsverzeichnis.pdf')
JSON_DIR = os.path.join(ROOT, 'tide_tables/germany_bsh/json')
AUS = os.path.join(ROOT, 'harmonics/help/bsh_gt27_abgleich.csv')
CACHE = os.path.join(ROOT, 'water_levels/BSH_GT_nominatim.json')
GATTUNG = GATTUNG | {'fjord', 'fjordur', 'fjorden', 'loch', 'lough', 'ria', 'rio', 'porto', 'praia', 'enseada', 'baia', 'ile', 'iles',
                     'ny', 'tonne', 'leuchtturm', 'feuerschiff', 'einfahrt', 'aussen', 'hafen', 'sund', 'firth', 'head', 'harbour',
                     'insel', 'alter', 'neuer', 'anleger', 'bake', 'reede', 'seeseite', 'hafeneinfahrt', 'barre', 'muendung', 'ost', 'nord', 'sud', 'west', 'l', 'd', 'en', 'van', 'aan', 'zeegat', 'sur', 'mer', 'pointe'}
NUM = r'\d+[a-zA-Z]?(?:\s*[–-]\s*\d+[a-zA-Z]?)?'
EINTRAG = re.compile(r'(\S.*?)\s*(?:\.\s?)+\s*(' + NUM + r'(?:,\s*' + NUM + r')*)(?=\s{2,}|\s*$)')
EUROPA = (25.0, 84.0, -75.0, 66.0)
# Nummernbereiche mit Spruengen: Nachbarnummern helfen dort nicht (Kanaren landeten auf den Azoren)
REGION = [((1, 15), (59.0, 78.0, -46.0, -15.0)),           # Ostgroenland
          ((16, 103), (63.0, 67.0, -25.0, -13.0)),         # Island
          ((104, 104), (70.5, 71.5, -9.5, -7.0)),          # Jan Mayen
          ((105, 124), (74.0, 81.0, 9.0, 34.0)),           # Spitzbergen, Baereninsel
          ((125, 125), (79.0, 82.5, 44.0, 66.0)),          # Franz-Josef-Land
          ((1318, 1336), (61.3, 62.5, -7.8, -6.2)),        # Faeroeer
          ((2190, 2199), (35.0, 36.2, -6.5, -4.8)),        # Ceuta, Tanger
          ((2202, 2209), (36.8, 40.0, -31.5, -24.5)),      # Azoren
          ((2210, 2216), (32.3, 33.3, -17.5, -16.0)),      # Madeira, Porto Santo
          ((2217, 2230), (27.4, 29.5, -18.5, -13.2))]      # Kanaren


# Von keiner Suche gefunden (Tonnen, Tuerme, Schleusen, Schreibweisen): ungefaehre Lage von Hand, nur fuer die Abdeckung
HAND = {'113': (79.56, 11.0), '435': (66.50, 12.10), '435a': (66.43, 12.62), '445b': (64.73, 11.18), '445c': (64.86, 11.60),
        '464': (64.01, 11.49), '608': (54.00, 8.11), '611': (53.73, 6.35), '621a': (54.58, 8.15), '630': (54.53, 8.24),
        '672': (53.95, 8.55), '789': (53.67, 7.07), '797': (53.65, 6.80), '804': (53.32, 7.33), '857': (51.75, 3.82),
        '876': (51.82, 5.02), '880': (51.70, 4.42), '1010': (48.53, -2.73), '1131': (51.50, 1.08), '1195a': (53.33, 0.57),
        '1200': (53.71, -0.45), '1631': (51.52, -9.54), '1932': (43.71, -7.45)}


def region(n):
    for (a, b), box in REGION:
        if a <= n <= b:
            return box
    return None


def in_box(p, box):
    return box[0] <= p[0] <= box[1] and box[2] <= p[1] <= box[3]


def kern2(s):
    w = [x for x in norm(s).split() if x not in GATTUNG]
    return ' '.join(w) or norm(s).strip()


def aufloesen(n):
    """'Aveiro, Porto de –' -> 'Porto de Aveiro'; 'Cruz, Santa –, Flores' -> 'Santa Cruz, Flores'."""
    n = n.replace('§', '').strip()
    m = re.match(r'^([^,]+),\s*([^,]*?)\s*–\s*(,.*)?$', n)
    if m:
        vor = m.group(2)
        verb = '' if vor.endswith(('-', '’', "'")) else ' '
        return (vor + verb + m.group(1)).strip() + (m.group(3) or '')
    return n


def verzeichnis():
    t = subprocess.run(['pdftotext', '-layout', PDF, '-'], capture_output=True, text=True, check=True).stdout
    roh = []
    for z in t.splitlines():
        if 'Ortsverzeichnis' in z or not z.strip():
            continue
        bezug = set()
        z2 = re.sub(r'\s*\(S\.\s*\d+\s*[–-]\s*\d+\)', '§', z)
        z2 = re.sub(r'^\s*[A-ZÄÖÜ]\s{3,}', ' ', z2)               # Buchstaben-Zwischentitel vor der rechten Spalte
        z2 = re.sub(r'\S[^.]*?–\s*,\s*siehe Eigennamen?', ' ', z2)  # Verweise ("Den – , siehe Eigennamen")
        for m in EINTRAG.finditer(z2):
            name, nrs = m.group(1).strip(), m.group(2)
            if re.search(r'\d[a-zA-Z]?\s*[–-]\s*\d', nrs):                 # Gebiet ("Wesergebiet 734-752")
                continue
            for nr in re.split(r',\s*', nrs):
                roh.append(dict(name=aufloesen(name), roh=name.replace('§', ''), nr=nr.strip(), bezug=int('§' in name)))
    # Die deutschen Bezugsorte (101, 103, 111, 502-512) tragen Nummern, die in Teil II zugleich Spitzbergen- und
    # Norwegen-Orte bezeichnen (111 Norderney / Virgo-Hafen, 510 Husum / Eidfjord) -> eigener Schluessel, kein Nummernanker
    g = collections.OrderedDict()
    for e in roh:
        k = e['nr'].lower()
        de = e['bezug'] and int(re.match(r'\d+', k).group()) < 600
        x = g.setdefault(k + ('#de' if de else ''), dict(nr=e['nr'], nr_int=int(re.match(r'\d+', k).group()), namen=[], bezug=0,
                                                       schluessel=k + ('#de' if de else ''), anker=not de))
        if e['name'] not in x['namen']:
            x['namen'].append(e['name'])
        x['bezug'] |= e['bezug']
    return sorted(g.values(), key=lambda x: (x['nr_int'], x['nr'].lower()))


def varianten(namen):
    out = []
    for name in namen:
        for v in [name] + [p.strip() for p in re.split(r'[,/]|\s–\s', name)]:
            v = v.strip(' –')
            if v and v not in out and len(norm(v).strip()) >= 3 and [x for x in norm(v).split() if x not in GATTUNG]:
                out.append(v)
    return out


def bsh_json():
    pos = {}
    for f in glob.glob(os.path.join(JSON_DIR, 'DE_*.json')):
        d = json.load(open(f))
        nr = d['bshnr']
        nr = nr[:-1] if nr.endswith('P') else nr
        pos[nr.lower()] = (d['latitude'], d['longitude'], d['station_name'])
    return pos


def passt(a, b):
    s = difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0
    if a == b and len(a) >= 3:
        return 1.0
    if len(a) >= 5 and (a in b.split() or b in a.split()):
        return 0.95
    return s if s >= 0.88 else 0


def satznamen(r):
    return [r['name'].split(',')[0]] + re.findall(r'\(([^)]*)\)', r['name'])


def main(argv):
    I = verzeichnis()
    J = bsh_json()
    R = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    RE = [r for r in R if EUROPA[0] <= r['lat'] <= EUROPA[1] and EUROPA[2] <= r['lon'] <= EUROPA[3]]
    # Klammerinhalt gilt nur als Ortsname, wenn er bei hoechstens einem Satz steht; "(Elbe)", "(Jade)",
    # "(Bristol Channel)", "(Carlingford Lough)" sind Gewaesser-Zusaetze vieler Saetze (Elbe Tonne traf sonst Cuxhaven)
    kl = collections.Counter(kern2(x) for r in RE for x in set(re.findall(r'\(([^)]*)\)', r['name'])))
    kerne = [(r, [kern2(re.sub(r'\(.*?\)', '', r['name'].split(',')[0]))] +
              [kern2(x) for x in re.findall(r'\(([^)]*)\)', r['name']) if kl[kern2(x)] <= 1]) for r in RE]
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    letzte = [0.0]
    for e in I:
        e.update(pos=None, methode='unbekannt', treffer='')
        if e['nr'].lower() in J and (e['nr_int'] >= 600 or not e['anker']):
            j = J[e['nr'].lower()]
            e['pos'], e['methode'], e['treffer'] = (j[0], j[1]), 'bsh', j[2]

    def treffer(e, mitte=None, rad=None, nur_exakt=False):
        best = []
        for r, ks in kerne:
            if mitte is not None and km(mitte, (r['lat'], r['lon'])) > rad:
                continue
            for v in varianten(e['namen']):
                a = kern2(v)
                for b in ks:
                    s = 1.0 if (a == b and len(a) >= 4) else (0 if nur_exakt else passt(a, b))
                    if s:
                        best.append((s, r))
        return best

    # Saat: eindeutige exakte Namen europaweit
    saat = {}
    for e in I:
        if e['pos']:
            continue
        t = treffer(e, nur_exakt=True)
        if not t:
            continue
        pts = [(r['lat'], r['lon']) for _, r in t]
        med = min(pts, key=lambda q: sum(km(q, p) for p in pts))
        if max(km(med, p) for p in pts) <= 30:
            saat[e['schluessel']] = (med, t[0][1]['name'])
    # Saat gegen Nummernnachbarn pruefen (Median der Nachbarn innerhalb +-25 Nummern)
    nr_von = {e['schluessel']: e['nr_int'] for e in I}
    fest = [(e['nr_int'], e['pos']) for e in I if e['pos'] and e['anker']] + [(nr_von[k], v[0]) for k, v in saat.items()]
    for e in I:
        k = e['schluessel']
        if k not in saat or not e['anker']:
            continue
        nb = [p for n, p in fest if abs(n - e['nr_int']) <= 25 and p != saat[k][0]]
        if len(nb) >= 2:
            med = min(nb, key=lambda q: sum(km(q, p) for p in nb))
            if km(med, saat[k][0]) > 400:
                continue
        e['pos'], e['methode'], e['treffer'] = saat[k][0], 'saat', saat[k][1]
    print('Saat: %d BSH-JSON, %d Namen' % (sum(e['methode'] == 'bsh' for e in I), sum(e['methode'] == 'saat' for e in I)), flush=True)

    laender = {}

    def land(la, lo):
        k = (math.floor(la), math.floor(lo))
        if k not in laender:
            laender[k] = osm_land.Land([(la, lo)])
        return laender[k]

    def nominatim(q, box):
        key = q + '|' + ','.join('%.2f' % b for b in box)
        if key not in cache:
            if '--ohne-netz' in argv:
                return []
            time.sleep(max(0.0, 1.1 - (time.time() - letzte[0])))
            u = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
                dict(q=q, format='jsonv2', limit=5, viewbox='%.4f,%.4f,%.4f,%.4f' % box, bounded=1))
            try:
                cache[key] = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'weather-tides/1.0'}), timeout=40))
            except Exception as ex:                               # noqa: BLE001
                print('   Nominatim-Fehler %s: %s' % (q, ex), flush=True)
                return []
            letzte[0] = time.time()
            if len(cache) % 25 == 0:
                json.dump(cache, open(CACHE, 'w'))
        return cache[key]

    def lage(e):
        an = sorted(((x['nr_int'], x['pos']) for x in I if x['pos'] and x['anker'] and x is not e), key=lambda x: x[0])
        vor = [p for n, p in an if e['nr_int'] - 30 <= n <= e['nr_int']][-3:]
        nach = [p for n, p in an if e['nr_int'] <= n <= e['nr_int'] + 30][:3]
        pts = vor + nach
        if not pts:
            return None, None
        med = min(pts, key=lambda q: sum(km(q, p) for p in pts))
        pts = [p for p in pts if km(med, p) <= 600]
        mitte = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        return mitte, min(300.0, max(60.0, 1.5 * max(km(mitte, p) for p in pts)))

    for runde in range(8):
        geo = runde >= 2 and '--ohne-netz' not in argv
        neu_n = 0
        for e in I:
            if e['pos']:
                continue
            mitte, rad = lage(e)
            if mitte is None:
                continue
            t = treffer(e, mitte, rad)
            if t:
                s, r = max(t, key=lambda x: (x[0], -km(mitte, (x[1]['lat'], x[1]['lon']))))
                e['pos'], e['methode'], e['treffer'] = (r['lat'], r['lon']), 'name', r['name']
            elif geo:
                dla = rad / 111.0
                dlo = rad / (111.0 * max(0.2, math.cos(math.radians(mitte[0]))))
                box = (mitte[1] - dlo, mitte[0] + dla, mitte[1] + dlo, mitte[0] - dla)
                for v in varianten(e['namen']):
                    res = nominatim(v, box)
                    ok = [x for x in sorted(res, key=lambda x: km(mitte, (float(x['lat']), float(x['lon']))))
                          if km(mitte, (float(x['lat']), float(x['lon']))) <= min(rad, 150.0)
                          and land(float(x['lat']), float(x['lon'])).kueste_km(float(x['lat']), float(x['lon']), rmax=5) <= 3.0]
                    if ok:
                        e['pos'] = (float(ok[0]['lat']), float(ok[0]['lon']))
                        e['methode'], e['treffer'] = 'geo', ok[0]['display_name'][:120]
                        break
            if e['pos']:
                neu_n += 1
        print('Runde %d (%s): %d neu verortet, offen %d' % (runde, 'Nominatim' if geo else 'Namen', neu_n,
                                                          sum(1 for e in I if not e['pos'])), flush=True)
        if not neu_n and runde >= 2:
            break
    # Regionsstufe: fehlende Orte und Orte ausserhalb ihres Kastens im Kasten suchen (Namen 0.8, dann Nominatim)
    for e in I:
        box = region(e['nr_int']) if e['anker'] else None
        if not box or (e['pos'] and in_box(e['pos'], box)):
            continue
        e.update(pos=None, methode='unbekannt', treffer='')
        best = None
        for r, ks in kerne:
            if not in_box((r['lat'], r['lon']), box):
                continue
            for v in varianten(e['namen']):
                a = kern2(v)
                for b in ks:
                    sc = difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0
                    if (a in b.split() or b in a.split()) and min(len(a), len(b)) >= 4:
                        sc = max(sc, 0.9)
                    if sc >= 0.8 and (best is None or sc > best[0]):
                        best = (sc, r)
        if best:
            e['pos'], e['methode'], e['treffer'] = (best[1]['lat'], best[1]['lon']), 'region', best[1]['name']
            continue
        for v in varianten(e['namen']):
            res = nominatim(v, (box[2], box[1], box[3], box[0]))
            if res:
                x = res[0]
                e['pos'], e['methode'], e['treffer'] = (float(x['lat']), float(x['lon'])), 'geo', x['display_name'][:120]
                break
    for e in I:
        if not e['pos'] and e['anker'] and e['nr'].lower() in HAND:
            e['pos'], e['methode'], e['treffer'] = HAND[e['nr'].lower()], 'hand', 'ungefaehr (Handposition)'
    json.dump(cache, open(CACHE, 'w'))
    felder = ['nr', 'namen', 'bezugsort', 'methode', 'treffer', 'lat', 'lon', 'satz', 'satz_km', 'status']
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        for e in I:
            z = dict(nr=e['nr'], namen=' | '.join(e['namen']), bezugsort=e['bezug'], methode=e['methode'], treffer=e['treffer'],
                     lat='', lon='', satz='', satz_km='', status='unbekannt')
            if e['pos']:
                d, r = min(((km(e['pos'], (r['lat'], r['lon'])), r) for r in R), key=lambda x: x[0])
                z.update(lat='%.4f' % e['pos'][0], lon='%.4f' % e['pos'][1], satz=r['name'], satz_km='%.1f' % d,
                         status='gedeckt' if d <= 5 else ('nah' if d <= 15 else 'luecke'))
            e['status'] = z['status']
            w.writerow(z)
    c = collections.Counter(e['status'] for e in I)
    m = collections.Counter(e['methode'] for e in I)
    print('%d Orte | gedeckt %d, nah %d, Luecke %d, unbekannt %d | Methode %s' % (
        len(I), c['gedeckt'], c['nah'], c['luecke'], c['unbekannt'], dict(m)))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
