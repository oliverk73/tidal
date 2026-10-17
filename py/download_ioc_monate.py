#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laedt IOC-Pegel monatsweise und bildet Stundenwerte (naechste Stunde, nicht abgerundet).

Oliver 17.10.2026 (PSMSL-Frage): PSMSL hat nur Monatsmittel; Stundenwerte fuer russische Pegel
gibt es beim IOC. Starodubskoe, Severo-Kuril'sk, Vodopadnaya und Cape Kril'on waren nicht im Bestand.
Das alte py/download_ioc_russia.py bildet Stunden durch Abrunden (Mittel von hh:00..hh:59 auf hh:00)
-- genau der Fehler, der Korsakov/Poronaysk 30 min verschob (Memory ioc-stundenmittel-halbe-stunde).
Hier: Mittel aller Werte mit |t - hh:00| < 30 min auf hh:00; ein Sensor je Pegel (rad vor prs/enc).

Usage: python3 py/download_ioc_monate.py CODE:JJJJ-MM:JJJJ-MM [...]
       -> water_levels/Russia_IOC/ioc_<code>_monate.csv  (time,waterlevel_m; UTC)
"""
import collections
import datetime as dt
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels/Russia_IOC')
SENSOR = ['rad', 'ra2', 'prs', 'pr1', 'pwl', 'ras', 'enc', 'flt', 'bub']


def monat(code, y, m):
    a = dt.date(y, m, 1)
    b = dt.date(y + (m == 12), m % 12 + 1, 1)
    url = ('https://www.ioc-sealevelmonitoring.org/service.php?query=data&code=%s&timestart=%s&timestop=%s&format=json'
           % (code, a.isoformat(), b.isoformat()))
    for k in range(3):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'tidal-research'}), timeout=120))
        except Exception:                                   # noqa: BLE001
            time.sleep(5 * (k + 1))
    return []


def main(argv):
    os.makedirs(ZIEL, exist_ok=True)
    for arg in argv:
        code, von, bis = arg.split(':')
        y, m = map(int, von.split('-'))
        ye, me = map(int, bis.split('-'))
        werte = collections.defaultdict(list)
        sensoren = collections.Counter()
        roh = []
        while (y, m) <= (ye, me):
            D = monat(code, y, m)
            roh += D
            sensoren.update(x.get('sensor') for x in D)
            y, m = (y + (m == 12), m % 12 + 1)
            time.sleep(0.5)
        s = next((x for x in SENSOR if sensoren.get(x)), None)
        for x in roh:
            if x.get('sensor') != s or x.get('slevel') is None:
                continue
            t = dt.datetime.strptime(x['stime'].strip(), '%Y-%m-%d %H:%M:%S')
            h = t.replace(minute=0, second=0)
            if t.minute >= 30:
                h += dt.timedelta(hours=1)
            werte[h].append(float(x['slevel']))
        pfad = os.path.join(ZIEL, 'ioc_%s_monate.csv' % code)
        with open(pfad, 'w') as fh:
            fh.write('time,waterlevel_m\n')
            for h in sorted(werte):
                v = sorted(werte[h])
                fh.write('%sZ,%.4f\n' % (h.isoformat(), v[len(v) // 2]))      # Median gegen Ausreisser
        print('%s: Sensor %s, %d Stundenwerte %s..%s -> %s' % (code, s, len(werte), min(werte) if werte else '-',
                                                               max(werte) if werte else '-', os.path.relpath(pfad, ROOT)), flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
