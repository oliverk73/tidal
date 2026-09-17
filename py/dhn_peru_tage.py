#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Holt DHN-Peru-Gezeiten (HW/LW) tageweise fuer beliebige Zeitraeume.

py/download_dhn_peru.py bekommt aus pdf-tabla-marea/<HAFEN> nur den laufenden
Monat; faellt der Monatslauf aus (August 2026: der Cron zeigte noch auf den
alten Pfad ~/py/), fehlt der Monat fuer immer. Die Kartenseite der DHN
(www.dhn.mil.pe/app/mareas/) laedt ihre Hafenkaestchen aber aus

    https://www.dhn.mil.pe/app/mareas/res.php?f=<JJJJ-MM-TT>&p=<Hafen>

und das nimmt jedes Datum an (2025 geht, 2027 ist leer). Die Antwort nennt
den Tag und den folgenden mit Uhrzeit (Ortszeit UTC-5) und Hoehe in cm --
dieselben Werte wie die PDF-Tafel (Callao 1./15.07.2026 geprueft).

Ablage: tide_tables/peru/tage/<hafen>.csv  datum,zeit,hoehe_cm  (zusammengefuehrt,
ohne Dubletten). Hoeflich: eine Anfrage je Sekunde, ehrlicher User-Agent.

Usage: python3 py/dhn_peru_tage.py --von 2026-08-01 --bis 2026-08-31 [--hafen Callao]
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'tide_tables', 'peru', 'tage')
URL = 'https://www.dhn.mil.pe/app/mareas/res.php'
UA = 'oliver-weather-tides/1.0 (private tide research; oliver.k73@gmail.com)'
HAEFEN = ['Ancon', 'Atico', 'Bayovar', 'Cabo Blanco', 'Caleta Grau', 'Callao', 'Cerro Azul', 'Chala',
          'Chancay', 'Chimbote', 'Eten', 'Huacho', 'Huarmey', 'Ilo', 'Lobitos', 'Lobos de Afuera',
          'Malabrigo', 'Matarani', 'Melchorita', 'Paita', 'Pisco', 'Salaverry', 'San Juan', 'Supe',
          'Talara', 'Zorritos']


def tag_holen(hafen, datum):
    q = urllib.parse.urlencode({'f': datum.isoformat(), 'p': hafen})
    req = urllib.request.Request(f'{URL}?{q}', headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode('utf-8', 'ignore')
    t = re.sub(r'<style.*?</style>', ' ', t, flags=re.S)
    t = ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', t)).split())
    out = []
    for block in re.finditer(r'(\d{4}-\d\d-\d\d) Hora Altura ((?:\d\d:\d\d:\d\d -?\d+ cm ?)+)', t):
        for zeit, cm in re.findall(r'(\d\d:\d\d):\d\d (-?\d+) cm', block.group(2)):
            out.append((block.group(1), zeit, int(cm)))
    return out


def main(argv):
    von = dt.date.fromisoformat(argv[argv.index('--von') + 1])
    bis = dt.date.fromisoformat(argv[argv.index('--bis') + 1])
    haefen = [argv[argv.index('--hafen') + 1]] if '--hafen' in argv else HAEFEN
    os.makedirs(ZIEL, exist_ok=True)
    for hafen in haefen:
        pfad = os.path.join(ZIEL, hafen.lower().replace(' ', '_') + '.csv')
        daten = set()
        if os.path.exists(pfad):
            daten = {(z['datum'], z['zeit'], int(z['hoehe_cm'])) for z in csv.DictReader(open(pfad))}
        vorher = len(daten)
        d = von
        leer = 0
        while d <= bis:
            try:
                neu = tag_holen(hafen, d)
            except Exception as e:
                print(f'  {hafen} {d}: {e}', flush=True)
                neu = []
                time.sleep(5)
            if not neu:
                leer += 1
            daten.update(neu)
            d += dt.timedelta(days=2)         # jede Antwort enthaelt Tag und Folgetag
            time.sleep(1.0)
        teil = pfad + '.teil'
        with open(teil, 'w', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['datum', 'zeit', 'hoehe_cm'])
            w.writerows(sorted(daten))
        os.replace(teil, pfad)
        tage = {x[0] for x in daten if von.isoformat() <= x[0] <= bis.isoformat()}
        print(f'  {hafen:16} +{len(daten) - vorher:4} Werte, {len(tage)} Tage im Zeitraum, {leer} leere Antworten',
              flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
