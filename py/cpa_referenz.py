#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Gezeitentafeln der Chittagong Port Authority (Bangladesch).

Die Tafeln liegen unter tide_tables/bangladesh/chattogram/ bereits
geparst als cpa2026.json vor -- acht Stationen am Karnaphuli und vor der
Kueste, voller Jahrgang 2026. Die Zeiten sind BST (UTC+6, keine
Sommerzeit), die Hoehen ueber Chart Datum.

Eine Position steht nicht in der Datei. Sie kommt aus dem Bestand ueber
die Kennung "station_id_context: CPA-<name>", die die daraus gefitteten
Saetze tragen -- eine eindeutige Zuordnung, die kein Namensvergleich
leisten muss.

Zum Karnaphuli gehoert eine Warnung: das ist ein Tidefluss mit vier bis
sechs Metern Hub und starker Flachwasserverzerrung. Selbst die Saetze,
die aus eben diesen Tafeln gefittet wurden, treffen sie nur auf 2.4 bis
4.3 Prozent des Hubs. Wer dort Prozentzahlen wie an einer offenen Kueste
liest, haelt gesunde Saetze fuer krank.

Usage: python3 py/cpa_referenz.py             Uebersicht
       python3 py/cpa_referenz.py <text>      eine Station zeigen
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON = os.path.join(ROOT, 'tide_tables/bangladesh/chattogram/cpa2026.json')
TXT = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
BST = dt.timedelta(hours=6)

VON = dt.datetime(2026, 7, 1)
BIS = dt.datetime(2026, 8, 1)
JAHR = 2026


def _positionen(praefix='CPA-'):
    """Kennung -> (lat, lon, Satzname) aus dem Bestand."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from health_check import MERIDIAN
    l = open(TXT, encoding='iso-8859-1').read().split('\n')
    aus, kontext, lat, lon = {}, None, None, None
    for k, z in enumerate(l):
        if z.startswith('# station_id_context:'):
            kontext = z.split(':', 1)[1].strip()
        elif z.startswith('# !latitude:'):
            lat = float(z.split(':', 1)[1])
        elif z.startswith('# !longitude:'):
            lon = float(z.split(':', 1)[1])
        if (z and not z.startswith('#') and k + 1 < len(l)
                and MERIDIAN.match(l[k + 1])):
            if kontext and kontext.startswith(praefix):
                aus[kontext[len(praefix):]] = (lat, lon, z.strip())
            kontext = None
    return aus


def stationen():
    d = json.load(open(JSON, encoding='utf-8'))
    pos = _positionen()
    aus = []
    for name, werte in sorted(d.items()):
        p = pos.get(name)
        if not p:
            continue
        aus.append({'code': name, 'name': p[2], 'lat': p[0], 'lon': p[1],
                    'werte': werte})
    return aus


def reihe(st, von=None, bis=None):
    ev = []
    for z, h in st['werte'].items():
        try:
            t = dt.datetime.strptime(z, '%Y-%m-%d %H:%M') - BST
        except ValueError:
            continue
        if (von and t < von) or (bis and t >= bis):
            continue
        ev.append((t, float(h)))
    return sorted(set(ev))


def vorhersage(st):
    import dhn_qualitaet
    return dhn_qualitaet.art_bestimmen(reihe(st, VON, BIS))


def jahresreihe(st):
    return reihe(st, dt.datetime(JAHR, 1, 1), dt.datetime(JAHR + 1, 1, 1))


def main(argv):
    nur = next((a for a in argv if not a.startswith('--')), None)
    st = stationen()
    if not nur:
        print(f'{len(st)} Stationen')
        for s in st:
            print(f'  {s["code"]:14} {s["name"][:44]:44} {s["lat"]:8.4f} '
                  f'{s["lon"]:8.4f}  {len(s["werte"]):5} Ereignisse')
        return 0
    for s in st:
        if nur.lower() not in s['code'].lower() and nur.lower() not in s['name'].lower():
            continue
        v = vorhersage(s)
        print(f'{s["name"]}  {s["lat"]:.4f} {s["lon"]:.4f}  {len(v)} im Juli')
        for z, h, a in v[:4]:
            print(f'   {z:%Y-%m-%d %H:%M} UTC  {h:6.2f} m  {a}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
