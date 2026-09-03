#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traegt die fehlende Provinz in Stationsnamen nach.

In einem Teil der Laender steht die Provinz im Namen: wir schreiben
"Yakushima, Kagoshima, Japan", nicht "Yakushima, Japan". Welche
Laender das sind, entscheidet der Bestand selbst -- gezaehlt wird,
bei wie vielen Saetzen eines Landes das vorletzte Namensglied eine
Provinz ist. Wo das auf zwei Drittel zutrifft, ist es die Hausregel,
und die uebrigen Saetze fehlen.

Die Grenzen kommen aus Natural Earth (10m admin-1, Public Domain),
die BESCHRIFTUNG dagegen aus unserem eigenen Bestand: zu jedem
Polygon wird gezaehlt, welche Provinznamen die Saetze darin schon
tragen, und der haeufigste gewinnt. Damit stimmt die Schreibweise
automatisch mit dem ueberein, was schon dasteht -- "Québec" mit
Akzent, "Odisha" statt "Orissa" -- und zwei Sonderfaelle loesen sich
von selbst:

  Grossbritannien. Natural Earth kennt 232 Grafschaften, wir
  schreiben England, Scotland, Wales, Northern Ireland. Jede
  Grafschaft erbt aus den Saetzen in ihr die richtige der vier.

  Neufundland und Labrador. Das Polygon heisst "Newfoundland and
  Labrador", wir fuehren beide getrennt -- Insel und Festland sind
  aber verschiedene Polygonteile, und beschriftet wird nach den
  Saetzen, nicht nach dem Polygonnamen.

Ein Pegel liegt selten im Land. Deshalb drei Stufen: das Polygon,
das den Punkt enthaelt; sonst das naechste Polygon innerhalb von
25 km; sonst der naechste beschriftete Satz desselben Landes
innerhalb von 50 km, wenn die drei naechsten sich einig sind. Was
danach uebrig bleibt, wird nicht geraten, sondern aufgelistet.

Die Polygondatei wird einmal erzeugt:

  curl -L -o ne.geojson https://raw.githubusercontent.com/nvkelso/\
natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson
  python3 py/provinz_ergaenzen.py --polygone ne.geojson

Usage: python3 py/provinz_ergaenzen.py [--csv] [--schreiben]
                                       [--polygone <geojson>]
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
SLIM = os.path.join(HELP, 'ne_admin1_slim.json')

MIND_ANTEIL = 2 / 3      # ab hier gilt die Provinz als Hausregel des Landes
MIND_SAETZE = 20         # und so viele Saetze muessen sie schon tragen
NAH_POLYGON = 25.0       # so weit darf ein Pegel vor der Kueste liegen
NAH_SATZ = 50.0          # so weit darf der beschriftete Nachbar entfernt sein

# Was im vorletzten Namensglied stehen kann, ohne eine Provinz zu sein.
KEINE_PROVINZ = ('strait', 'river', 'bay', 'island', 'islands', 'entrance', 'gulf',
                 'coast', 'arch', 'channel', 'sound', 'shoal', 'reef', 'atoll',
                 'harbor', 'harbour', 'peninsula', 'cape', 'lagoon', 'inlet',
                 'pulau', 'teluk', 'firth', 'loch', 'sund', '(', ')', '<', '>', '[')


def ist_provinz(s):
    return 1 < len(s) < 32 and not any(w in s.lower() for w in KEINE_PROVINZ)


