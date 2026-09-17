#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schneidet aus dem GeoNames-Gesamtdump die Eintraege um die Pegel heraus.

allCountries.txt hat 13,5 Mio. Zeilen (1,7 GB); fuer Namens- und Positionsproben
braucht es nur die Umgebung der Saetze. Behalten wird jede Zeile in einer
0,25-Grad-Zelle, die an eine Zelle mit einem Satz grenzt (also bis ~25-50 km).

Quelle: https://download.geonames.org/export/dump/ (CC BY 4.0), geladen 15.09.2026.
Ergebnis: tide_tables/catalogues/geonames/umfeld.tsv
  geonameid, name, asciiname, alternatenames, lat, lon, fclass, fcode, cc

Usage: python3 py/geonames_umfeld.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                         # noqa: E402

DIR = os.path.join(ROOT, 'tide_tables/catalogues/geonames')
ZELLE = 0.25


def zelle(lat, lon):
    return int((lat + 90) // ZELLE), int((lon + 180) // ZELLE) % int(360 / ZELLE)


def main():
    n_lon = int(360 / ZELLE)
    zellen = set()
    for r in load_records():
        if r['lat'] is None or r['lon'] is None:
            continue
        a, b = zelle(r['lat'], r['lon'])
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                zellen.add((a + da, (b + db) % n_lon))
    n = k = 0
    with open(os.path.join(DIR, 'allCountries.txt'), encoding='utf-8') as fh, \
            open(os.path.join(DIR, 'umfeld.tsv.neu'), 'w', encoding='utf-8') as out:
        for line in fh:
            n += 1
            p = line.split('\t')
            try:
                lat, lon = float(p[4]), float(p[5])
            except (ValueError, IndexError):
                continue
            if zelle(lat, lon) in zellen:
                out.write('\t'.join((p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8])) + '\n')
                k += 1
    os.replace(os.path.join(DIR, 'umfeld.tsv.neu'), os.path.join(DIR, 'umfeld.tsv'))
    print(f'{k} von {n} Eintraegen in {len(zellen)} Zellen -> umfeld.tsv')


if __name__ == '__main__':
    main()
