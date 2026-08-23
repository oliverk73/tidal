#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wertet harmonics/help/bom_qualitaet.csv zu Loeschvorschlaegen aus.

Zwei Saetze, die gegen dieselbe BOM-Tafel gemessen wurden, sind noch keine
Dublette: die Suche nimmt alles im Umkreis, und 8 km auseinander liegende
Pegel landen an derselben Tafel. Erst wenn die beiden Saetze auch zueinander
nahe stehen, geht es um denselben Pegel.

Entschieden wird ausschliesslich nach gemessener Qualitaet, nicht nach
Quelle. Vorgeschlagen wird nur, was deutlich schlechter ist.

Usage: python3 py/bom_dubletten.py [--km 2.0] [--faktor 2.0] [--delta 0.01]
"""
from __future__ import annotations

import collections
import csv
import difflib
import re
import unicodedata
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, curve_diff               # noqa: E402
from health_check import namekey                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, 'harmonics/help/bom_qualitaet.csv')

NAH_KM = 2.0        # bis hier gelten zwei Saetze als derselbe Pegel
FAKTOR = 2.0        # ab diesem Vielfachen gilt ein Satz als deutlich schlechter
DELTA = 0.01        # und der Abstand muss mindestens so gross sein (m)
TAFEL_KM = 2.5      # so nah muessen beide an der Tafel stehen, die sie beurteilt


def _ort(name):
    """Nur der Ortsteil vor dem ersten Komma, ohne Akzente und Zeichen.

    Der volle Name traegt Bundesland und Land mit; danach sind "Cape
    Grenville, Queensland, Australia" und "Harvey Island, Queensland,
    Australia" zu 55 Prozent gleich, obwohl es zwei Orte sind.
    """
    t = unicodedata.normalize('NFKD', name.split(',')[0])
    t = t.encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]', ' ', t).strip()


def gleicher_ort(a, b):
    """Bezeichnen zwei Saetze denselben Ort?

    Ein Klammerzusatz wie "Bundaberg (Burnett Heads)" nennt den Pegel beim
    zweiten Namen -- deshalb zaehlt auch, wenn der eine Ortsname im anderen
    steckt.
    """
    x, y = _ort(a['name']), _ort(b['name'])
    if namekey(a['name']) and namekey(a['name']) == namekey(b['name']):
        return True
    if x and y and (x in y or y in x):
        return True
    return difflib.SequenceMatcher(None, x, y).ratio() > 0.80


def main(argv):
    nah, faktor, delta, tafel = NAH_KM, FAKTOR, DELTA, TAFEL_KM
    for i, a in enumerate(argv):
        if a == '--km':      nah = float(argv[i + 1])
        elif a == '--faktor': faktor = float(argv[i + 1])
        elif a == '--delta':  delta = float(argv[i + 1])
        elif a == '--tafel':  tafel = float(argv[i + 1])

    recs = load_records()
    byname = {}
    for r in recs:
        byname.setdefault((os.path.basename(r['file']), r['name']), r)

    rows = list(csv.DictReader(open(CSV, encoding='utf-8')))
    fehlt = 0
    for row in rows:
        r = byname.get((row['datei'], row['satz']))
        if r is None:
            fehlt += 1
        row['_rec'] = r
        row['_rms'] = float(row['rms_m'])

    # Pro Satz nur die beste Messung behalten -- manche Saetze sind gegen
    # mehrere Jahrgaenge derselben Tafel gemessen.
    best = {}
    for row in rows:
        k = (row['station'], row['datei'], row['satz'])
        if k not in best or row['_rms'] < best[k]['_rms']:
            best[k] = row

    gruppen = collections.defaultdict(list)
    for row in best.values():
        gruppen[row['station']].append(row)

    # Ein Satz, der an irgendeiner Tafel der beste ist, hat einen eigenen
    # Pegel und ist nirgends eine Dublette. Ohne diese Regel melden sich
    # Harvey Island und Hicks Island gegenseitig als Dublette, obwohl beide
    # eine eigene gedruckte Tafel haben -- sie stehen nur 1.8 km auseinander.
    eigen = set()
    for st, rs in gruppen.items():
        sieger = min(rs, key=lambda x: x['_rms'])
        eigen.add((sieger['datei'], sieger['satz']))

    paare, fern, weg, nachbar = [], [], [], []
    for st, rs in sorted(gruppen.items()):
        if len(rs) < 2:
            continue
        rs.sort(key=lambda x: x['_rms'])
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                ra, rb = a['_rec'], b['_rec']
                if not (ra and rb):
                    continue
                d = km(ra, rb)
                _, rel = curve_diff(ra, rb)
                if d > nah:
                    fern.append((st, a, b, d, rel))
                    continue
                paare.append((st, a, b, d, rel))
                if (b['datei'], b['satz']) in eigen:
                    continue
                if not (b['_rms'] >= a['_rms'] * faktor and b['_rms'] - a['_rms'] >= delta):
                    continue
                # Beide muessen nahe an der Tafel liegen, die sie beurteilt.
                # Die beiden Saetze "Melbourne (Williamstown)" werden sonst
                # an der 4.4 km entfernten Tafel St Kilda gemessen -- in der
                # Port Phillip Bay laeuft die Tide dort schon anders.
                if max(float(a['abstand_m']), float(b['abstand_m'])) > tafel * 1000:
                    fern.append((st, a, b, d, rel))
                    continue
                # Gleicher Ort oder nur Nachbar? Verschiedene Namen in 1.5 km
                # Abstand sind zwei Pegel -- der schlechtere ist dann ein
                # Qualitaetsproblem, aber keine Dublette.
                if gleicher_ort(ra, rb):
                    weg.append((st, a, b, d, rel))
                else:
                    nachbar.append((st, a, b, d, rel))

    print(f'{len(rows)} Messungen, {len(best)} Saetze, {fehlt} nicht im Bestand gefunden')
    print(f'{sum(1 for g in gruppen.values() if len(g) > 1)} Stationen mit mehreren Saetzen')
    print(f'{len(paare)} Paare naeher als {nah} km, {len(fern)} weiter auseinander (kein Dublettenfall)')
    print(f'{len(weg)} Loeschvorschlaege (mindestens {faktor}x schlechter und {delta*100:.0f} cm Abstand)\n')

    # Ein Satz kann in mehreren Paaren verlieren; nur einmal loeschen.
    einmal = {}
    for st, a, b, d, rel in weg:
        k = (b['datei'], b['satz'])
        if k not in einmal or b['_rms'] / a['_rms'] > einmal[k][5]:
            einmal[k] = (st, a, b, d, rel, b['_rms'] / a['_rms'])

    print(f'{len(einmal)} verschiedene Saetze zum Loeschen:\n')
    for st, a, b, d, rel, f in sorted(einmal.values(), key=lambda x: -x[5]):
        print(f'{st}')
        print(f'   weg   {b["_rms"]:.4f} m  {b["satz"][:56]:56} {b["datei"]}')
        print(f'   bleibt{a["_rms"]:.4f} m  {a["satz"][:56]:56} {a["datei"]}')
        print(f'         Faktor {f:.1f}   Abstand {d*1000:.0f} m   Kurvenabweichung {rel*100:.0f} %\n')

    print(f'\n{len(nachbar)} Faelle: nah beieinander, aber verschiedene Ortsnamen --')
    print('nicht loeschen, sondern einzeln pruefen:\n')
    for st, a, b, d, rel in sorted(nachbar, key=lambda x: -x[2]['_rms']):
        print(f'   {b["_rms"]:.4f} m  {b["satz"][:52]:52} {b["datei"]}')
        print(f'   {"":9} Tafel {st}, {d*1000:.0f} m entfernt, dort {a["_rms"]:.4f} m mit {a["satz"][:40]}\n')

    z = collections.Counter(k[0] for k in einmal)
    print('Nach Datei:')
    for f, n in z.most_common():
        print(f'   {n:3}  {f}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
