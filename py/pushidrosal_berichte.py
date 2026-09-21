#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Stundentafeln aus den taeglichen Pushidrosal-Lageberichten.

tide_tables/indonesia/pushidrosal2023/*.pdf sind keine Jahrbuchseiten, sondern
die taeglichen Berichte "Analisa Cuaca di Perairan Indonesia dan Prediksi
Pasut di Fasilitas Labuh TNI AL" (ab Mai 2024, geladen mit py/pushidrosal_laden.py). Jeder enthaelt fuer 41
Marinehaefen die komplette Monatstafel: je Tag 24 Stundenwerte in Metern mit
einer Nachkommastelle, Ortszeit mit angegebener Zone. Anders als das Jahrbuch
2023 (py/pushidrosal_ocr.py) haben sie eine Textebene -- kein OCR noetig.

Zwei Formate:
  bis 29.04.  "1) Sabang GMT+7." / "APRIL/APRIL 2026" / Zeilen ohne Marken
  ab 30.04.   dazu "1. SABANG", die Pegelposition in Grad/Minuten/Sekunden,
              gesperrter Monat "M E I/ M AY 2026" und "*" an den Wendepunkten

Eine Tagzeile zaehlt nur mit genau 24 Werten und gleicher Tagesnummer links
und rechts. Derselbe Tag steht in bis zu 31 Berichten; weichen zwei Fassungen
voneinander ab, wird das gezaehlt und die haeufigste genommen.

Ergebnis: tide_tables/indonesia/pushidrosal_berichte_2026.json
  {station: {"tz": 7, "lat": .., "lon": .., "tage": {"2026-05-01": [24 Werte]}},
   ...}  -- Spalte k (1..24) ist die Stunde k Ortszeit.

Usage: python3 py/pushidrosal_berichte.py
"""
from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'tide_tables/indonesia/pushidrosal2023')
AUS = os.path.join(ROOT, 'tide_tables/indonesia/pushidrosal_berichte_2026.json')

MONATE = {'JANUARI': 1, 'FEBRUARI': 2, 'PEBRUARI': 2, 'MARET': 3, 'APRIL': 4, 'MEI': 5,
          'JUNI': 6, 'JULI': 7, 'AGUSTUS': 8, 'SEPTEMBER': 9, 'OKTOBER': 10,
          'NOVEMBER': 11, 'NOPEMBER': 11, 'DESEMBER': 12}

STATION = re.compile(r'^\s*(\d{1,2})\)\s+(.+?)\s+GMT\s*\+\s*(\d{1,2})', re.M)
MONAT = re.compile(r'((?:[A-Z]\s?){3,9})\s*/\s*(?:[A-Z]\s?){3,9}\s*(20\d\d)')
POSITION = re.compile(r'(\d{1,3})\s*°\s*(\d{1,2})\s*\'\s*([\d.]+)\s*"\s*(U/N|S/S)\s*-\s*'
                      r'(\d{1,3})\s*°\s*(\d{1,2})\s*\'\s*([\d.]+)\s*"\s*(T/E|B/W)')
ZAHL = re.compile(r'^-?\d+,\d$')

# Druckfehler in der Halbkugel. Pulau Nipa steht in allen Berichten mit
# "01 08' 39.66" S/S"; die Marineinsel liegt aber in der Singapurstrasse auf
# NORDbreite -- GeoNames 1.14722 N 103.65694 E, genau diese Ziffern.
# Mit Suedbreite laege sie vor der Kueste von Jambi.
BREITE_NORD = {'Pulau Nipa'}

# Positionen, die in den Berichten falsch stehen -- ersetzt durch den Hafen.
# Pantoloan: in allen Berichten 00 49' 15.65" S 119 48' 40.57" E, ein Punkt
# mitten in der Bucht von Palu, 12 km SSW des Hafens und 1.4 km vor dem
# Westufer. Der Marinestuetzpunkt ist der Hafen an der Ostseite: OSM
# "Pelabuhan Pantoloan" -0.71123 119.85604; BMKG-4000000011 steht 0.11 km daneben.
POSITION_BERICHTIGT = {'Pantoloan (Palu)': (-0.71123, 119.85604)}

# Schreibweisen desselben Hafens ueber die Jahre ("Tanjung Balaikarimun" bis
# 09/2025, danach "Tanjung Balai karimun"). Zusammengefuehrt wird ueber den
# Namen ohne Leerzeichen und Grossschreibung.
NAME = {'tanjungbalaikarimun': 'Tanjung Balai Karimun'}


def einheitlich(name):
    return NAME.get(re.sub(r'\s+', '', name.lower()), name)


def monatsabstand(a, b):
    return abs((a[0] * 12 + a[1]) - (b[0] * 12 + b[1]))


def tafelmonat(kopf, bericht):
    """(Jahr, Monat) der Tafel, am Berichtsdatum geprueft.

    Im Tafelkopf ist das Jahr gelegentlich vertippt (Dabo Singkep stand so
    im November 2026, Tanjung Wangi im Januar 2024 -- beides ausserhalb der
    Berichte). Eine Tafel gehoert zum Monat ihres Berichts oder zum
    benachbarten; passt der Kopf dazu nicht, wird das Jahr des Berichts
    genommen. Passt auch das nicht, gilt die Tafel als unklar.
    """
    for kandidat in (kopf, (bericht[0], kopf[1]), (bericht[0] - 1, kopf[1]), (bericht[0] + 1, kopf[1])):
        if monatsabstand(kandidat, bericht) <= 1:
            return kandidat
    return None


