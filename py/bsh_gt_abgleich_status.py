#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Abdeckung in harmonics/help/bsh_gt27_abgleich.csv gegen den heutigen Bestand neu berechnen (20.11.2026).

Behaelt Verortung und Handkorrekturen der Datei (lat/lon, ort_gefunden) und rechnet nur naechster_satz,
naechster_km und status neu – wie py/bsh_gt_abgleich.py: naechster Wasserstands-Satz (keine Stroemung),
<= 5 km gedeckt, 5–15 km nah, > 15 km Luecke. Der volle Neulauf (py/bsh_gt_abgleich.py) dauert > 10 min und
verliert Handkorrekturen der Ortslage.

Usage: venv/bin/python py/bsh_gt_abgleich_status.py [--trocken]
"""
import collections
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/help/bsh_gt27_abgleich.csv')


def km(la1, lo1, la2, lo2):
    return math.hypot((la2 - la1) * 111.2, (lo2 - lo1) * 111.2 * math.cos(math.radians((la1 + la2) / 2)))


def main(argv):
    R = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    with open(DATEI, newline='') as f:
        zeilen = list(csv.DictReader(f))
        felder = list(zeilen[0].keys())
    vorher = collections.Counter(z['status'] for z in zeilen)
    wechsel = []
    for z in zeilen:
        if not z['lat']:
            continue
        la, lo = float(z['lat']), float(z['lon'])
        best = min(R, key=lambda r: km(la, lo, r['lat'], r['lon']))
        d = km(la, lo, best['lat'], best['lon'])
        status = 'gedeckt' if d <= 5 else ('nah' if d <= 15 else 'luecke')
        neu_satz = '' if best['name'] == z['ort_gefunden'] else best['name']
        if status != z['status']:
            wechsel.append((z['nr'], z['namen'][:40], z['status'], status, best['name'], round(d, 1)))
        z.update(naechster_satz=neu_satz, naechster_km='%.1f' % d, status=status)
    nachher = collections.Counter(z['status'] for z in zeilen)
    print('Saetze im Bestand: %d' % len(R))
    print('vorher ', dict(vorher))
    print('nachher', dict(nachher))
    for w in wechsel:
        print('  %s %-40s %s -> %s  (%s, %.1f km)' % w)
    if '--trocken' not in argv:
        with open(DATEI + '.neu', 'w', newline='') as f:
            wr = csv.DictWriter(f, fieldnames=felder)
            wr.writeheader()
            wr.writerows(zeilen)
        os.replace(DATEI + '.neu', DATEI)


if __name__ == '__main__':
    main(sys.argv[1:])
