#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traegt Provinz, Bundesland oder Region als FELD in jeden Satz ein.

Bisher steht die Region nur im Namen -- und das auch nur bei den
Laendern, deren Hausregel das vorsieht: Kanada und Japan zu 100 Prozent,
Indonesien zu 30, Russland zu 19, Frankreich zu 5. Als Feld gepflegt ist
sie fast nirgends (Kanada 68 %, Australien 40 %, sonst nahe null).

Ein gefuelltes Feld loest zwei Dinge auf einmal: die Anzeige kann den
Namen selbst zusammensetzen -- kurz auf dem Telefon, vollstaendig auf
der Detailseite --, und es werden Regionsseiten moeglich, ohne dass ein
einziger Stationsname laenger wird. Der Name bleibt, was er ist: der
Schluessel, ueber den XTide aufloest.

Woher der Wert kommt, in dieser Reihenfolge:

  1. aus dem NAMEN, wo er dort schon steht. Das ist die verlaesslichste
     Quelle, weil von Hand geprueft -- und sie loest den britischen
     Sonderfall: wir schreiben England, Scotland, Wales, Northern
     Ireland, waehrend Natural Earth 232 Grafschaften kennt. Da 99 % der
     britischen Namen die Landesteile tragen, werden die Polygone dort
     gar nicht erst gefragt.
  2. aus einem schon vorhandenen Feld.
  3. aus den Polygonen: liegt der Pegel darin, gilt dessen Name; sonst
     das naechste Ufer innerhalb der Grenze. Ein Pegel steht im Wasser,
     die Grenzen liegen an Land -- ohne diesen Schritt bekaeme nur ein
     Fuenftel des Bestands einen Wert.

     Gesucht wird dabei NUR in den Polygonen des eigenen Landes. Ohne
     diese Fessel bekommt "Saint-Louis, Senegal" die mauretanische
     Provinz Trarza, die gegenueber der Flussmuendung beginnt, und
     "Xiis, Somalia" bekommt "Somaliland". Das naechste Ufer ist nicht
     immer das eigene.

Der Feldname folgt dem Land, nicht dem Werkzeug: province in Kanada,
state in Australien, region in Grossbritannien. Wo das Land schon einen
benutzt, wird der genommen; sonst entscheidet der Typ, den Natural Earth
mitfuehrt (Province -> province, State -> state, alles andere ->
region).

# admin1_quelle haelt fest, woher der Wert stammt ("Name", "Feld",
"Polygon", "Ufer 3.2 km"). Wer spaeter zweifelt, sieht sofort, ob ein
Mensch das geprueft hat oder ein Polygon geraten.

Die Grenzen sind Natural Earth 10m admin-1 (Public Domain) und liegen
nicht im Git -- 32 MB. Einmalig holen:

  curl -L -o ne.geojson https://raw.githubusercontent.com/nvkelso/\
natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson
  python3 py/region_felder_fuellen.py --aufbauen ne.geojson

