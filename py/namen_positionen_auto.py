#!/usr/bin/env python3
"""Namen und Positionen eines Landes automatisch pruefen und verbessern.

Was Oliver bisher von Hand korrigiert hat, in Regeln gefasst:

  1. Position: Steht ein Satz auf einer gerundeten Buchposition (ganze
     Bogenminuten), wird er auf den naechsten Anleger/Hafen aus OSM
     geschoben (ferry_terminal, pier, quay, breakwater, harbour, marina).
     Bis SICHER_KM automatisch, bis VORSCHLAG_KM als Vorschlag.
     Saetze mit genauer Position (amtliche Pegelkoordinaten) bleiben.
  2. Name auffindbar? Der Grundname (ohne Land, ohne Klammer) muss in OSM
     oder GeoNames im Umkreis NAME_KM vorkommen. Wenn nicht, wird ein
     GeoNames-Objekt gesucht, das den Namen als Alternativnamen fuehrt
     (alte Umschrift); dessen heutiger Name wird vorgeschlagen.
  3. Eindeutigkeit: Grundnamen, die im Land mehrfach vorkommen, bekommen
     einen Ortsteil-Vorschlag (Nominatim: Dorf/Insel/Kreis).

Ausgabe harmonics/help/auto_<land>_<datum>.csv. Mit --schreiben werden die
sicheren Positionsverschiebungen eingetragen (Notiz + Sicherung); Namen
werden nie ohne Freigabe geaendert.

    python3 py/namen_positionen_auto.py "South Korea" KR [--schreiben]
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, auf_raster, ROOT  # noqa: E402
from positionen_geonames import geonames, norm                # noqa: E402

SICHER_KM = 1.5
VORSCHLAG_KM = 4.0
NAME_KM = 4.0
UA = 'tidal-harmonics-check/1.0 (oliver.k73@gmail.com)'
OVERPASS = ['https://maps.mail.ru/osm/tools/overpass/api/interpreter',
            'https://overpass-api.de/api/interpreter',
            'https://overpass.private.coffee/api/interpreter']
HAFEN = ('ferry_terminal', 'pier', 'quay', 'breakwater', 'harbour', 'marina')


def _abfrage(bb):
    s, w, n, e = bb
    box = '%f,%f,%f,%f' % (s, w, n, e)
    q = ('[out:json][timeout:120];('
         'nwr["amenity"="ferry_terminal"](%s);nwr["man_made"~"^(pier|quay|breakwater)$"](%s);'
         'nwr["landuse"="harbour"](%s);nwr["leisure"="marina"](%s);'
         ');out center tags;') % ((box,) * 4)
    for versuch in range(3):
        for ep in OVERPASS:
            o = subprocess.run(['curl', '-s', '-m', '150', '-A', UA, '-H', 'Accept: */*', ep,
                                '--data-urlencode', 'data=' + q], capture_output=True, text=True).stdout
            if o.startswith('{'):
                return json.loads(o)['elements']
        time.sleep(10)
    return None


def osm_haefen(cc, bbox, saetze):
    """Anleger/Haefen um die Saetze -- in Kacheln abgefragt, zwischengespeichert."""
    pfad = os.path.join(ROOT, 'harmonics/help/geonames/osm_haefen_%s.json' % cc)
    out = json.load(open(pfad)) if os.path.exists(pfad) else {'kacheln': {}, 'haefen': []}
    kacheln = sorted({(int(r['lat'] * 2) / 2.0, int(r['lon'] * 2) / 2.0) for r in saetze})
    for la, lo in kacheln:
        key = '%.1f,%.1f' % (la, lo)
        if key in out['kacheln']:
            continue
        el = _abfrage((la - 0.05, lo - 0.05, la + 0.55, lo + 0.55))
        if el is None:
            print('  Kachel %s: keine Antwort' % key, flush=True)
            continue
        for x in el:
            c = x.get('center') or x
            t = x.get('tags', {})
            art = ('ferry_terminal' if t.get('amenity') == 'ferry_terminal' else
                   t.get('man_made') or ('harbour' if t.get('landuse') == 'harbour' else t.get('leisure', 'harbour')))
            out['haefen'].append(dict(lat=c['lat'], lon=c['lon'], art=art,
                                      name=t.get('name', ''), name_en=t.get('name:en', '')))
        out['kacheln'][key] = len(el)
        print('  Kachel %s: %d Objekte' % (key, len(el)), flush=True)
        json.dump(out, open(pfad, 'w'))
    return out['haefen']


def nominatim(lat, lon):
    url = 'https://nominatim.openstreetmap.org/reverse?' + urllib.parse.urlencode(
        dict(lat=lat, lon=lon, format='jsonv2', zoom=16, addressdetails=1))
    try:
        j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=25))
    except Exception:  # noqa: BLE001
        return {}
    time.sleep(1.1)
    return j.get('address', {})


def grundname(n):
    t = n.rsplit(',', 1)[0]
    return re.sub(r'\s*\(.*?\)', '', t).strip()


def main(argv):
    land, cc = argv[1], argv[2]
    schreiben = '--schreiben' in argv
    gn = geonames(cc)
    rs = [r for r in load_records() if r['name'].endswith(land) and not r['current']]
    bbox = (min(r['lat'] for r in rs) - 0.3, min(r['lon'] for r in rs) - 0.3,
            max(r['lat'] for r in rs) + 0.3, max(r['lon'] for r in rs) + 0.3)
    haefen = osm_haefen(cc, bbox, rs)
    print('%d Saetze, %d OSM-Anleger/Haefen' % (len(rs), len(haefen)), flush=True)
    zaehl = {}
    for r in rs:
        zaehl[norm(grundname(r['name']))] = zaehl.get(norm(grundname(r['name'])), 0) + 1
    zeilen = []
    for r in sorted(rs, key=lambda r: r['name']):
        z = dict(satz=r['name'], datei=r['file'], lat=r['lat'], lon=r['lon'],
                 raster='ja' if auf_raster(r['lat'], r['lon']) else '')
        # 1. Position
        if z['raster']:
            h = min(haefen, key=lambda h: km(r, h))
            d = km(r, h)
            z.update(hafen=h['name'] or h['name_en'] or h['art'], hafen_art=h['art'],
                     hafen_lat=round(h['lat'], 4), hafen_lon=round(h['lon'], 4), hafen_km=round(d, 2))
            z['position'] = ('SICHER' if d <= SICHER_KM else 'vorschlag' if d <= VORSCHLAG_KM else '')
        # 2. Name auffindbar?
        g = norm(grundname(r['name']))
        g0 = re.sub(r'(hang|gang|do|to|ri|ni|dong)$', '', g)
        nah = [x for x in gn if km(r, x) <= NAME_KM]
        treffer = [x for x in nah if g in x['namen'] or (len(g0) >= 4 and any(n.startswith(g0) for n in x['namen']))]
        osm = [h for h in haefen if km(r, h) <= NAME_KM and g0 and g0 in norm(h['name'] + h['name_en'])]
        if treffer or osm:
            z['name_ok'] = 'ja'
            haupt = treffer[0]['name'] if treffer else ''
            if haupt and norm(haupt) != g and "'" not in haupt and not re.search(r'[^\x00-\x7f]', haupt):
                z['name_vorschlag'] = haupt
        else:
            z['name_ok'] = 'nein'
        # 3. Eindeutigkeit
        if zaehl[g] > 1 or g0 and sum(1 for k in zaehl if k.startswith(g0) and k != g) > 0:
            a = nominatim(r['lat'], r['lon'])
            teil = a.get('village') or a.get('island') or a.get('hamlet') or a.get('suburb') or a.get('county') or ''
            z['mehrdeutig'] = 'ja'
            z['ortsteil'] = teil
        zeilen.append(z)
    aus = os.path.join(ROOT, 'harmonics/help/auto_%s_%s.csv' % (re.sub(r'\W+', '_', land.lower()),
                                                                date.today().strftime('%Y%m%d')))
    felder = ['satz', 'datei', 'lat', 'lon', 'raster', 'position', 'hafen', 'hafen_art', 'hafen_lat',
              'hafen_lon', 'hafen_km', 'name_ok', 'name_vorschlag', 'mehrdeutig', 'ortsteil']
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder, extrasaction='ignore')
        w.writeheader()
        w.writerows(zeilen)
    sicher = [z for z in zeilen if z.get('position') == 'SICHER']
    print('Positionen sicher %d, Vorschlag %d; Namen nicht auffindbar %d; mehrdeutig %d; Tabelle %s'
          % (len(sicher), sum(1 for z in zeilen if z.get('position') == 'vorschlag'),
             sum(1 for z in zeilen if z.get('name_ok') == 'nein'),
             sum(1 for z in zeilen if z.get('mehrdeutig')), os.path.relpath(aus, ROOT)))
    if schreiben and sicher:
        nach = {}
        for z in sicher:
            nach.setdefault(z['datei'], []).append(z)
        for f, lst in nach.items():
            p = os.path.join(ROOT, f)
            shutil.copy2(p, os.path.join(ROOT, 'harmonics/backup', os.path.basename(p) + '.vor_auto_%s'
                                         % date.today().strftime('%Y%m%d')))
            L = open(p, encoding='latin-1', newline='').read().split('\n')
            for z in lst:
                i = [k for k, l in enumerate(L) if l == z['satz']]
                if len(i) != 1:
                    continue
                i = i[0]
                for j in range(i - 60, i):
                    if L[j].startswith('# !latitude:'):
                        L[j] = '# !latitude: %.4f' % z['hafen_lat']
                    if L[j].startswith('# !longitude:'):
                        L[j] = '# !longitude: %.4f' % z['hafen_lon']
                art = z['hafen_art']
                L.insert(i, '# note: %s Position %.4f/%.4f (Buchraster) -> %.4f/%.4f naechster OSM-%s (%.2f km), automatisch.'
                         % (date.today().strftime('%Y%m%d'), z['lat'], z['lon'], z['hafen_lat'], z['hafen_lon'],
                            art, z['hafen_km']))
            open(p + '.tmp', 'w', encoding='latin-1', newline='').write('\n'.join(L))
            os.replace(p + '.tmp', p)
        print('%d Positionen geschrieben' % len(sicher))


if __name__ == '__main__':
    main(sys.argv)
