#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sammelt die amtlichen Hoch- und Niedrigwasser Kuwaits von met.gov.kw.

Die Seite https://www.met.gov.kw/Forecasts/marine.php enthaelt im Seitenquelltext
die Scheitel (Zeit, Hoehe in m ueber Kartennull, Hoch/Niedrig) fuer rund fuenf
Tage voraus, je Pegel ein Feld:
  stn1DataArr = Shuwaikh     stn2DataArr = Shuaiba
Zeiten in Kuwait-Ortszeit (UTC+3, keine Sommerzeit), Hoehen auf 0,1 m.
Fuenf Tage reichen fuer keinen Fit; der Sammler haengt jeden Lauf an eine Datei
je Pegel an (Scheitelfit nach etwa sechs Monaten, wie bei sjolag.is):

  tide_tables/kuwait_met/<pegel>.csv   zeit_lokal,zeit_utc,hoehe,typ,abruf,wartung

Bei gleicher Zeit gewinnt der juengste Abruf. 'wartung' = 1, wenn die Seite den
Pegel als in Wartung markiert (class tide-maint-mode; Shuaiba seit 28.10.2026).

Usage: python3 py/kuwait_sammler.py [--stand]
       --stand  nur zeigen, wie viele Scheitel je Pegel schon gesammelt sind
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'tide_tables', 'kuwait_met')
URL = 'https://www.met.gov.kw/Forecasts/marine.php'
UA = 'oliver-weather-tides/1.0 (private tide research; oliver.k73@gmail.com)'
FELDER = ['zeit_lokal', 'zeit_utc', 'hoehe', 'typ', 'abruf', 'wartung']
PEGEL = {'stn1': 'shuwaikh', 'stn2': 'shuaiba'}


def hole(versuche=4):
    for k in range(versuche):
        try:
            req = urllib.request.Request(URL, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode('utf-8', 'ignore')
        except Exception:
            if k == versuche - 1:
                raise
            time.sleep(20 * (k + 1))


def lesen(t):
    """-> {stn: ([zeilen], wartung)}"""
    abruf = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    aus = {}
    for stn in PEGEL:
        m = re.search(stn + r'DataArr\s*=\s*\[(.*?)\];', t, re.S)
        if not m:
            continue
        zeilen = []
        for z in re.finditer(r'new Date\("(\d{4}-\d\d-\d\d \d\d:\d\d)"\)\s*,\s*value:\s*([-\d.]+)\s*,\s*type:\s*"&(u|d)arr;', m.group(1)):
            lokal = dt.datetime.strptime(z.group(1), '%Y-%m-%d %H:%M')
            zeilen.append(dict(zeit_lokal=z.group(1), zeit_utc=(lokal - dt.timedelta(hours=3)).strftime('%Y-%m-%d %H:%M'),
                               hoehe=z.group(2), typ='HW' if z.group(3) == 'u' else 'NW', abruf=abruf))
        label = re.search(r"value='%s'[^<]*>(?:<span class=\"([^\"]*)\")?" % stn, t)
        wartung = 1 if label and 'maint' in (label.group(1) or '') else 0
        for z in zeilen:
            z['wartung'] = wartung
        aus[stn] = (zeilen, wartung)
    return aus


def anhaengen(name, neu):
    pfad = os.path.join(ZIEL, f'{name}.csv')
    alt = {}
    if os.path.exists(pfad):
        for z in csv.DictReader(open(pfad, encoding='utf-8')):
            alt[z['zeit_lokal']] = z
    for z in neu:
        vorher = alt.get(z['zeit_lokal'])
        if not vorher or z['abruf'] >= vorher['abruf']:
            alt[z['zeit_lokal']] = z
    teil = pfad + '.teil'
    with open(teil, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=FELDER)
        w.writeheader()
        w.writerows(alt[k] for k in sorted(alt))
    os.replace(teil, pfad)
    return len(alt)


def stand():
    for name in PEGEL.values():
        pfad = os.path.join(ZIEL, f'{name}.csv')
        z = list(csv.DictReader(open(pfad, encoding='utf-8'))) if os.path.exists(pfad) else []
        spanne = f"{z[0]['zeit_lokal'][:10]} .. {z[-1]['zeit_lokal'][:10]}" if z else '-'
        print(f'{name:10} {len(z):5} Scheitel  {spanne}')


def main(argv):
    os.makedirs(ZIEL, exist_ok=True)
    if '--stand' in argv:
        stand()
        return 0
    print(f'--- {dt.datetime.now():%Y-%m-%d %H:%M}', flush=True)
    daten = lesen(hole())
    if not any(z for z, _ in daten.values()):
        print('  keine Scheitel im Quelltext', flush=True)
        return 1
    for stn, (zeilen, wartung) in daten.items():
        n = anhaengen(PEGEL[stn], zeilen)
        print(f'  {PEGEL[stn]:10} +{len(zeilen):2} -> {n} Scheitel' + ('  (Wartung)' if wartung else ''), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
