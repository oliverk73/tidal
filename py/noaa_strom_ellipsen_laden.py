#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laedt die vollstaendigen Strom-Ellipsenkonstanten (Haupt- UND Nebenachse) der NOAA-CO-OPS-Stromstationen.

Grundlage fuer Stufe 3 der eigenen Tidenrechnung (Strom-Ellipsen, Oliver 4.11.2026). Die Harmonics-Saetze
fuehren nur die Hauptachse (Flut/Ebbe); mdapi harcon.json liefert je Konstituente zusaetzlich
minorAmplitude/minorPhaseGMT und die Achsrichtung azi.

Quelle: https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/<id>/harcon.json?bin=<n>
Ziel:   water_levels/NOAA_current_harcon/<id>_<bin>.json (Rohantwort, vorhandene werden uebersprungen)

Usage: venv/bin/python py/noaa_strom_ellipsen_laden.py
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels/NOAA_current_harcon')
QUELLE = os.path.join(ROOT, 'harmonics/classic/harmonics-dwf-20251228-free.txt')
URL = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{s}/harcon.json?bin={b}'


def ids():
    out = []
    for l in open(QUELLE, encoding='iso-8859-1'):
        m = re.match(r'# noaa_station_id:\s*(\S+)_(\d+)\s*$', l)
        if m:
            out.append((m.group(1), m.group(2)))
    return sorted(set(out))


def laden(sb):
    s, b = sb
    pfad = os.path.join(ZIEL, f'{s}_{b}.json')
    if os.path.exists(pfad) and os.path.getsize(pfad) > 100:
        return 'da'
    for k in range(4):
        try:
            req = urllib.request.Request(URL.format(s=s, b=b), headers={'User-Agent': 'tide-research'})
            d = json.load(urllib.request.urlopen(req, timeout=60))
            json.dump(d, open(pfad, 'w'))
            return 'ok' if d.get('HarmonicConstituents') else 'leer'
        except Exception:
            time.sleep(2 * (k + 1))
    return 'fehler'


def main():
    os.makedirs(ZIEL, exist_ok=True)
    liste = ids()
    print(len(liste), 'Stationen/Bins', flush=True)
    zahl = {}
    with cf.ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(laden, liste)):
            zahl[r] = zahl.get(r, 0) + 1
            if i % 250 == 0:
                print(i, zahl, flush=True)
    print('fertig', zahl)


if __name__ == '__main__':
    sys.exit(main())
