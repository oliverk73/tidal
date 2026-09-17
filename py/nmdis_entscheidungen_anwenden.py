#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traegt die Entscheidungen aus der NMDIS-Namenswerkstatt in den Bestand ein.

Die Seite (py/nmdis_seite_bauen.py) schreibt je Station ein Dokument in die
Artifact-Datenbank; Claude liest sie dort aus und legt sie als CSV hier ab:

  harmonics/help/nmdis_entscheidungen.csv
  code,voller_name,lat,lon

Dieses Skript setzt sie um: Name in der Satzzeile und im Kommentarkopf,
Position in den !latitude/!longitude-Zeilen, dazu ein Vermerk mit Herkunft
und altem Wert. Der alte Name bleibt als Kommentar erhalten -- die
Guetetabellen sind auf Namen verschluesselt, deshalb danach
py/umbenennungen_nachziehen.py laufen lassen.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.

Usage: python3 py/nmdis_entscheidungen_anwenden.py [--quelle <csv>] [--schreiben]
       --quelle  nur diese Entscheidungen (z.B. die seit dem letzten Eintragen neuen)
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pegel_dubletten                                              # noqa: E402
import sicher_schreiben                                             # noqa: E402
from health_check import ROOT, load_records                         # noqa: E402

QUELLE = os.path.join(ROOT, 'harmonics/help/nmdis_entscheidungen.csv')
LOG = os.path.join(ROOT, 'harmonics/help/nmdis_umbenannt.csv')


def main(argv):
    schreiben = '--schreiben' in argv
    quelle = argv[argv.index('--quelle') + 1] if '--quelle' in argv else QUELLE
    entsch = {z['code']: z for z in csv.DictReader(open(quelle, encoding='utf-8'))}
    verm = pegel_dubletten.vermerke()
    recs = [r for r in load_records() if not r['current']]
    nach_code = {}
    for r in recs:
        m = re.search(r'# nmdis_site: (T\d+)', verm.get((r['file'], r['line']), ''))
        if m:
            nach_code[m.group(1)] = r

    protokoll = []
    nach_datei = {}
    for code, z in sorted(entsch.items()):
        r = nach_code.get(code)
        if not r:
            print(f'  {code}: kein Satz im Bestand')
            continue
        neu_name = re.sub(r'\s+', ' ', (z.get('voller_name') or '')).strip()
        lat = (z.get('lat') or '').strip()
        lon = (z.get('lon') or '').strip()
        if not neu_name and not lat:
            continue
        bestaetigt = (not lat) and neu_name == r['name']
        pfad = os.path.join(ROOT, r['file'])
        if pfad not in nach_datei:
            nach_datei[pfad] = open(pfad, encoding='iso-8859-1').read().split('\n')
        zeilen = nach_datei[pfad]
        # Satzzeile suchen (Name kann durch eine fruehere Aenderung verschoben sein)
        treffer = [k for k, l in enumerate(zeilen) if l == r['name']]
        if len(treffer) != 1:
            print(f'  {code}: Satzzeile nicht eindeutig ({len(treffer)}) -- uebersprungen')
            continue
        k = treffer[0]
        j = k - 1
        while j >= 0 and zeilen[j].startswith('#'):
            j -= 1
        block = list(range(j + 1, k))
        alt_pos = (r['lat'], r['lon'])
        teile = []
        if neu_name and neu_name != r['name']:
            zeilen[k] = neu_name
            for b in block:
                if zeilen[b].strip() == f'# {r["name"]}':
                    zeilen[b] = f'# {neu_name}'
            teile.append(f'Name "{r["name"]}" -> "{neu_name}"')
        if lat and lon:
            for b in block:
                if zeilen[b].startswith('# !latitude:'):
                    zeilen[b] = f'# !latitude: {float(lat):.4f}'
                elif zeilen[b].startswith('# !longitude:'):
                    zeilen[b] = f'# !longitude: {float(lon):.4f}'
            teile.append(f'Position {alt_pos[0]:.4f}/{alt_pos[1]:.4f} -> {float(lat):.4f}/{float(lon):.4f}')
        if not teile and bestaetigt:
            # Name in der Werkstatt ausdruecklich bestaetigt: nichts zu aendern,
            # aber vermerken -- sonst steht der Satz beim naechsten Neubau der
            # Werkstatt wieder als "unberuehrt" in der Liste.
            einf = [b for b in block if zeilen[b].startswith('# !units:')]
            if einf and not any('Name bestaetigt' in zeilen[b] for b in block):
                zeilen.insert(einf[0], f'# note: {dt.date.today():%Y%m%d} NMDIS-Namenswerkstatt: Name bestaetigt (Oliver).')
                protokoll.append(dict(code=code, datei=os.path.basename(r['file']), alt=r['name'],
                                      neu=r['name'], alt_lat='', alt_lon='', neu_lat='', neu_lon=''))
            continue
        if not teile:
            continue
        notiz = (f'# note: {dt.date.today():%Y%m%d} NMDIS-Namenswerkstatt (Oliver): ' + '; '.join(teile) + '.')
        einf = [b for b in block if zeilen[b].startswith('# !units:')]
        if einf:
            zeilen.insert(einf[0], notiz)
        protokoll.append(dict(code=code, datei=os.path.basename(r['file']), alt=r['name'],
                              neu=neu_name or r['name'],
                              alt_lat=f'{alt_pos[0]:.4f}', alt_lon=f'{alt_pos[1]:.4f}',
                              neu_lat=lat, neu_lon=lon))
        print(f'  {code} {"; ".join(teile)}')

    print(f'\n{len(protokoll)} Saetze betroffen in {len(nach_datei)} Dateien')
    if not schreiben:
        print('(nur Probe; mit --schreiben wird geaendert)')
        return 0
    for pfad, zeilen in nach_datei.items():
        sicher_schreiben.schreiben(pfad, '\n'.join(zeilen))
        print('geschrieben:', os.path.relpath(pfad, ROOT))
    neu = not os.path.exists(LOG)
    with open(LOG, 'a', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['code', 'datei', 'alt', 'neu', 'alt_lat', 'alt_lon',
                                           'neu_lat', 'neu_lon'])
        if neu:
            w.writeheader()
        w.writerows(protokoll)
    print('Protokoll:', os.path.relpath(LOG, ROOT))
    print('Danach: python3 py/umbenennungen_nachziehen.py --schreiben')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
