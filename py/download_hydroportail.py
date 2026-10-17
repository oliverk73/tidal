#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laedt Wasserstaende (Rohdaten, Hauteur instantanee) von HydroPortail (hydro.eaufrance.fr) monatsweise.

Oliver 17.10.2026: Rouen (Seine) fehlte im Bestand. SHOM rechnet fuer die Seine oberhalb Honfleur keine
Kurven, REFMAR hat nur Honfleur/Le Havre; die HAROPA-Pegel (Station partenaire HAROPA) stehen aber bei
Vigicrues/HydroPortail. Hub'Eau (observations_tr) haelt nur 30 Tage, der Ajax-Dienst der Stationsseite
liefert die ganze Rohreihe. Werte in mm ueber Pegelnull -> Meter; Stundenwert = Median aller Werte mit
|t - hh:00| < 30 min (naechste Stunde, nicht abgerundet).

Usage: python3 py/download_hydroportail.py CODE:JJJJ-MM:JJJJ-MM [...]
       -> water_levels/France_HydroPortail/hp_<code>.csv  (time,waterlevel_m; UTC)
"""
import collections
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels/France_HydroPortail')
URL = 'https://www.hydro.eaufrance.fr/stationhydro/ajax/%s/series?'


def monat(code, y, m):
    a = dt.date(y, m, 1)
    b = dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)
    q = urllib.parse.urlencode({
        'hydro_series[startAt]': a.strftime('%d/%m/%Y'), 'hydro_series[endAt]': b.strftime('%d/%m/%Y'),
        'hydro_series[variableType]': 'simple_and_interpolated_and_hourly_variable',
        'hydro_series[simpleAndInterpolatedAndHourlyVariable]': 'H', 'hydro_series[statusData]': 'raw'})
    req = urllib.request.Request(URL % code + q, headers={'User-Agent': 'Mozilla/5.0', 'X-Requested-With': 'XMLHttpRequest'})
    for k in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=120))['series']['data']
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
        while (y, m) <= (ye, me):
            for x in monat(code, y, m):
                if x.get('v') is None:
                    continue
                t = dt.datetime.strptime(x['t'][:19], '%Y-%m-%dT%H:%M:%S')
                h = t.replace(minute=0, second=0) + dt.timedelta(hours=t.minute >= 30)
                werte[h].append(x['v'] / 1000)
            y, m = (y + (m == 12), m % 12 + 1)
            time.sleep(0.5)
        pfad = os.path.join(ZIEL, 'hp_%s.csv' % code)
        with open(pfad, 'w') as fh:
            fh.write('time,waterlevel_m\n')
            for h in sorted(werte):
                v = sorted(werte[h])
                fh.write('%sZ,%.3f\n' % (h.isoformat(), v[len(v) // 2]))
        print('%s: %d Stundenwerte %s..%s -> %s' % (code, len(werte), min(werte) if werte else '-',
                                                    max(werte) if werte else '-', os.path.relpath(pfad, ROOT)), flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
