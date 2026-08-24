#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft das Referenz-Mapping aller NOAA-Table-2-Zeilen gegen die Geografie.

NOAA Table 2 gruppiert die Nebenstationen unter Ueberschriften "on
<Referenzstation>". Wo der Parser eine Ueberschrift uebersehen hat, laeuft
die vorige weiter -- ganze Bloecke haengen dann an einer falschen Referenz.

Der Abgleich nutzt aus, dass die Ueberschriften geografisch geordnet sind:
die gedruckte Referenz ist fast immer auch die naechstgelegene. Gemeldet
wird, wo das nicht zutrifft, und zwar zusammenhaengend nach
Stationsnummern, weil der Fehler blockweise auftritt.

Usage: python3 py/noaa_referenz_abgleich.py [--faktor 5] [--csv <datei>]
"""
from __future__ import annotations

import collections
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, MERIDIAN, ROOT           # noqa: E402

JSON = os.path.join(ROOT, 'harmonics/help/cptt2018_table2_full.json')
TXT = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_cptt.txt')
FAKTOR = 5.0     # so viel weiter als die naechste gilt als Verdacht
MIND_KM = 300.0  # darunter ist der Unterschied belanglos
ABSOLUT_KM = 1500.0  # so weit ist eine Referenz unabhaengig vom Faktor verdaechtig


def referenzorte():
    """Gedruckter Referenzname -> Satz im Bestand.

    Die Zuordnung kommt aus den erzeugten Notizzeilen: dort steht der
    aufgeloeste Name, in der JSON der gedruckte. Verbunden ueber die
    Stationsnummer.
    """
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None]
    nach = collections.defaultdict(list)
    for r in recs:
        nach[r['name']].append(r)
    l = open(TXT, encoding='iso-8859-1').read().split('\n')
    paare = collections.defaultdict(collections.Counter)
    full = {r['no']: r for r in json.load(open(JSON))}
    for k, x in enumerate(l):
        if 'Table 2 transfer from' not in x:
            continue
        m = re.search(r'\(no\.(\d+)\)', x)
        if not m:
            continue
        aufgeloest = x.split('transfer from ', 1)[1].split(' (no.')[0].strip()
        r = full.get(int(m.group(1)))
        if r and r.get('ref'):
            paare[r['ref']][aufgeloest] += 1
    out = {}
    for gedruckt, c in paare.items():
        name = c.most_common(1)[0][0]
        if name in nach:
            out[gedruckt] = (nach[name][0], name)
    return out, full


def main(argv):
    faktor, mind, ausgabe = FAKTOR, MIND_KM, None
    for i, a in enumerate(argv):
        if a == '--faktor':  faktor = float(argv[i + 1])
        elif a == '--km':    mind = float(argv[i + 1])
        elif a == '--csv':   ausgabe = argv[i + 1]

    orte, full = referenzorte()
    print(f'{len(orte)} Referenzstationen verortet')
    zeilen = [r for r in full.values() if not r.get('daily') and r.get('ref')]
    print(f'{len(zeilen)} Nebenstationen in der Tafel\n')

    befund = []
    for r in sorted(zeilen, key=lambda x: x['no']):
        if r['ref'] not in orte:
            continue
        p = {'lat': r['lat'], 'lon': r['lon']}
        d = km(p, orte[r['ref']][0])
        best = min(orte, key=lambda g: km(p, orte[g][0]))
        db = km(p, orte[best][0])
        # Gemeldet wird nur, wenn es ueberhaupt eine deutlich naehere
        # Alternative gibt. Sonst faellt Franzoesisch-Polynesien durch, wo
        # die gedruckte Referenz zwar 6468 km weg ist, aber auch die
        # naechste -- dort gibt es einfach nichts Naeheres.
        # Der Faktor allein genuegt nicht: liegt die naechste selbst weit
        # weg, kaeme eine Referenz in 4800 km Entfernung durch. Darum
        # zusaetzlich eine absolute Schranke.
        if (d > mind and db * 2 < d
                and (d > faktor * max(db, 1.0) or d > ABSOLUT_KM)):
            befund.append(dict(no=r['no'], name=r.get('name', ''),
                               gedruckt=r['ref'], gedruckt_km=round(d),
                               vorschlag=best, vorschlag_km=round(db),
                               seite=r.get('pdfpage')))
    print(f'{len(befund)} Zeilen, deren gedruckte Referenz mehr als das '
          f'{faktor:.0f}-fache weiter weg ist als die naechste\n')

    # Zusammenhaengende Nummernbloecke bilden -- der Fehler tritt blockweise auf.
    bloecke = []
    for b in befund:
        if (bloecke and bloecke[-1][-1]['gedruckt'] == b['gedruckt']
                and bloecke[-1][-1]['vorschlag'] == b['vorschlag']
                and b['no'] - bloecke[-1][-1]['no'] <= 12):
            bloecke[-1].append(b)
        else:
            bloecke.append([b])
    print(f'{len(bloecke)} zusammenhaengende Bloecke:\n')
    for bl in sorted(bloecke, key=lambda x: -len(x)):
        a, z = bl[0], bl[-1]
        print(f'   {len(bl):3} Zeilen  no {a["no"]}-{z["no"]}  S.{a["seite"]}  '
              f'{a["gedruckt"][:20]:20} {a["gedruckt_km"]:6} km  ->  '
              f'{a["vorschlag"][:20]:20} {a["vorschlag_km"]:5} km')
        if len(bl) <= 3:
            for b in bl:
                print(f'          {b["name"][:52]}')
    if ausgabe and befund:
        with open(ausgabe, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(befund[0]))
            w.writeheader()
            w.writerows(befund)
        print(f'\n{len(befund)} Zeilen nach {ausgabe}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
