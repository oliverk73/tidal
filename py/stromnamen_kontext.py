#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ergaenzt zu generische NOAA-Stromnamen um die Buchueberschrift (1.11.2026, Oliver).

"Harbor (W of Soper Point)" -> "Oyster Bay Harbor (W of Soper Point)", "Beach Channel (bridge)" ->
"Beach Channel (bridge, Jamaica Bay)". NOAA nennt in Table 2 und in der API nur den eingerueckten Teil;
der Ort steht in der Zwischenueberschrift (py/noaa_t2_ueberschriften.py) oder im Abschnittstitel.
Reine Gattungsnamen bekommen die Ueberschrift vorangestellt, wenn sie ein Gewaesser benennt, sonst in die Klammer.
Satz <-> Buch: gleiche Position auf 0.01 Grad. Ohne Buchzeile bleibt der Name.

Usage: python3 py/stromnamen_kontext.py [--schreiben] -> harmonics/help/stromnamen_kontext_20261101.csv
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc                                           # noqa: E402

ROOT = hc.ROOT if hasattr(hc, 'ROOT') else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/stromnamen_kontext_20261101.csv')
ATTR = r'(?:Beach|Main|Ship|North|South|East|West|Middle|Mid|Inner|Outer|Upper|Lower|Northeast|Northwest|Southeast|Southwest|Railroad|Highway|Old|New|Back|Cross|Bay|Harbor|Entrance|Range|Turning)'
GATT = r'(?:Channel|Entrance|Harbor|Harbour|Bridge|Drawbridge|Bar|Reach|Range|Cut|Inlet|Passage|Pass|Canal|Narrows|River|Bay|Basin|Midchannel|Mouth|Channel)'
GENERISCH = re.compile(rf'^(?:{ATTR} )*{GATT}$', re.I)
REIN = re.compile(rf'^(?:Harbor |Turning )?{GATT}$')
VON_HAND = {'Southeast Channel, Florida Current': 'Southeast Channel (Dry Tortugas), Florida Current',
            'Southwest Channel, Florida Current': 'Southwest Channel (Dry Tortugas), Florida Current',
            'South Channel, California Current': 'South Channel (San Francisco Bay Entrance), California Current'}
GEWAESSER = re.compile(r'(Bay|Harbor|Harbour|River|Inlet|Sound|Pass|Channel|Cut|Strait)$')


def titel(s):
    return ' '.join(w.capitalize() if w.lower() not in ('of', 'and') else w.lower() for w in s.split()).replace('St.', 'St.')


def main():
    B = {}
    H = json.load(open(os.path.join(ROOT, 'harmonics/help/noaa_t2_ueberschriften.json'), encoding='utf-8'))
    for buch in ('acct', 'pcct'):
        for x in json.load(open(os.path.join(ROOT, f'harmonics/help/{buch}_t2_full.json'), encoding='utf-8')):
            k = H[buch].get(str(x['no']))
            B.setdefault((round(x['lat'], 2), round(x['lon'], 2)), []).append((k, x.get('sec', ''), x['name']))
    aus = []
    for r in hc.load_records():
        if not r['current'] or r['lat'] is None or 'noaa' not in r['file']:
            continue
        m = re.match(r'^([^,(]+?)(?: \(([^)]*)\))?(, .*)$', r['name'])
        if not m or not GENERISCH.match(m[1]):
            continue
        z = B.get((round(r['lat'], 2), round(r['lon'], 2)))
        if not z:
            aus.append(dict(datei=r['file'], alt=r['name'], neu='', quelle='keine Buchzeile'))
            continue
        kopf = next((k for k, _s, n in z if k), None)
        sec = titel(z[0][1]) if z[0][1] else ''
        ort = re.sub(r'-cont\.$', '', kopf or sec)
        if 'Average' in ort or m[1] == 'New Bridge':
            aus.append(dict(datei=r['file'], alt=r['name'], neu=VON_HAND.get(r['name'], ''), quelle=f"von Hand {r['lat']} {r['lon']}"))
            continue
        if ',' in ort:
            ort = 'York River'     # Ueberschrift "Tue Marshes Light, 2.7 miles west of"
        if not ort or ort.lower() in r['name'].lower():
            continue
        if REIN.match(m[1]):                                 # reiner Gattungsname: Suchwort braucht den Ort
            neu = f"{ort} {m[1]}" + (f' ({m[2]})' if m[2] else '') + m[3]
        else:
            neu = f"{m[1]} ({m[2] + ', ' if m[2] else ''}{ort}){m[3]}"
        aus.append(dict(datei=r['file'], alt=r['name'], neu=neu, quelle='Ueberschrift' if kopf else 'Abschnitt'))
    with open(AUS, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'alt', 'neu', 'quelle'])
        w.writeheader()
        w.writerows(aus)
    print(len(aus))
    for x in aus:
        print(f"{x['alt'][:52]:52s} -> {x['neu'][:66]}")
    if '--schreiben' in sys.argv:
        for pfad in sorted({x['datei'] for x in aus}):
            p = os.path.join(ROOT, pfad)
            t = open(p, encoding='iso-8859-1').read().split('\n')
            for x in aus:
                if x['datei'] == pfad and x['neu']:
                    k = t.index(x['alt'])
                    t[k] = x['neu']
                    i = k
                    while not t[i].startswith('# !units'):
                        i -= 1
                    t[i:i] = ['# note: 20261101 Name um die NOAA-Buchueberschrift ergaenzt (Oliver).']
            open(p, 'w', encoding='iso-8859-1').write('\n'.join(t))


if __name__ == '__main__':
    main()
