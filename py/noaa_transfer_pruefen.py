#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft NOAA-Table-2-Uebertragungen gegen unabhaengige Nachbarsaetze.

Viele Saetze in harmonics_noaa_cptt.txt sind Uebertragungen: eine
Referenzstation mit Faktor und Zeitversatz. Bei einigen liegt die genannte
Referenz Tausende Kilometer entfernt, was auf eine falsche Verknuepfung
deutet. Die Entfernung allein beweist aber nichts -- entscheidend ist, ob
der Satz zu unabhaengigen Saetzen in seiner Nachbarschaft passt.

Als Massstab dient der Bestand selbst: wie stark weichen zwei Saetze
verschiedener Quellen in derselben Entfernung normalerweise voneinander
ab? Gemeldet wird, was deutlich darueber liegt.

Usage: python3 py/noaa_transfer_pruefen.py [--ref-km 1000] [--nachbar-km 25]
                                            [--faktor 3] [--csv <datei>]
"""
from __future__ import annotations

import collections
import csv
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import (load_records, km, curve_diff, MERIDIAN,    # noqa: E402
                          ROOT)

DATEI = 'harmonics/noaa/harmonics_noaa_cptt.txt'
REF_KM = 1000.0      # ab dieser Entfernung gilt die Referenz als verdaechtig
NACHBAR_KM = 25.0    # so weit wird nach einem unabhaengigen Nachbarn gesucht
FAKTOR = 3.0         # so viel ueber dem Normalmass gilt als Widerspruch
BINS = [1, 2, 5, 10, 25, 50]   # km-Grenzen fuer das Normalmass


def uebertragungen(pfad):
    """-> {Stationsname: (Referenzname, k, dt)} aus den Notizzeilen."""
    l = open(pfad, encoding='iso-8859-1').read().split('\n')
    out = {}
    for k, x in enumerate(l):
        if 'Table 2 transfer from' not in x:
            continue
        ref = x.split('transfer from ', 1)[1].split(' (no.')[0].strip()
        i = k
        while i < len(l) and not (l[i] and not l[i].startswith('#')
                                  and i + 1 < len(l) and MERIDIAN.match(l[i + 1])):
            i += 1
        if i >= len(l):
            continue
        m = re.search(r'k=([\d.]+) dt=([+-]\d+)min', x)
        out[l[i]] = (ref, float(m.group(1)) if m else None,
                     int(m.group(2)) if m else None)
    return out


def gitter(recs, grad=0.25):
    g = collections.defaultdict(list)
    for i, r in enumerate(recs):
        g[(round(r['lat'] / grad), round(r['lon'] / grad))].append(i)
    return g, grad


def nachbarn(recs, g, grad, r, weite):
    """Alle Saetze im Umkreis, ueber ein Gitter vorgefiltert."""
    n = int(weite / (111.0 * grad)) + 1
    a, b = round(r['lat'] / grad), round(r['lon'] / grad)
    out = []
    for da in range(-n, n + 1):
        for db in range(-n, n + 1):
            for i in g.get((a + da, b + db), []):
                x = recs[i]
                if x is r:
                    continue
                d = km(r, x)
                if d <= weite:
                    out.append((d, x))
    return sorted(out, key=lambda t: t[0])


def normalmass(recs, g, grad, weite):
    """Uebliche Kurvenabweichung zweier Saetze verschiedener Quellen je Entfernung."""
    proben = collections.defaultdict(list)
    for r in recs:
        for d, x in nachbarn(recs, g, grad, r, weite):
            if x['file'] == r['file']:
                continue
            b = next((k for k in BINS if d <= k), None)
            if b:
                proben[b].append(curve_diff(r, x)[1])
    return {b: statistics.median(v) for b, v in proben.items() if len(v) >= 20}, proben


def main(argv):
    ref_km, nachbar_km, faktor, ausgabe = REF_KM, NACHBAR_KM, FAKTOR, None
    for i, a in enumerate(argv):
        if a == '--ref-km':       ref_km = float(argv[i + 1])
        elif a == '--nachbar-km': nachbar_km = float(argv[i + 1])
        elif a == '--faktor':     faktor = float(argv[i + 1])
        elif a == '--csv':        ausgabe = argv[i + 1]

    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    g, grad = gitter(recs)
    nach_name = collections.defaultdict(list)
    for r in recs:
        nach_name[r['name']].append(r)

    mass, proben = normalmass(recs, g, grad, max(BINS))
    print('Normalmass: Kurvenabweichung zweier Saetze verschiedener Quellen')
    vor = 0
    for b in BINS:
        if b in mass:
            print(f'   {vor:3}-{b:3} km   {len(proben[b]):5} Paare   Median {mass[b]*100:5.1f} %')
        vor = b
    print()

    ueb = uebertragungen(os.path.join(ROOT, DATEI))
    fern = []
    for name, (ref, kf, dt) in ueb.items():
        a = [r for r in recs if r['name'] == name and 'noaa_cptt' in r['file']]
        b = nach_name.get(ref, [])
        if not (a and b):
            continue
        d = min(km(a[0], y) for y in b)
        if d >= ref_km:
            fern.append((d, a[0], ref, kf, dt))
    print(f'{len(ueb)} Uebertragungen, {len(fern)} mit Referenz ueber {ref_km:.0f} km\n')

    zeilen = []
    ohne = 0
    for d, r, ref, kf, dt in fern:
        kand = [(dd, x) for dd, x in nachbarn(recs, g, grad, r, nachbar_km)
                if x['file'] != r['file']]
        if not kand:
            ohne += 1
            continue
        dd, x = kand[0]
        rel = curve_diff(r, x)[1]
        b = next((k for k in BINS if dd <= k), None)
        erw = mass.get(b) if b else None
        zeilen.append(dict(satz=r['name'], referenz=ref, ref_km=round(d),
                           k=kf, dt_min=dt, nachbar=x['name'],
                           nachbar_datei=os.path.basename(x['file']),
                           nachbar_km=round(dd, 2),
                           abweichung=round(rel * 100, 1),
                           erwartet=round(erw * 100, 1) if erw else None,
                           verhaeltnis=round(rel / erw, 1) if erw else None))
    verdacht = [z for z in zeilen if z['verhaeltnis'] and z['verhaeltnis'] >= faktor]
    print(f'{len(zeilen)} davon haben einen unabhaengigen Nachbarn unter {nachbar_km:.0f} km, '
          f'{ohne} nicht')
    print(f'{len(verdacht)} weichen um mehr als das {faktor:.0f}-fache des Normalmasses ab:\n')
    for z in sorted(verdacht, key=lambda x: -x['verhaeltnis']):
        print(f'   {z["verhaeltnis"]:5.1f}x  {z["abweichung"]:5.1f} % statt {z["erwartet"]:4.1f} %  '
              f'{z["satz"][:40]:40}')
        print(f'   {"":9}Referenz {z["referenz"][:32]:32} {z["ref_km"]:6} km  k={z["k"]} dt={z["dt_min"]:+}min')
        print(f'   {"":9}Nachbar  {z["nachbar"][:32]:32} {z["nachbar_km"]:6.2f} km  '
              f'[{z["nachbar_datei"]}]\n')
    if ausgabe and zeilen:
        with open(ausgabe, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
            w.writeheader()
            w.writerows(sorted(zeilen, key=lambda x: -(x['verhaeltnis'] or 0)))
        print(f'{len(zeilen)} Zeilen nach {ausgabe}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))


def einigkeit(recs, g, grad, r, weite=25.0):
    """Sind die unabhaengigen Nachbarn untereinander einig, r aber nicht?

    Das ist der eigentliche Beweis. Weicht ein Satz von seinen Nachbarn ab,
    waehrend die Nachbarn untereinander uebereinstimmen, ist er der Fehler
    -- nicht sie. Stimmen die Nachbarn auch untereinander nicht ueberein,
    ist der Ort einfach schwierig und nichts bewiesen.
    """
    andere = [x for _d, x in nachbarn(recs, g, grad, r, weite)
              if x['file'] != r['file']]
    if len(andere) < 2:
        return None
    unter_sich = [curve_diff(a, b)[1]
                  for i, a in enumerate(andere) for b in andere[i + 1:]
                  if a['file'] != b['file']]
    if not unter_sich:
        return None
    gegen_r = [curve_diff(r, x)[1] for x in andere]
    return (statistics.median(unter_sich), statistics.median(gegen_r),
            len(andere))
