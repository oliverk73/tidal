#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sammelt die Gezeitenvorhersagen der isländischen Häfen von sjolag.is.

Gefunden über den isländischen IHO-Landesbericht (ARHC, Landhelgisgæslan
verweist auf die Vorhersagen der Vegagerðin; deren alte Adresse
vegagerdin.is/vs/ leitet seit 2026 auf sjolag.is um).

Jede Hafenseite (sjolag.is/hafnir/<id>) enthaelt im Seitenquelltext die
stuendliche Vorhersage fuer rund fuenf Tage: sjavarfoll = astronomische
Gezeit, ahladandi = Windstau, sjavarhaed = Summe. Zeiten in UTC (Island
kennt keine Sommerzeit). Einzelne fuenf Tage reichen fuer keinen Fit; der
Sammler haengt deshalb jeden Lauf an eine Datei je Hafen an:

  tide_tables/iceland_sjolag/<id>.csv   dags,sjavarfoll,ahladandi,sjavarhaed,dags_greiningar
  tide_tables/iceland_sjolag/stationen.json   id -> Name, lat, lon

Bei gleicher Stunde gewinnt der juengste Vorhersagelauf. Laeuft als
User-Timer sjolag-sammler.timer taeglich; nach etwa einem Monat lassen sich
M2/S2/N2/K1/O1 trennen, nach sechs Monaten der volle Satz.

Usage: python3 py/sjolag_sammler.py [--stand]
       --stand  nur zeigen, wie viele Stunden je Hafen schon gesammelt sind
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'tide_tables', 'iceland_sjolag')
BASIS = 'https://sjolag.is'
UA = 'oliver-weather-tides/1.0 (private tide research; oliver.k73@gmail.com)'
FELDER = ['dags', 'sjavarfoll', 'ahladandi', 'sjavarhaed', 'dags_greiningar']


def hole(pfad):
    req = urllib.request.Request(BASIS + pfad, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode('utf-8', 'ignore')


def hafen_ids():
    t = hole('/hafnir')
    return sorted({int(x) for x in re.findall(r'hafnir/(\d+)', t)})


def lesen(text):
    """-> (name, lat, lon, [zeilen]) aus einer Hafenseite."""
    t = text.replace('\\"', '"')
    titel = re.search(r'<title>([^<]*)', t)
    name = titel.group(1).split(' – ')[0].strip() if titel else ''
    ll = re.search(r'"lat":([-\d.]+),"lon":([-\d.]+)', t)
    zeilen = {}
    for m in re.finditer(r'\{"idstod":\d+,"dags_greiningar":"([^"]+)","dags":"([^"]+)",'
                         r'"sjavarfoll":([-\d.]+),"ahladandi":([-\d.]+),"sjavarhaed":([-\d.]+)', t):
        zeilen[m.group(2)] = dict(dags=m.group(2), sjavarfoll=m.group(3), ahladandi=m.group(4),
                                  sjavarhaed=m.group(5), dags_greiningar=m.group(1))
    return name, (float(ll.group(1)) if ll else None), (float(ll.group(2)) if ll else None), list(zeilen.values())


def anhaengen(hid, neu):
    pfad = os.path.join(ZIEL, f'{hid}.csv')
    alt = {}
    if os.path.exists(pfad):
        for z in csv.DictReader(open(pfad, encoding='utf-8')):
            alt[z['dags']] = z
    for z in neu:
        vorher = alt.get(z['dags'])
        if not vorher or z['dags_greiningar'] >= vorher['dags_greiningar']:
            alt[z['dags']] = z
    teil = pfad + '.teil'
    with open(teil, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=FELDER)
        w.writeheader()
        w.writerows(alt[k] for k in sorted(alt))
    os.replace(teil, pfad)
    return len(alt)


def stand():
    stat = json.load(open(os.path.join(ZIEL, 'stationen.json'), encoding='utf-8'))
    for hid, s in sorted(stat.items(), key=lambda p: int(p[0])):
        pfad = os.path.join(ZIEL, f'{hid}.csv')
        z = list(csv.DictReader(open(pfad, encoding='utf-8'))) if os.path.exists(pfad) else []
        spanne = f"{z[0]['dags'][:10]} .. {z[-1]['dags'][:10]}" if z else '-'
        print(f'{hid:>3} {s["name"][:28]:28} {len(z):6} Stunden  {spanne}')


def main(argv):
    os.makedirs(ZIEL, exist_ok=True)
    if '--stand' in argv:
        stand()
        return 0
    pfad_stat = os.path.join(ZIEL, 'stationen.json')
    stat = json.load(open(pfad_stat, encoding='utf-8')) if os.path.exists(pfad_stat) else {}
    print(f'--- {dt.datetime.now():%Y-%m-%d %H:%M}', flush=True)
    fehler = 0
    for hid in hafen_ids():
        try:
            name, lat, lon, zeilen = lesen(hole(f'/hafnir/{hid}'))
        except Exception as e:
            print(f'  {hid}: {e}', flush=True)
            fehler += 1
            continue
        if not zeilen:
            print(f'  {hid} {name}: keine Vorhersage im Quelltext', flush=True)
            fehler += 1
            continue
        stat[str(hid)] = dict(name=name, lat=lat, lon=lon)
        n = anhaengen(hid, zeilen)
        print(f'  {hid:>3} {name[:28]:28} +{len(zeilen):3} -> {n} Stunden', flush=True)
        time.sleep(2.0)
    json.dump(stat, open(pfad_stat, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return 1 if fehler and not stat else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