def schluessel(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', s)


def wortschatz(recs, ziel, polys):
    """Gueltige Provinznamen je Land.

    Die Wortliste kommt aus zwei Quellen, und die zweite ist noetig,
    weil die erste sie nicht erkennen wuerde: "Prince Edward Island"
    ist eine Provinz und faellt trotzdem durch jede Heuristik, die
    "Island" fuer einen geografischen Zusatz haelt. Natural Earth
    kennt sie namentlich, und damit zaehlen die vorhandenen
    PEI-Saetze als beschriftet -- ohne diesen Schritt galten sie als
    Luecke und haetten eine zweite Provinz danebengesetzt bekommen.
    """
    w = collections.defaultdict(set)
    for admin, name, _teile in polys:
        if admin in ziel and name:
            w[admin].add(schluessel(name))
    zaehl = collections.defaultdict(collections.Counter)
    for r in recs:
        segs = zerlegen(r['name'])
        if len(segs) >= 3 and segs[-1] in ziel:
            zaehl[segs[-1]][segs[-2]] += 1
    for land, c in zaehl.items():
        for k, n in c.items():
            if n >= 3 and ist_provinz(k):
                w[land].add(schluessel(k))
    return w


def zerlegen(name):
    return [x.strip() for x in name.split(',')]


def provinz(name, wort=None):
    """-> Provinz aus dem Namen, sonst None."""
    segs = zerlegen(name)
    if len(segs) < 3:
        return None
    if wort is not None:
        return segs[-2] if schluessel(segs[-2]) in wort.get(segs[-1], ()) else None
    return segs[-2] if ist_provinz(segs[-2]) else None


def laender(recs):
    """-> {Land: (mit, ohne)} fuer Laender, die die Provinz im Namen fuehren."""
    mit, ohne = collections.Counter(), collections.Counter()
    for r in recs:
        land = zerlegen(r['name'])[-1]
        (mit if provinz(r['name']) else ohne)[land] += 1
    out = {}
    for land in set(mit) | set(ohne):
        n = mit[land] + ohne[land]
        if mit[land] >= MIND_SAETZE and mit[land] / n >= MIND_ANTEIL:
            out[land] = (mit[land], ohne[land])
    return out


def polygone(pfad=SLIM):
    """-> [(admin, name, [(bbox, [Ringe])])] aus der geschrumpften Datei."""
    import numpy as np
    out = []
    for f in json.load(open(pfad)):
        teile, g = [], f['geometry']
        stuecke = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        for stueck in stuecke:
            ringe = [np.array(r, dtype=float) for r in stueck if len(r) > 3]
            if not ringe:
                continue
            a = ringe[0]
            teile.append(((a[:, 0].min(), a[:, 0].max(), a[:, 1].min(), a[:, 1].max()), ringe))
        if teile:
            out.append((f['admin'], f.get('name'), teile))
    return out


def _im_ring(x, y, ring):
    """Strahlenverfahren: liegt (x, y) im geschlossenen Ring?"""
    import numpy as np
    x1, y1 = ring[:-1, 0], ring[:-1, 1]
    x2, y2 = ring[1:, 0], ring[1:, 1]
    kreuzt = ((y1 > y) != (y2 > y))
    with np.errstate(divide='ignore', invalid='ignore'):
        xs = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
    return int(np.count_nonzero(kreuzt & (x < xs))) % 2 == 1


def welches(punkt, polys):
    """-> (Polygon, Teilflaeche), die den Punkt enthaelt, sonst None.

    Gezaehlt wird die Teilflaeche, nicht das ganze Polygon: "Newfoundland
    and Labrador" ist EIN Eintrag in Natural Earth, wir fuehren die Insel
    und das Festland aber getrennt. Ueber die Teilflaechen bekommt jede
    ihre eigene Beschriftung aus den Saetzen, die auf ihr liegen.
    """
    lon, lat = punkt
    for i, (_admin, _name, teile) in enumerate(polys):
        for j, ((xmin, xmax, ymin, ymax), ringe) in enumerate(teile):
            if not (xmin - 0.01 <= lon <= xmax + 0.01 and ymin - 0.01 <= lat <= ymax + 0.01):
                continue
            if not _im_ring(lon, lat, ringe[0]):
                continue
            if any(_im_ring(lon, lat, loch) for loch in ringe[1:]):
                continue                      # im Loch, also draussen
            return (i, j)
    return None


def naechstes(punkt, polys, grenze_km, namen, ganz):
    """-> naechste BESCHRIFTETE Teilflaeche innerhalb der Grenze.

    Nur beschriftete zaehlen: ein Pegel vor der Kueste soll die Provinz
    des Ufers erben, und eine Teilflaeche ohne eigene Saetze weiss
    nichts.
    """
    import numpy as np
    lon, lat = punkt
    grad = grenze_km / 111.0
    cos = max(0.05, math.cos(math.radians(lat)))
    best = (None, float('inf'))
    for i, (_admin, _name, teile) in enumerate(polys):
        for j, ((xmin, xmax, ymin, ymax), ringe) in enumerate(teile):
            if (i, j) not in namen and i not in ganz:
                continue
            if (lon < xmin - grad / cos or lon > xmax + grad / cos
                    or lat < ymin - grad or lat > ymax + grad):
                continue
            ring = ringe[0]
            d = float(np.min((ring[:, 1] - lat) ** 2
                             + ((ring[:, 0] - lon) * cos) ** 2)) ** 0.5 * 111.0
            if d < best[1]:
                best = ((i, j), d)
    return best[0] if best[1] <= grenze_km else None


def schon_drin(name, prov):
    """Steht die Provinz schon im Namen -- auch mit Zusatz dahinter?

    "Lunenburg, Nova Scotia (2), Canada" traegt sie, nur mit einer
    Unterscheidungsziffer; "Shanghai, China" ist selbst die Provinz.
    Beide bekommen sie nicht ein zweites Mal.
    """
    ziel = schluessel(prov)
    for seg in zerlegen(name)[:-1]:
        if schluessel(re.sub(r'\s*\(.*', '', seg)) == ziel:
            return True
    return False


def neuer_name(name, prov):
    segs = zerlegen(name)
    return ', '.join(segs[:-1] + [prov, segs[-1]])


def main(argv):
    if '--polygone' in argv:
        return schrumpfen(argv[argv.index('--polygone') + 1])
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    ziel = laender(recs)
    print('Laender mit Provinz im Namen:')
    for land, (m, o) in sorted(ziel.items(), key=lambda x: -x[1][1]):
        print(f'  {land[:28]:28} {m:5} mit, {o:5} ohne  ({m / (m + o) * 100:.0f} %)')
    polys = polygone()
    wort = wortschatz(recs, ziel, polys)
    print(f'\n{len(polys)} Polygone geladen, Wortschatz '
          f'{sum(len(v) for v in wort.values())} Provinznamen', file=sys.stderr)

    # Schritt 1: Polygone aus dem Bestand beschriften.
    beschriftung = collections.defaultdict(collections.Counter)
    lage = {}
    for r in recs:
        if zerlegen(r['name'])[-1] not in ziel:
            continue
        i = welches((r['lon'], r['lat']), polys)
        lage[id(r)] = i
        p = provinz(r['name'], wort)
        if p and i is not None:
            beschriftung[i][p] += 1
    namen = {i: c.most_common(1)[0][0] for i, c in beschriftung.items()}
    # Teilflaechen ohne eigene Saetze duerfen von ihrem Polygon erben --
    # aber nur, wenn dessen Teile sich einig sind. Genau daran scheitert
    # "Newfoundland and Labrador": Insel und Festland tragen
    # verschiedene Namen, also erbt dort nichts.
    ganz = collections.defaultdict(set)
    for (i, _j), name in namen.items():
        ganz[i].add(name)
    ganz = {i: s.pop() for i, s in ganz.items() if len(s) == 1}
    print(f'{len(namen)} Polygone aus dem Bestand beschriftet', file=sys.stderr)

    # Schritt 2: fehlende Provinzen zuordnen.
    beschriftet = [r for r in recs if provinz(r['name'], wort)
                   and zerlegen(r['name'])[-1] in ziel]
    treffer, offen = [], []
    for r in recs:
        land = zerlegen(r['name'])[-1]
        if land not in ziel or provinz(r['name'], wort):
            continue
        i, quelle = lage.get(id(r)), 'Polygon'
        if i is None or (i not in namen and i[0] not in ganz):
            i = naechstes((r['lon'], r['lat']), polys, NAH_POLYGON, namen, ganz)
            quelle = f'Polygon unter {NAH_POLYGON:.0f} km'
        if i is not None and (i in namen or i[0] in ganz):
            prov = namen.get(i) or ganz[i[0]]
            if not schon_drin(r['name'], prov):
                treffer.append((r, prov, quelle, polys[i[0]][1] or ''))
            continue
        nah = sorted(((km(r, x), x) for x in beschriftet
                      if zerlegen(x['name'])[-1] == land), key=lambda t: t[0])[:3]
        if nah and nah[0][0] <= NAH_SATZ:
            kand = {provinz(x['name'], wort) for _d, x in nah}
            if len(kand) == 1:
                prov = kand.pop()
                if not schon_drin(r['name'], prov):
                    treffer.append((r, prov, f'Nachbarn ab {nah[0][0]:.0f} km', ''))
                continue
        offen.append(r)

    print(f'\n{len(treffer)} Saetze bekommen eine Provinz, {len(offen)} bleiben offen')
    for land, n in collections.Counter(zerlegen(r['name'])[-1]
                                       for r, _p, _q, _n in treffer).most_common():
        print(f'  {land[:28]:28} {n:5}')
    if offen:
        print('\noffen:')
        for r in offen[:40]:
            print(f'  {r["name"][:52]:52} {r["lat"]:8.3f} {r["lon"]:9.3f}')
        if len(offen) > 40:
            print(f'  ... und {len(offen) - 40} weitere')

    if '--csv' in argv:
        p = os.path.join(HELP, 'provinz_ergaenzen.csv')
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['datei', 'alt', 'neu', 'provinz', 'quelle', 'polygon', 'lat', 'lon'])
            for r, prov, quelle, poly in treffer:
                w.writerow([os.path.basename(r['file']), r['name'], neuer_name(r['name'], prov),
                            prov, quelle, poly, f'{r["lat"]:.4f}', f'{r["lon"]:.4f}'])
            for r in offen:
                w.writerow([os.path.basename(r['file']), r['name'], '', '', 'offen', '',
                            f'{r["lat"]:.4f}', f'{r["lon"]:.4f}'])
        print(f'\n-> {p}')

    if '--schreiben' in argv:
        schreiben(treffer)
    return 0


