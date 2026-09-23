#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grobe Lagefehler bei den chinesischen Saetzen finden.

Anlass: Ruian stand 55 km draussen auf den Beiji-Inseln (die Kurve verriet
eine Flussmuendung), Hengmen 2.6 km an Land statt am Hengmen-Wasserweg.
Die Portal-/Buchpositionen sind auf die Bogenminute gerundet; 1 km Fehler
ist fuer die Vorhersage belanglos, grobe Fehler nicht.

Je Satz:
  km_meer   Abstand zur naechsten Ozeanzelle (GLOBE-Landmaske, ~1 km);
            Flusspegel im Delta liegen zu Recht einige km landeinwaerts
  kurve     Median des Kurvenunterschieds zu den 6 naechsten Saetzen
            (0.5-40 km); ein Pegel am falschen Gewaesser faellt heraus
  raster    Position auf ganze Bogenminuten gerundet

Ausgabe: harmonics/help/china_lage.csv, sortiert nach Verdacht.

Usage: python3 py/china_lage_pruefen.py
"""
from __future__ import annotations

import csv
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT, curve_diff, km, load_records      # noqa: E402
from lage_ausreisser import ozean_abstand                          # noqa: E402

AUS = os.path.join(ROOT, 'harmonics/help/china_lage.csv')


def raster(r):
    return all(abs(x * 60 - round(x * 60)) < 0.02 for x in (r['lat'], r['lon']))


def main():
    R = [r for r in load_records() if r['lat'] is not None and not r['current']]
    zeilen = []
    for r in R:
        if not r['name'].endswith('China'):
            continue
        d = ozean_abstand(r['lat'], r['lon'])
        nb = sorted((x for x in R if x is not r and 0.5 < km(r, x) <= 40), key=lambda x: km(r, x))[:6]
        cds = [curve_diff(r, x)[1] for x in nb]
        med = st.median(cds) if cds else None
        verdacht = (d or 0) / 3 + ((med or 0) * 100) / 15
        zeilen.append(dict(satz=r['name'], datei=os.path.basename(r['file']), lat=f"{r['lat']:.4f}",
                           lon=f"{r['lon']:.4f}", raster='ja' if raster(r) else '',
                           km_meer=f'{d:.1f}' if d is not None else '',
                           kurve_median_pct='' if med is None else f'{med * 100:.0f}', nachbarn=len(nb),
                           verdacht=f'{verdacht:.1f}'))
    zeilen.sort(key=lambda z: -float(z['verdacht']))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print(f'-> {os.path.relpath(AUS, ROOT)}: {len(zeilen)} Saetze')
    for z in zeilen[:30]:
        print(f"  {z['verdacht']:>5}  {z['satz'][:40]:40} {z['datei'][9:26]:17} Meer {z['km_meer']:>5} km"
              f"  Kurve {z['kurve_median_pct']:>3} %  {z['raster']}")


if __name__ == '__main__':
    sys.exit(main())