def text(pfad):
    return subprocess.run(['pdftotext', '-layout', pfad, '-'], capture_output=True,
                          text=True, errors='replace').stdout


def tagzeile(zeile):
    """-> (tag, [24 Werte]) oder None."""
    t = zeile.replace('*', ' ').split()
    if len(t) != 26 or not (t[0].isdigit() and t[-1] == t[0]):
        return None
    werte = t[1:-1]
    if not all(ZAHL.match(w) for w in werte):
        return None
    return int(t[0]), [float(w.replace(',', '.')) for w in werte]


def position(block):
    m = POSITION.search(block)
    if not m:
        return None
    la = int(m.group(1)) + int(m.group(2)) / 60 + float(m.group(3)) / 3600
    lo = int(m.group(5)) + int(m.group(6)) / 60 + float(m.group(7)) / 3600
    return (la if m.group(4) == 'U/N' else -la), (lo if m.group(8) == 'T/E' else -lo)


def lesen():
    fassungen = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    kopf = {}
    unklar = 0
    verlegt = set()
    umdatiert = set()
    for pfad in sorted(glob.glob(os.path.join(ORDNER, '*.pdf'))):
        t = text(pfad)
        # Hochladezeit steht als Unix-Zeit im Dateinamen: 1776843682_... = 22.04.2026
        hoch = dt.datetime.fromtimestamp(int(os.path.basename(pfad).split('_')[0]), dt.timezone.utc)
        bericht = (hoch.year, hoch.month)
        treffer = list(STATION.finditer(t))
        for i, m in enumerate(treffer):
            block = t[m.end(): treffer[i + 1].start() if i + 1 < len(treffer) else len(t)]
            name, tz = einheitlich(' '.join(m.group(2).split())), int(m.group(3))
            k = kopf.setdefault(name, {'tz': tz, 'lat': None, 'lon': None, 'nr': int(m.group(1))})
            if k['tz'] != tz:
                print(f'  ACHTUNG {name}: Zone {k["tz"]} und {tz}')
            pos = position(block)
            if pos:
                la = abs(pos[0]) if name in BREITE_NORD else pos[0]
                # Dateien laufen nach Hochladezeit: die juengste Position gilt.
                if k['lat'] is not None and (abs(la - k['lat']) > 0.001 or abs(pos[1] - k['lon']) > 0.001):
                    verlegt.add((name, k['lat'], k['lon'], round(la, 5), round(pos[1], 5)))
                k['lat'], k['lon'] = round(la, 5), round(pos[1], 5)
            monat = None
            for zeile in block.split('\n'):
                mm = MONAT.search(zeile)
                if mm:
                    wort = mm.group(1).replace(' ', '')
                    monat = None
                    if wort in MONATE:
                        kopf_m = (int(mm.group(2)), MONATE[wort])
                        monat = tafelmonat(kopf_m, bericht)
                        if monat != kopf_m:
                            umdatiert.add((name, kopf_m, monat, os.path.basename(pfad)[:10]))
                    continue
                z = tagzeile(zeile)
                if not z:
                    continue
                if monat is None:
                    unklar += 1
                    continue
                try:
                    datum = dt.date(monat[0], monat[1], z[0]).isoformat()
                except ValueError:
                    unklar += 1
                    continue
                fassungen[name][datum][tuple(z[1])] += 1
    for name, (la, lo) in POSITION_BERICHTIGT.items():
        if name in kopf:
            kopf[name]['lat'], kopf[name]['lon'] = la, lo
    for v in sorted(verlegt):
        print(f'  ACHTUNG {v[0]}: Position {v[1]} {v[2]} und {v[3]} {v[4]} (juengste gilt)')
    for v in sorted(umdatiert, key=str):
        print(f'  Tafelkopf {v[0]}: {v[1][1]:02d}/{v[1][0]} im Bericht {v[3]} -> '
              + (f'{v[2][1]:02d}/{v[2][0]}' if v[2] else 'verworfen'))
    return fassungen, kopf, unklar


def main():
    fassungen, kopf, unklar = lesen()
    out, widerspruch = {}, 0
    for name, tage in fassungen.items():
        t = {}
        for datum, c in sorted(tage.items()):
            if len(c) > 1:
                widerspruch += 1
            t[datum] = list(c.most_common(1)[0][0])
        out[name] = dict(kopf[name], tage=t)
    json.dump(out, open(AUS, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(f'{len(out)} Stationen -> {os.path.relpath(AUS, ROOT)}')
    print(f'Tagzeilen ohne erkennbaren Monat: {unklar};  Tage mit abweichenden Fassungen: {widerspruch}')
    for name, s in sorted(out.items(), key=lambda x: x[1]['nr']):
        d = sorted(s['tage'])
        print(f"  {s['nr']:2d} {name:34s} GMT+{s['tz']}  {len(d):3d} Tage {d[0]}..{d[-1]}  "
              f"{'pos ' + format(s['lat'], '.4f') + ' ' + format(s['lon'], '.4f') if s['lat'] is not None else 'ohne Position'}")


if __name__ == '__main__':
    sys.exit(main())
