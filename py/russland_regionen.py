#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traegt bei allen russischen Saetzen das Foederationssubjekt in Namen und Feld # region ein.

Oliver 15.10.2026: "Ergaenze bei allen russischen Stationen die Region. Krai oder Oblast?"
Weder noch fuer alle: jedes Subjekt hat seinen festen Typ, und so steht es bei Google Maps
(Primorsky Krai, Sakhalin Oblast, Republic of Karelia, Chukotka Autonomous Okrug). Natural Earth
liefert nur die Grenzen (ISO-Code); die Namen kommen aus NAMEN unten, nicht aus Natural Earth
("Maga Buryatdan Region" ist dort Magadan).

Zuordnung: Polygon, das den Pegel enthaelt, sonst naechstes russisches Polygon.
Namen: "A, Russia" -> "A, <Subjekt>, Russia". Ein alter Mittelteil wird Kontext in der Klammer
("Ostrov Mamya (Matua), Kuril Islands" -> "Ostrov Mamya (Matua, Kuril Islands), Sakhalin Oblast");
ein alter Regionsname (Sakhalin, Krasnoyarsk Krai) entfaellt.

Usage: venv/bin/python py/russland_regionen.py [--schreiben]
"""
import collections
import json
import os
import re
import sys

from shapely.geometry import Point, shape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import active_files                             # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERIDIAN = re.compile(r'^[+-]?\d{1,2}:\d{2}\b')
NAMEN = {
    'RU-ARK': 'Arkhangelsk Oblast', 'RU-MUR': 'Murmansk Oblast', 'RU-NEN': 'Nenets Autonomous Okrug',
    'RU-KR': 'Republic of Karelia', 'RU-YAN': 'Yamalo-Nenets Autonomous Okrug', 'RU-KYA': 'Krasnoyarsk Krai',
    'RU-SA': 'Sakha Republic', 'RU-CHU': 'Chukotka Autonomous Okrug', 'RU-KAM': 'Kamchatka Krai',
    'RU-MAG': 'Magadan Oblast', 'RU-KHA': 'Khabarovsk Krai', 'RU-SAK': 'Sakhalin Oblast',
    'RU-PRI': 'Primorsky Krai', 'RU-SPE': 'Saint Petersburg', 'RU-LEN': 'Leningrad Oblast',
    'RU-KGD': 'Kaliningrad Oblast', 'RU-KDA': 'Krasnodar Krai', 'RU-ROS': 'Rostov Oblast',
    'RU-DA': 'Republic of Dagestan', 'RU-AST': 'Astrakhan Oblast', 'RU-KL': 'Republic of Kalmykia',
    'RU-KO': 'Komi Republic',
}
SOLOWKI = (64.95, 65.25, 35.4, 36.3)         # Solowezki-Inseln: Arkhangelsk Oblast, NE-Polygon gibt Karelien
WEG = {'sakhalin', 'krasnoyarsk krai'}            # alter Mittelteil, den das Subjekt ersetzt


def polygone():
    J = json.load(open(os.path.join(ROOT, 'harmonics/help/ne_admin1_welt.json')))
    return [(f['iso'], shape(f['geometry'])) for f in J if f['admin'] == 'Russia']


def subjekt(P, lat, lon):
    pt = Point(lon, lat)
    for iso, g in P:
        if g.contains(pt) and not (SOLOWKI[0] < lat < SOLOWKI[1] and SOLOWKI[2] < lon < SOLOWKI[3]):
            return iso, 0.0
    if SOLOWKI[0] < lat < SOLOWKI[1] and SOLOWKI[2] < lon < SOLOWKI[3]:
        return 'RU-ARK', 0.0
    iso, g = min(P, key=lambda x: x[1].distance(pt))
    return iso, g.distance(pt) * 111.2


def neuer_name(name, reg):
    teile = name.split(', ')
    if teile[-1] == 'Russia':
        teile = teile[:-1]
    basis, mitte = teile[0], [t for t in teile[1:] if t.lower() not in WEG and t != reg]
    if mitte:
        ctx = ', '.join(mitte)
        m = re.match(r'^(.*?) \((.*)\)$', basis)
        basis = '%s (%s, %s)' % (m.group(1), m.group(2), ctx) if m else '%s (%s)' % (basis, ctx)
    return '%s, %s, Russia' % (basis, reg)


def main(argv):
    P = polygone()
    plan, weit = [], []
    for f in active_files():
        L = open(os.path.join(ROOT, f), encoding='iso-8859-1').read().split('\n')
        aend = False
        i = 0
        while i < len(L) - 1:
            l = L[i]
            if l and not l.startswith('#') and MERIDIAN.match(L[i + 1]):
                j, land, lat, lon, regz = i - 1, None, None, None, None
                while j >= 0 and L[j].startswith('#') and L[j] != '#':
                    if L[j].startswith('# country:'):
                        land = L[j].split(':', 1)[1].strip()
                    elif L[j].startswith('# !latitude:'):
                        lat = float(L[j].split(':')[1])
                    elif L[j].startswith('# !longitude:'):
                        lon = float(L[j].split(':')[1])
                    elif re.match(r'# (region|province|state): ', L[j]):
                        regz = j
                    j -= 1
                if (l.endswith(', Russia') or land == 'Russia') and lat is not None:
                    iso, d = subjekt(P, lat, lon)
                    if not l.endswith(', Russia') and d > 100:
                        print('NICHT RUSSLAND (country-Feld falsch?)', l, os.path.basename(f))
                        i += 1
                        continue
                    reg = NAMEN.get(iso)
                    if reg is None:
                        print('UNBEKANNT', iso, l, f)
                    else:
                        neu = neuer_name(l, reg)
                        plan.append((f, l, neu, iso, d))
                        if d > 20:
                            weit.append((f, l, neu, d))
                        L[i] = neu
                        if regz is not None:
                            L[regz] = '# region: ' + reg
                        else:
                            L.insert(i, '# region: ' + reg)
                            i += 1
                        aend = True
            i += 1
        if aend and '--schreiben' in argv:
            schreiben(os.path.join(ROOT, f), '\n'.join(L))
    print(len(plan), 'Saetze', dict(collections.Counter(NAMEN[p[3]] for p in plan)))
    for f, a, n, iso, d in plan:
        if a.count(', ') != 1:
            print('  %-60s -> %s' % (a, n))
    for f, a, n, d in weit:
        print('  WEIT %.0f km: %s -> %s [%s]' % (d, a, n, os.path.basename(f)))


if __name__ == '__main__':
    main(sys.argv[1:])
