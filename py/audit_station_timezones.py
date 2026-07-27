#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft die Anzeige-Zeitzone jeder Station gegen die an ihren Koordinaten
tatsaechlich geltende Zone (timezonefinder) und schreibt eine CSV.

Hintergrund: In XTide steht hinter dem Meridian die Zone, in der die PHASEN
liegen; dahinter nach dem Doppelpunkt die Zone, in der die Vorhersage ANGEZEIGT
wird. Beim ATT-Sekundaerhafen-Transfer wird beides vom Bezugshafen geerbt --
der Meridian zu Recht, die Anzeigezone nicht. Ausserdem tragen Altbestaende
teils historisch falsche Zonen (Spitzbergen auf Europe/Moscow).

Zwei Befundklassen:
  A  Anzeige in UTC statt Ortszeit -- Konvention des utide-Zweigs, kein Fehler
     im engeren Sinn, aber fuer den Endanwender irrefuehrend.
  B  Anzeige in der Zone eines anderen Ortes mit abweichendem UTC-Versatz
     -- echter Fehler.

Reine Namensunterschiede ohne Versatzunterschied (Europe/Rome vs Europe/Zagreb)
werden NICHT gemeldet.

Der Meridian wird nie angefasst -- die Rechenwerte aendern sich durch eine
Korrektur der Anzeigezone nicht.

Aufruf: python3 py/audit_station_timezones.py [ZIEL.csv]
"""
from __future__ import annotations
import csv
import glob
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

HARM = '/home/oliver/weather/harmonics'
DEFAULT_OUT = f'{HARM}/help/timezone_audit_2026-07-27.csv'
# Vier Stichtage: Sommer- und Winterzeit im laufenden und im Folgejahr. Ein
# einzelnes Datum reicht nicht -- tzdata 2026b laesst z.B. British Columbia ab
# 2027 dauerhaft auf Sommerzeit, wodurch America/Vancouver und America/Inuvik
# im Januar 2027 zufaellig gleich sind, im Juli aber nicht.
DATES = [datetime(y, m, 15, 12) for y in (2026, 2027) for m in (1, 7)]
JAN, JUL = DATES[0], DATES[1]
MER = re.compile(r'^([+-]\d\d:\d\d) :(\S+)\s*$')
UTCISH = {'UTC', 'Etc/UTC', 'GMT', 'Etc/GMT'}


def offset(tz, t):
    try:
        d = t.replace(tzinfo=ZoneInfo(tz)).utcoffset()
    except Exception:
        return None
    return f'{d.total_seconds()/3600:+.2f}'.rstrip('0').rstrip('.')


def scan(tf):
    rows = []
    files = sorted(glob.glob(f'{HARM}/att/*.txt') + glob.glob(f'{HARM}/noaa/*.txt')
                   + glob.glob(f'{HARM}/classic/*.txt') + glob.glob(f'{HARM}/utide/*.txt')
                   + glob.glob(f'{HARM}/ticon/*.txt'))
    total = 0
    for f in files:
        L = open(f, encoding='iso-8859-1').read().split('\n')
        lat = lon = None
        for i, l in enumerate(L):
            if l.startswith('# !latitude:'):
                lat = float(l.split(': ')[1]); continue
            if l.startswith('# !longitude:'):
                lon = float(l.split(': ')[1]); continue
            m = MER.match(l)
            if not m:
                continue
            # Achtung: hier KEIN Zuruecksetzen ausserhalb dieses Zweigs -- zwischen
            # der Koordinaten- und der Meridianzeile liegt noch die Namenszeile.
            if lat is not None and lon is not None:
                total += 1
                mer, tz = m.group(1), m.group(2)
                geo = tf.timezone_at(lat=lat, lng=lon)
                # Etc/GMT* heisst "offene See" -- timezonefinder hat dort keine
                # Landzone gefunden. Das sagt nichts ueber die Station aus und
                # wuerde sonst korrekte Eintraege (Anadyr, Banquereau Bank) melden.
                if geo and geo.startswith('Etc/'):
                    geo = None
                deltas = []
                for t in DATES:
                    a, b = offset(tz, t), offset(geo, t) if geo else None
                    if a is None or b is None:
                        continue
                    deltas.append(abs(float(a) - float(b)))
                if geo and tz != geo and deltas and max(deltas) > 0:
                    rows.append(dict(
                        gruppe='A' if tz in UTCISH else 'B',
                        datei=os.path.basename(f), station=L[i - 1].strip(),
                        lat=f'{lat:.4f}', lon=f'{lon:.4f}', meridian=mer,
                        tz_ist=tz, tz_geo=geo,
                        utc_jan_ist=offset(tz, JAN), utc_jan_geo=offset(geo, JAN),
                        utc_jul_ist=offset(tz, JUL), utc_jul_geo=offset(geo, JUL),
                        max_delta_h=f'{max(deltas):g}'))
            lat = lon = None
    return rows, total


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    rows, total = scan(TimezoneFinder())
    rows.sort(key=lambda r: (r['gruppe'], r['datei'], r['station']))
    with open(out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    a = sum(1 for r in rows if r['gruppe'] == 'A')
    b = len(rows) - a
    print(f'{total} Stationen geprueft.')
    print(f'  A (Anzeige in UTC, Konvention) : {a}')
    print(f'  B (fremde Ortszeitzone, Fehler): {b}')
    print(f'-> {out}')


if __name__ == '__main__':
    main()