def schreiben(treffer):
    import datetime as dt
    heute = dt.date.today().strftime('%Y%m%d')
    nach_datei = collections.defaultdict(list)
    for r, prov, quelle, _poly in treffer:
        nach_datei[r['file']].append((r, prov, quelle))
    os.makedirs(BACKUP, exist_ok=True)
    for datei, gs in nach_datei.items():
        pfad = os.path.join(ROOT, datei)
        shutil.copy2(pfad, os.path.join(
            BACKUP, f'{os.path.basename(datei)[:-4]}_{heute}_provinz.txt'))
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        for r, prov, quelle in sorted(gs, key=lambda x: -x[0]['line']):
            k = r['line'] - 1
            if lines[k].strip() != r['name']:
                print(f'  uebersprungen (Zeile passt nicht): {r["name"]}')
                continue
            lines[k] = neuer_name(r['name'], prov)
            lines[k:k] = [f'# note: {heute} Provinz "{prov}" ergaenzt ({quelle}),',
                          '# note: siehe py/provinz_ergaenzen.py.']
        open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(lines))
        print(f'{os.path.basename(datei)}: {len(gs)} Namen ergaenzt')


def schrumpfen(geojson):
    """Aus dem vollen Natural-Earth-Satz die Laender ziehen, die wir fuehren."""
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    ziel = set(laender(recs))
    out = []
    for f in json.load(open(geojson))['features']:
        pr = f['properties']
        if pr.get('admin') in ziel:
            out.append({'admin': pr.get('admin'), 'name': pr.get('name'),
                        'geonunit': pr.get('geonunit'), 'iso': pr.get('iso_3166_2'),
                        'geometry': f['geometry']})
    json.dump(out, open(SLIM, 'w'))
    print(f'{len(out)} Polygone -> {SLIM}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
