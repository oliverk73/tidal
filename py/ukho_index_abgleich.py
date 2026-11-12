#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UKHO-Hafenverzeichnis (NP202/NP205/NP206, Lieferung 12.11.2026) gegen den Bestand abgleichen (Oliver: "intelligent matchen").

Quelle: tide_tables/att/CS-361179-W8R3 - ADMIRALTY Tide Tables Indexes- Standard and Secondary Ports.docx (nur Name +
ATT-Nummer, keine Koordinaten). Die ATT-Nummern laufen die Kueste entlang -> Lage aus den Nachbarnummern, die wir mit
Position kennen (aktive + archivierte ATT-Saetze). Dann:
  1. eigene Nummer bekannt                      -> 'att'      (Position = unser Satz)
  2. Name unscharf im Bestand im Umkreis         -> 'name'     (Umlaute, o/ae, Gattungswoerter, Klammern)
  3. Nominatim im Umkreis (viewbox, 1/s, Cache)  -> 'geo'      (Position aus OSM)
  sonst                                          -> 'unbekannt'
Abdeckung: naechster Wasserstands-Satz zur Position; <= 5 km gedeckt, 5-15 km nah, > 15 km Luecke.
Schreibt harmonics/help/ukho_index_abgleich.csv; Cache water_levels/UKHO_index_nominatim.json.
Usage: venv/bin/python py/ukho_index_abgleich.py [--ohne-netz]
"""
import collections
import csv
import difflib
import glob
import html
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCX = os.path.join(ROOT, 'tide_tables/att/CS-361179-W8R3 - ADMIRALTY Tide Tables Indexes- Standard and Secondary Ports.docx')
AUS = os.path.join(ROOT, 'harmonics/help/ukho_index_abgleich.csv')
CACHE = os.path.join(ROOT, 'water_levels/UKHO_index_nominatim.json')
GATTUNG = {'harbour', 'harbor', 'hang', 'gang', 'port', 'bay', 'wan', 'ko', 'ura', 'bukhta', 'zaliv', 'teluk', 'pulau', 'tanjung',
           'kuala', 'bahia', 'puerto', 'baie', 'havn', 'hamn', 'haven', 'hafen', 'cove', 'inlet', 'island', 'islands', 'is', 'i',
           'point', 'pt', 'the', 'de', 'la', 'le', 'du', 'des', 'of', 'entrance', 'approaches', 'off', 'dao', 'jima', 'shima',
           'mys', 'ostrov', 'river', 'schleuse', 'sluis', 'lock', 'sluice', 'lighthouse', 'fyr', 'light', 'north', 'south', 'east', 'west', 'side', 'rivier', 'kou', 'jiao', 'wharf', 'pier', 'jetty', 'landing', 'sound', 'channel'}


def norm(s):
    s = s.lower().replace('ø', 'o').replace('æ', 'ae').replace('ß', 'ss').replace('’', '').replace("'", '')
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = s.replace('--', ' ').replace('-', ' ')
    return re.sub(r'[^a-z0-9 ]', ' ', s)


def kern(s):
    w = [x for x in norm(s).split() if x not in GATTUNG]
    return ' '.join(w) or norm(s).strip()


def varianten(name):
    """Hauptname, Klammerinhalt, Teile um Komma/Schraegstrich."""
    out = []
    haupt = re.sub(r'\(.*?\)', '', name).strip(' ,')
    out.append(haupt)
    out += [p.strip() for p in re.findall(r'\(([^)]*)\)', name)]
    for teil in re.split(r'[,/]', haupt):
        if teil.strip() and teil.strip() not in out:
            out.append(teil.strip())
    # nur Teile mit eigenem Namenskern ("Schleuse" allein traf Buesum statt Husum)
    return [v for v in out if len(norm(v).strip()) >= 3 and [x for x in norm(v).split() if x not in GATTUNG]]


def index_lesen():
    z = zipfile.ZipFile(DOCX)
    x = z.read('word/document.xml').decode()
    vol, out = None, []
    for p in re.findall(r'<w:p[ >].*?</w:p>', x, flags=re.S):
        t = html.unescape(''.join(re.findall(r'<w:t(?: [^>]*)?>([^<]*)</w:t>', p))).strip()
        m = re.match(r'^NP ?(\d{3})$', t)
        if m:
            vol = m.group(1)
            continue
        m = re.match(r'^(.*?)\s*(?:\. ?)+\s*(\d+)([a-z]?)\s*$', t)
        if m and vol:
            n = m.group(1).strip(' .')
            out.append(dict(np=vol, name=n, nr=m.group(2) + m.group(3), nr_int=int(m.group(2)),
                            standard=int(n.upper() == n and any(c.isalpha() for c in n))))
    return out


def anker():
    """ATT-Nummer -> (lat, lon) aus allen ATT-Dateien (auch Archiv/Backups); Mehrfache: Median."""
    pos = collections.defaultdict(list)
    for f in glob.glob(os.path.join(ROOT, 'harmonics/att/*.txt')) + glob.glob(os.path.join(ROOT, 'harmonics/backup/geloescht/harmonics_att*.txt')):
        nr = la = lo = None
        for z in open(f, encoding='iso-8859-1'):
            if z.startswith('# att_number:'):
                nr = z.split(':', 1)[1].strip().lower()
            elif z.startswith('# !latitude:'):
                la = float(z.split(':')[1])
            elif z.startswith('# !longitude:'):
                lo = float(z.split(':')[1])
            elif not z.startswith('#') and nr and la is not None and lo is not None:
                pos[nr].append((la, lo))
                nr = la = lo = None
    return {k: (sorted(v)[len(v) // 2]) for k, v in pos.items()}


def km(a, b):
    return 6371 * math.hypot(math.radians(a[0] - b[0]), math.radians(((a[1] - b[1] + 180) % 360) - 180) * math.cos(math.radians(a[0])))


def main(argv):
    I = index_lesen()
    A = anker()
    nummern = sorted(((int(re.match(r'\d+', k).group()), k, v) for k, v in A.items() if re.match(r'\d+', k)), key=lambda x: x[0])
    R = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    letzte = [0.0]

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
            except Exception as e:                                # noqa: BLE001
                print('   Nominatim-Fehler %s: %s' % (q, e), flush=True)
                return []
            letzte[0] = time.time()
            if len(cache) % 25 == 0:
                json.dump(cache, open(CACHE, 'w'))
        return cache[key]

    def lage(e, anker_n):
        """Mitte + Radius aus Nachbarnummern (bekannte ATT-Saetze und schon gefundene Index-Haefen)."""
        vor = [x for x in anker_n if e['nr_int'] - 40 <= x[0] <= e['nr_int'] and x[1] != e['nr'].lower()][-3:]
        nach = [x for x in anker_n if e['nr_int'] <= x[0] <= e['nr_int'] + 40 and x[1] != e['nr'].lower()][:3]
        pts = [x[2] for x in vor + nach]
        if not pts:
            return None, None
        med = min(pts, key=lambda q: sum(km(q, p) for p in pts))  # Medoid
        pts = [p for p in pts if km(med, p) <= 800]               # Nummernkollisionen anderer Baende (NP208)
        mitte = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        return mitte, min(400.0, max(80.0, 1.5 * max(km(mitte, p) for p in pts)))

    def name_suche(e, mitte, rad):
        best = None
        for r in R:
            if km(mitte, (r['lat'], r['lon'])) > rad:
                continue
            rn = [r['name'].split(',')[0]] + re.findall(r'\(([^)]*)\)', r['name'])
            for v in varianten(e['name']):
                for x in rn:
                    a, b = kern(v), kern(re.sub(r'\(.*?\)', '', x))
                    s = difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0
                    if s >= 0.88 or (len(a) >= 5 and (a == b or a in b.split() or b in a.split())):
                        if best is None or s > best[0]:
                            best = (s, r)
        return best

    for e in I:
        e.update(lat='', lon='', methode='unbekannt', treffer='', satz='', satz_km='', status='unbekannt', pos=None)
        if e['nr'].lower() in A:
            e['pos'], e['methode'] = A[e['nr'].lower()], 'att'
    # Runden: gefundene Haefen werden Anker ihrer Nummernnachbarn; Nominatim erst, wenn Namen nichts mehr bringen
    for runde in range(8):
        geo = runde >= 2 and '--ohne-netz' not in argv
        neu_n = 0
        anker_n = sorted([(x[0], x[1], x[2]) for x in nummern] +
                         [(e['nr_int'], e['nr'].lower(), e['pos']) for e in I if e['pos'] and e['methode'] != 'att'], key=lambda x: x[0])
        for n, e in enumerate(I):
            if e['pos']:
                continue
            mitte, rad = lage(e, anker_n)
            if mitte is None:
                continue
            best = name_suche(e, mitte, rad)
            if best:
                e['pos'], e['methode'], e['treffer'] = (best[1]['lat'], best[1]['lon']), 'name', best[1]['name']
            elif geo:
                dla = rad / 111.0
                dlo = rad / (111.0 * max(0.2, math.cos(math.radians(mitte[0]))))
                box = (mitte[1] - dlo, mitte[0] + dla, mitte[1] + dlo, mitte[0] - dla)
                for v in varianten(e['name']):
                    res = nominatim(v, box)
                    if res:
                        res = sorted(res, key=lambda x: km(mitte, (float(x['lat']), float(x['lon']))))
                        e['pos'] = (float(res[0]['lat']), float(res[0]['lon']))
                        e['methode'], e['treffer'] = 'geo', res[0]['display_name'][:120]
                        break
            if e['pos']:
                neu_n += 1
                anker_n.append((e['nr_int'], e['nr'].lower(), e['pos']))
                anker_n.sort(key=lambda x: x[0])
        print('Runde %d (%s): %d neu verortet, offen %d' % (runde, 'Nominatim' if geo else 'Namen', neu_n,
                                                          sum(1 for e in I if not e['pos'])), flush=True)
        if not neu_n and runde >= 2:
            break
    zeilen = []
    for e in I:
        if e['pos']:
            pos = e['pos']
            d, r = min(((km(pos, (r['lat'], r['lon'])), r) for r in R), key=lambda x: x[0])
            e.update(lat='%.4f' % pos[0], lon='%.4f' % pos[1], satz=r['name'], satz_km='%.1f' % d,
                     status='gedeckt' if d <= 5 else ('nah' if d <= 15 else 'luecke'))
        zeilen.append(e)
    json.dump(cache, open(CACHE, 'w'))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['np', 'nr', 'name', 'standard', 'methode', 'treffer', 'lat', 'lon', 'satz', 'satz_km', 'status'])
        w.writeheader()
        for e in zeilen:
            w.writerow({k: e.get(k, '') for k in w.fieldnames})
    for v in ('202', '205', '206'):
        E = [e for e in zeilen if e['np'] == v]
        c = collections.Counter(e['status'] for e in E)
        m = collections.Counter(e['methode'] for e in E)
        print('NP%s: %d Haefen | gedeckt %d, nah %d, Luecke %d, unbekannt %d | Methode %s' % (
            v, len(E), c['gedeckt'], c['nah'], c['luecke'], c['unbekannt'], dict(m)))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
