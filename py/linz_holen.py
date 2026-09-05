#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Holt die Gezeitentafeln von Toitu Te Whenua (LINZ) als Massstab.

Von den 1043 Dublettenhaufen ohne Massstab liegen 34 in Neuseeland, und
fuer keinen davon liegt eine Messreihe auf der Platte. LINZ
veroeffentlicht seine Vorhersagen aber offen als CSV, und zwar nicht nur
fuer die Standardhaefen: Charleston, Deep Cove, Kawhia, Korotiti Bay,
Onehunga, Oamaru, Picton, Pouto Point, Raglan, Sumner Head, Okukari Bay
und North Cape stehen alle darin -- genau Namen von unserer Luecken-
liste.

    https://static.charts.linz.govt.nz/tide-tables/maj-ports/csv/<Ort>%20<Jahr>.csv

Kopfzeile: Kennung, Name, Breite, Laenge. Dritte Zeile "Local Std or
Daylight Time" -- die Zeiten stehen in neuseelaendischer ORTSZEIT MIT
SOMMERZEIT, das muss ueber die Zonenregeln laufen und nicht ueber einen
festen Versatz. Danach je Zeile ein Tag: Tagnummer, Wochentag, Monat,
Jahr und bis zu vier Paare aus Uhrzeit und Hoehe in Metern.

Weil es Vorhersagen sind und keine Messungen, misst der RMS dagegen
echte Guete und kein Staurauschen -- wie bei SHOM und JHOD.

Die Namen werden aus dem eigenen Bestand genommen und einzeln probiert;
was 404 liefert, gibt es dort nicht. Der Makron entscheidet: "Okukari
Bay" gibt es nicht, "Okukari Bay" mit O-Makron schon. Deshalb wird zu
jedem Namen auch eine Makronfassung versucht. Zwischen zwei Abrufen
liegt eine Sekunde, und was einmal geholt ist, wird nicht noch einmal
gefragt.

Usage: python3 py/linz_holen.py [--jahr 2026] [--nur Name]
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                       # noqa: E402

BASIS = ('https://static.charts.linz.govt.nz/tide-tables/maj-ports/csv/')
KOPF = {'User-Agent': 'tidal-corpus/1.0 (harmonic constant verification; '
                      'github.com/oliverk73/tidal)'}
ZIEL = os.path.join(ROOT, 'water_levels', 'NewZealand_LINZ')
PAUSE = 1.0
MAKRON = str.maketrans('aeiou', 'āēīōū')


def fassungen(name):
    """-> Schreibweisen, die es bei LINZ geben koennte."""
    out = [name]
    woerter = name.split()
    for i, w in enumerate(woerter):
        if w and w[0].lower() in 'aeiou':
            neu = list(woerter)
            neu[i] = w[0].translate(MAKRON) + w[1:]
            out.append(' '.join(neu))
    return out


def hole(name, jahr):
    pfad = os.path.join(ZIEL, f'{name} {jahr}.csv')
    if os.path.exists(pfad):
        return pfad, False
    u = BASIS + urllib.parse.quote(f'{name} {jahr}.csv')
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=KOPF),
                                    timeout=45) as r:
            roh = r.read()
    except urllib.error.HTTPError:
        return None, True
    except Exception:
        return None, True
    if len(roh) < 500:
        return None, True
    os.makedirs(ZIEL, exist_ok=True)
    open(pfad, 'wb').write(roh)
    return pfad, True


def main(argv):
    jahr = argv[argv.index('--jahr') + 1] if '--jahr' in argv else '2026'
    nur = argv[argv.index('--nur') + 1] if '--nur' in argv else None
    namen = sorted({r['name'].split(',')[0].strip() for r in load_records()
                    if r['name'].rstrip().endswith('New Zealand')
                    and not r['current']})
    if nur:
        namen = [n for n in namen if nur.lower() in n.lower()]
    print(f'{len(namen)} Ortsnamen aus dem Bestand', file=sys.stderr)
    gefunden = []
    for i, name in enumerate(namen, 1):
        for f in fassungen(name):
            pfad, gefragt = hole(f, jahr)
            if gefragt:
                time.sleep(PAUSE)
            if pfad:
                gefunden.append((name, f, pfad))
                break
        if i % 25 == 0:
            print(f'  {i}/{len(namen)}, {len(gefunden)} gefunden', file=sys.stderr)
    print(f'{len(gefunden)} von {len(namen)} bei LINZ vorhanden', file=sys.stderr)
    for name, f, _p in gefunden:
        print(f'{name}\t{f}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
