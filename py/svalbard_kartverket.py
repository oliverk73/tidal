#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Svalbard aus Kartverket-Daten: Messreihe Ny-Alesund, Tafeln fuer die uebrigen Orte.

Svalbard steht im Bestand mit 19 Saetzen da, und kein einziger stammt aus
einer Messung -- alles NOAA-Table-2-Uebertragungen. Kartverket betreibt
dort genau einen dauerhaften Pegel (Ny-Alesund, NYA) und veroeffentlicht
darueber hinaus amtliche Tidetafeln fuer die Haefen der Inselgruppe.

  --lade      Stundenwerte (OBS) fuer Ny-Alesund, ein Jahr je Anfrage,
              nach water_levels/Norway_Kartverket/
  --tafeln    Hoch- und Niedrigwasser (tidetable) fuer die Orte in ORTE
  --fit       UTide auf das Geladene, Saetze nach harmonics/utide/

Eine Anfrage je Sekunde, ehrlicher User-Agent. Ohne --schreiben wird beim
Fit nur gezeigt, was entstuende.

Usage: python3 py/svalbard_kartverket.py --lade [--jahre 8]
       python3 py/svalbard_kartverket.py --fit [--schreiben]
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT                                       # noqa: E402

API = 'https://vannstand.kartverket.no/tideapi.php'
UA = 'oliver-weather-tides/1.0 (private tide research; oliver.k73@gmail.com)'
REIHEN = os.path.join(ROOT, 'water_levels', 'Norway_Kartverket')

# Der einzige dauerhafte Pegel (stationlist type=perm, 16.09.2026)
PEGEL = dict(code='NYA', name='Ny-Alesund', lat=78.928545, lon=11.938015)

# Orte, fuer die Kartverket amtliche Tafeln fuehrt (Tidevannstabeller
# for den norske kyst med Svalbard). Position aus der Tafelabfrage.
ORTE = [
    dict(code='LYR', name='Longyearbyen', lat=78.22314, lon=15.64686),
    dict(code='BAR', name='Barentsburg', lat=78.06667, lon=14.21667),
    dict(code='SVEA', name='Sveagruva', lat=77.89667, lon=16.71667),
    dict(code='HORN', name='Hornsund', lat=77.00000, lon=15.55000),
    dict(code='BJO', name='Bjornoya', lat=74.50000, lon=19.00000),
    dict(code='HOP', name='Hopen', lat=76.50000, lon=25.06667),
]


def hole(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode('utf-8')


def obs_jahr(lat, lon, jahr):
    """Stundenwerte eines Jahres -> [(zeit, cm)]; nur echte Messwerte."""
    url = (f'{API}?lat={lat}&lon={lon}&fromtime={jahr}-01-01T00:00&totime={jahr + 1}-01-01T00:00'
           f'&datatype=OBS&refcode=cd&interval=60&tzone=utc&dst=0&lang=en&tide_request=locationdata')
    text = hole(url)
    out = []
    try:
        wurzel = ET.fromstring(text)
    except ET.ParseError:
        return out
    for wl in wurzel.iter('waterlevel'):
        if wl.get('flag') == 'obs' and wl.get('value') and wl.get('time'):
            out.append((wl.get('time'), float(wl.get('value'))))
    return out


def tafel(lat, lon, jahr):
    """Hoch- und Niedrigwasser eines Jahres -> [(zeit, cm, 'high'|'low')]."""
    url = (f'{API}?lat={lat}&lon={lon}&fromtime={jahr}-01-01T00:00&totime={jahr + 1}-01-01T00:00'
           f'&datatype=TAB&refcode=cd&lang=en&interval=10&dst=0&tzone=utc&tide_request=locationdata')
    text = hole(url)
    out = []
    try:
        wurzel = ET.fromstring(text)
    except ET.ParseError:
        return out
    for wl in wurzel.iter('waterlevel'):
        if wl.get('value') and wl.get('time'):
            out.append((wl.get('time'), float(wl.get('value')), wl.get('flag') or ''))
    return out


def laden(argv):
    import csv
    jahre = int(argv[argv.index('--jahre') + 1]) if '--jahre' in argv else 8
    os.makedirs(REIHEN, exist_ok=True)
    heute = dt.date.today().year
    pfad = os.path.join(REIHEN, 'kartverket_NYA.csv')
    alt = {}
    if os.path.exists(pfad):
        for z in csv.DictReader(open(pfad)):
            alt[z['time']] = z['waterlevel_cm']
    for jahr in range(heute - jahre, heute + 1):
        n = 0
        for t, cm in obs_jahr(PEGEL['lat'], PEGEL['lon'], jahr):
            if t not in alt:
                alt[t] = cm
                n += 1
        print(f'  {PEGEL["name"]} {jahr}: {n} neue Stundenwerte (gesamt {len(alt)})', flush=True)
        time.sleep(1.0)
    with open(pfad, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['time', 'waterlevel_cm'])
        for t in sorted(alt):
            w.writerow([t, alt[t]])
    print('->', os.path.relpath(pfad, ROOT))

    for ort in ORTE:
        pf = os.path.join(REIHEN, f'tafel_{ort["code"]}.csv')
        zeilen = []
        for jahr in (heute - 1, heute):
            zeilen += tafel(ort['lat'], ort['lon'], jahr)
            time.sleep(1.0)
        if not zeilen:
            print(f'  {ort["name"]}: keine Tafel')
            continue
        with open(pf, 'w', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['time', 'value_cm', 'flag'])
            w.writerows(zeilen)
        print(f'  {ort["name"]}: {len(zeilen)} Scheitel -> {os.path.relpath(pf, ROOT)}')


def main(argv):
    if '--lade' in argv:
        return laden(argv)
    print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
