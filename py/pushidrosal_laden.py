#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laedt die Pushidrosal-Lageberichte "Prakiraan Cuaca dan Pasut Indonesia".

Die Seite www.pushidrosal.id/layanan/cuaca listet sie ueber einen
DataTables-Endpunkt (/cms/pasut/get, 804 Berichte seit Mai 2024, Stand
21.09.2026). Jeder Bericht enthaelt fuer 41 Marinehaefen die KOMPLETTE
Stundentafel des laufenden Monats -- ein Bericht je Monat genuegt also.
Genommen wird der, dessen Datum am naechsten am 15. liegt; Berichte vom
Monatswechsel koennten sonst die falsche Tafel tragen.

Vorhandene Dateien werden nicht noch einmal geladen. Zwischen zwei
Downloads 2 s Pause.

Ziel:  tide_tables/indonesia/pushidrosal2023/<datei>.pdf   (liest py/pushidrosal_berichte.py)
Liste: tide_tables/indonesia/pushidrosal_liste.json

Usage: python3 py/pushidrosal_laden.py            zeigen, was fehlt
       python3 py/pushidrosal_laden.py --laden    fehlende Monate laden
"""
from __future__ import annotations

import datetime as dt
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'tide_tables/indonesia/pushidrosal2023')
LISTE = os.path.join(ROOT, 'tide_tables/indonesia/pushidrosal_liste.json')
BASIS = 'https://www.pushidrosal.id'
UA = 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120'


def oeffner():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.open(urllib.request.Request(BASIS + '/layanan/cuaca', headers={'User-Agent': UA}), timeout=60).read()
    return op


def liste(op):
    """Alle Berichte ueber den DataTables-Endpunkt (er verlangt die vollen Spaltenparameter)."""
    alle, start = [], 0
    while True:
        p = {'draw': '1', 'start': str(start), 'length': '10', 'search[value]': '',
             'search[regex]': 'false', '_': '1'}
        for i, c in enumerate(['no', 'judul', 'created', 'hits']):
            p.update({f'columns[{i}][data]': c, f'columns[{i}][name]': '',
                      f'columns[{i}][searchable]': 'true', f'columns[{i}][orderable]': 'true',
                      f'columns[{i}][search][value]': '', f'columns[{i}][search][regex]': 'false'})
        r = urllib.request.Request(BASIS + '/cms/pasut/get?' + urllib.parse.urlencode(p), headers={
            'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest', 'Referer': BASIS + '/layanan/cuaca'})
        d = json.load(op.open(r, timeout=60))
        alle += [{'datum': x['created'], 'titel': re.sub(r'<[^>]+>', '', x['judul']).strip(),
                  'datei': x['file']} for x in d['data']]
        start += 10
        if start >= d['recordsTotal'] or not d['data']:
            return alle
        time.sleep(0.5)


def je_monat(berichte):
    """Monat -> Bericht mit dem Datum am naechsten am 15."""
    out = {}
    for b in berichte:
        d = dt.date.fromisoformat(b['datum'])
        m = d.strftime('%Y-%m')
        if m not in out or abs(d.day - 15) < abs(dt.date.fromisoformat(out[m]['datum']).day - 15):
            out[m] = b
    return out


def main(argv):
    op = oeffner()
    berichte = liste(op)
    json.dump(berichte, open(LISTE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    wahl = je_monat(berichte)
    da = set(os.listdir(ZIEL)) if os.path.isdir(ZIEL) else set()
    # Monate, fuer die schon irgendein Bericht vorliegt, brauchen keinen weiteren
    vorhanden = {b['datum'][:7] for b in berichte if b['datei'] in da}
    fehlt = [(m, b) for m, b in sorted(wahl.items()) if m not in vorhanden]
    print(f'{len(berichte)} Berichte {berichte[-1]["datum"]}..{berichte[0]["datum"]}, '
          f'{len(wahl)} Monate, {len(wahl) - len(fehlt)} schon vorhanden, {len(fehlt)} fehlen')
    for m, b in fehlt:
        print(f'  {m}  {b["datum"]}  {b["titel"][:60]}  {b["datei"]}')
    if '--laden' not in argv:
        return 0
    os.makedirs(ZIEL, exist_ok=True)
    for m, b in fehlt:
        r = urllib.request.Request(f'{BASIS}/cms/pasut/download/pasut/{b["datei"]}',
                                   headers={'User-Agent': UA, 'Referer': BASIS + '/layanan/cuaca'})
        daten = op.open(r, timeout=180).read()
        if not daten.startswith(b'%PDF'):
            print(f'  {m}: kein PDF ({len(daten)} Bytes) -- uebersprungen')
            continue
        tmp = os.path.join(ZIEL, b['datei'] + '.tmp')
        open(tmp, 'wb').write(daten)
        os.replace(tmp, os.path.join(ZIEL, b['datei']))
        print(f'  {m}: {len(daten) / 1e6:.1f} MB')
        time.sleep(2)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