Usage: python3 py/region_felder_fuellen.py [--schreiben] [--km 25]
"""
from __future__ import annotations

import collections
import json
import math
import os
import re
import shutil
import sys
import unicodedata
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import active_files, load_records, ROOT, MERIDIAN  # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
WELT = os.path.join(HELP, 'ne_admin1_welt.json')
GRENZE_KM = 25.0
FELDER = ('province', 'state', 'region')
TYP_FELD = {'Province': 'province', 'State': 'state'}
# Woerter, die im vorletzten Namensglied keine Provinz sind
KEINE = ('strait', 'river', 'bay', 'island', 'islands', 'entrance', 'gulf',
         'harbour', 'harbor', 'sound', 'channel', 'lake', 'inlet', 'passage',
         'reef', 'point', 'cape', 'peninsula', 'approaches', 'lagoon')


def aufbauen(quelle):
    """Schreibt die abgespeckte Weltdatei aus dem Natural-Earth-Download."""
    d = json.load(open(quelle, encoding='utf-8'))
    out = [{'admin': f['properties'].get('admin'), 'name': f['properties']['name'],
            'typ': f['properties'].get('type_en'),
            'iso': f['properties'].get('iso_3166_2'), 'geometry': f['geometry']}
           for f in d['features'] if f['properties'].get('name')]
    json.dump(out, open(WELT, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'{len(out)} Polygone -> {WELT}')


def polygone():
    """-> [(admin, name, typ, [((xmin,xmax,ymin,ymax), ringe)])]."""
    import numpy as np
    roh = json.load(open(WELT, encoding='utf-8'))
    out = []
    for e in roh:
        g = e['geometry']
        teile = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        fertig = []
        for t in teile:
            ringe = [np.array(r, dtype=float) for r in t if len(r) > 3]
            if not ringe:
                continue
            a = ringe[0]
            fertig.append(((float(a[:, 0].min()), float(a[:, 0].max()),
                            float(a[:, 1].min()), float(a[:, 1].max())), ringe))
        if fertig:
            out.append((e['admin'], e['name'], e['typ'], fertig))
    return out


def _im_ring(x, y, ring):
    drin = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            drin = not drin
        j = i
    return drin


# Die US-Saetze fuehren im Namen den Staat statt des Landes ("Monhegan
# Island, Maine") und im Feld country meist "USA". Beides muss auf die
# Vereinigten Staaten zeigen, sonst findet die Suche kein Polygon --
# 3654 Saetze hingen genau daran.
US_STAATEN = {
    'alabama', 'alaska', 'california', 'connecticut', 'delaware', 'florida',
    'georgia', 'hawaii', 'louisiana', 'maine', 'maryland', 'massachusetts',
    'mississippi', 'new hampshire', 'new jersey', 'new york', 'north carolina',
    'oregon', 'pennsylvania', 'puerto rico', 'rhode island', 'south carolina',
    'texas', 'virginia', 'washington', 'american samoa', 'guam',
    'northern mariana islands', 'us virgin islands', 'usa',
    'united states virgin islands'}

LAND_ALIAS = {'United States of America': 'united states',
              'Republic of Serbia': 'serbia',
              'Republic of the Congo': 'congo',
              'Democratic Republic of the Congo': 'democratic republic of the congo',
              'United Republic of Tanzania': 'tanzania',
              'The Bahamas': 'bahamas',
              'East Timor': 'timor-leste',
              'Czechia': 'czech republic',
              'Republic of Korea': 'south korea',
              'Kingdom of Norway': 'norway',
              'Federated States of Micronesia': 'micronesia',
              'Saint Helena': 'saint helena, ascension and tristan da cunha',
              'Ashmore and Cartier Islands': 'australia',
              'Indian Ocean Territories': 'australia'}
# Wie der Bestand ein Land nennt, wenn es von Natural Earth abweicht
BESTAND_ALIAS = {'usa': 'united states', 'espana': 'spain', 'españa': 'spain',
                 'ivory coast': "cote d'ivoire", 'uk': 'united kingdom',
                 'south korea': 'south korea', 'north korea': 'north korea',
                 'burma': 'myanmar', 'holland': 'netherlands',
                 'federated states of micronesia': 'micronesia',
                 'saint helena': 'saint helena, ascension and tristan da cunha',
                 'ascension island': 'saint helena, ascension and tristan da cunha',
                 'tristan da cunha': 'saint helena, ascension and tristan da cunha'}


def _passt(admin, land):
    # Ein leeres country-Feld darf nicht jedes Land passieren lassen. Mit
    # dem frueheren Teilzeichenketten-Vergleich tat es das, weil die
    # leere Zeichenkette in jedem Land steckt -- die jemenitischen Saetze
    # bekamen ihre Region so nur durch Zufall der Naehe.
    land = (land or '').strip() or None
    if not land or not admin:
        return True
    l = land.lower().strip()
    a = LAND_ALIAS.get(admin, admin).lower()
    if l in US_STAATEN:
        return a == 'united states'
    if l in ('espana', 'españa'):
        l = 'spain'
    # Kein Teilzeichenketten-Vergleich: "Guinea" steckt in
    # "Guinea-Bissau", und Bissau bekam daraufhin die guineische Region
    # Boke. Ebenso Congo/DR Congo, Niger/Nigeria, Sudan/South Sudan.
    return a == l


def welches(lon, lat, polys, land=None):
    for admin, name, typ, teile in polys:
        if not _passt(admin, land):
            continue
        for (xmin, xmax, ymin, ymax), ringe in teile:
            if not (xmin <= lon <= xmax and ymin <= lat <= ymax):
                continue
            if _im_ring(lon, lat, ringe[0]) and not any(
                    _im_ring(lon, lat, r) for r in ringe[1:]):
                return admin, name, typ, 0.0
    return None


def naechstes(lon, lat, polys, grenze, land=None):
    import numpy as np
    grad = grenze / 111.0
    cos = max(0.05, math.cos(math.radians(lat)))
    best, bd = None, float('inf')
    for admin, name, typ, teile in polys:
        if not _passt(admin, land):
            continue
        for (xmin, xmax, ymin, ymax), ringe in teile:
            if (lon < xmin - grad / cos or lon > xmax + grad / cos
                    or lat < ymin - grad or lat > ymax + grad):
                continue
            r = ringe[0]
            d = float(np.min((r[:, 1] - lat) ** 2
                             + ((r[:, 0] - lon) * cos) ** 2)) ** 0.5 * 111.0
            if d < bd:
                best, bd = (admin, name, typ), d
    return (best[0], best[1], best[2], bd) if best and bd <= grenze else None


def latin1(s):
    """-> Fassung, die sich in ISO-8859-1 schreiben laesst.

    Die Bestandsdateien sind ISO-8859-1, Natural Earth fuehrt aber auch
    Namen mit Zeichen darueber hinaus ("Kaimanawa Ranges" ist harmlos,
    "Manawatū" nicht). Ohne diese Umschrift bricht das Schreiben mitten
    im Lauf ab -- und weil open(...,'w') die Datei zuerst leert, stand
    harmonics_att_np203.txt danach auf null Bytes.
    """
    try:
        s.encode('iso-8859-1')
        return s
    except UnicodeEncodeError:
        zerlegt = unicodedata.normalize('NFD', s)
        ohne = ''.join(c for c in zerlegt
                       if unicodedata.category(c) != 'Mn')
        gerade = unicodedata.normalize('NFC', ohne)
        try:
            gerade.encode('iso-8859-1')
            return gerade
        except UnicodeEncodeError:
            return gerade.encode('ascii', 'ignore').decode('ascii')


def aus_namen(name):
    """-> Region aus dem Namen, wenn das vorletzte Glied eine ist."""
    t = [x.strip() for x in name.split(',')]
    if len(t) < 3:
        return None
    kand = t[-2]
    if not (1 < len(kand) < 32):
        return None
    if any(w in kand.lower() for w in KEINE):
        return None
    if re.search(r'\(\d|\d{3}', kand):
        return None
    return kand


def kopf(path):
    """-> {Zeile: (Feldname, Wert, country)} der vorhandenen Regionsfelder."""
    lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
    out = {}
    for k, l in enumerate(lines):
        if (not l or l.startswith('#') or k + 1 >= len(lines)
                or not MERIDIAN.match(lines[k + 1])):
            continue
        j, feld, wert, land = k - 1, None, None, None
        while j >= 0 and lines[j].startswith('#'):
            m = re.match(r'#\s*([a-z_]+):\s*(.+?)\s*$', lines[j])
            if m:
                if m.group(1) in FELDER and feld is None:
                    feld, wert = m.group(1), m.group(2)
                elif m.group(1) == 'country':
                    land = m.group(2)
            j -= 1
        out[k + 1] = (feld, wert, land)
    return out


def main(argv):
    if '--aufbauen' in argv:
        return aufbauen(argv[argv.index('--aufbauen') + 1])
    schreiben = '--schreiben' in argv
    grenze = float(argv[argv.index('--km') + 1]) if '--km' in argv else GRENZE_KM
    if not os.path.exists(WELT):
        sys.exit(f'{WELT} fehlt -- siehe --aufbauen im Kopf dieser Datei')

    recs = load_records()
    info = {p: kopf(p) for p in active_files()}
    # Welches Feld benutzt ein Land schon?
    landfeld = collections.defaultdict(collections.Counter)
    for r in recs:
        feld, _w, land = info[r['file']].get(r['line'], (None, None, None))
        if feld and land:
            landfeld[land][feld] += 1
    hausfeld = {l: c.most_common(1)[0][0] for l, c in landfeld.items()}

    print('Polygone laden...', file=sys.stderr)
    polys = polygone()
    print(f'{len(polys)} Polygone', file=sys.stderr)

    quelle = collections.Counter()
    proDatei = collections.defaultdict(list)
    for n, r in enumerate(recs, 1):
        if n % 2000 == 0:
            print(f'  {n}/{len(recs)}', file=sys.stderr)
        feld, wert, land = info[r['file']].get(r['line'], (None, None, None))
        land = (land or '').strip() or None
        if wert:
            quelle['Feld'] += 1
            continue
        wert = aus_namen(r['name'])
        herkunft, typ = 'Name', None
        if not wert and r['lat'] is not None:
            heimat = land or r['name'].rsplit(', ', 1)[-1]
            t = welches(r['lon'], r['lat'], polys, heimat)
            if t:
                _a, wert, typ, _d = t
                herkunft = 'Polygon'
            else:
                t = naechstes(r['lon'], r['lat'], polys, grenze, heimat)
                if t:
                    _a, wert, typ, d = t
                    herkunft = f'Ufer {d:.1f} km'
        if not wert:
            quelle['ohne'] += 1
            continue
        quelle[herkunft.split()[0]] += 1
        name = hausfeld.get(land) or TYP_FELD.get(typ, 'region')
        proDatei[r['file']].append((r['line'], name, wert, herkunft))

    print('\nHerkunft der Werte:')
    for k in ('Feld', 'Name', 'Polygon', 'Ufer', 'ohne'):
        if quelle[k]:
            print(f'   {k:10} {quelle[k]:6}  {quelle[k]/len(recs)*100:5.1f} %')

    if not schreiben:
        print(f'\n{sum(len(v) for v in proDatei.values())} Felder waeren zu setzen')
        return 0

    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    gesamt = 0
    for datei, eintraege in sorted(proDatei.items()):
        voll = os.path.join(ROOT, datei)
        lines = open(voll, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and MERIDIAN.match(lines[k + 1]))
        for zeile, name, wert, herkunft in sorted(eintraege, reverse=True):
            i = zeile - 1
            lines[i:i] = [f'# {name}: {latin1(wert)}',
                          f'# admin1_quelle: {herkunft}']
            gesamt += 1
        shutil.copy2(voll, os.path.join(
            BACKUP, os.path.basename(datei) + f'.vor_region_{stamp}'))
        # Erst daneben schreiben, dann umbenennen: open(...,'w') leert die
        # Datei sofort, und ein Fehler beim Schreiben laesst sie leer
        # zurueck. Genau so ging harmonics_att_np203.txt einmal auf null.
        neben = voll + '.neu'
        with open(neben, 'w', encoding='iso-8859-1') as fh:
            fh.write('\n'.join(lines))
        os.replace(neben, voll)
        nachher = sum(1 for k, l in enumerate(lines)
                      if l and not l.startswith('#') and k + 1 < len(lines)
                      and MERIDIAN.match(lines[k + 1]))
        print(f'   {os.path.basename(datei):46} {len(eintraege):5} Felder, '
              f'{vorher} -> {nachher} Saetze')
        if nachher != vorher:
            print('   ACHTUNG: Satzzahl veraendert!')
            return 1
    print(f'\n{gesamt} Felder gesetzt')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
