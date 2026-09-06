#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Setzt die von Hand vergebenen Namen der NP203-Stromstationen.

Gelesen wird die Spalte "name_neu" aus
harmonics/help/stroemungsnamen_vorschlag.csv. Die Liste entsteht mit
py/stroemungsnamen_overpass.py und schlaegt je Station bis zu drei
Kandidaten vor; entschieden hat sie ein Mensch, und nur die Spalte
name_neu wird gelesen -- der Kandidat daneben dient dem Nachweis, nicht
der Auswahl.

Zugeordnet wird ueber die Stationsnummer np203_no aus dem Kopfkommentar,
nicht ueber den Namen: der ist ja gerade das, was sich aendert.

Im Satz bleibt stehen, woher der Name kommt -- alter Name, das OSM-
Merkmal mit seinem Abstand und der Hafen, ueber den NP203 selbst auf das
Gebiet verweist ("The numbers used in Part IIIa are the first three
digits of the port numbers in the same area"). Wer spaeter fragt, warum
eine Stromstation "Teluk Sandakan" heisst, findet dort beide Belege:
OSM 1.3 km und Buchhafen 0.4 km.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.

Usage: python3 py/stroemungsnamen_setzen.py [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sicher_schreiben                                             # noqa: E402
import stroemungsnamen_overpass as so                               # noqa: E402
from health_check import load_records, MERIDIAN, ROOT               # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
QUELLE = os.path.join(HELP, 'stroemungsnamen_vorschlag.csv')
LOG = os.path.join(HELP, 'stroemungsnamen_gesetzt.csv')


def main(argv):
    schreiben = '--schreiben' in argv
    info = so.kopfdaten()
    recs = {(r['file'], r['line']): r for r in load_records()}
    strom = {v['np203_no']: (k, recs[k]) for k, v in info.items()
             if 'np203_no' in v and k in recs}

    namen, beleg = {}, {}
    for z in csv.DictReader(open(QUELLE, encoding='utf-8')):
        n = (z.get('name_neu') or '').strip()
        if not n:
            continue
        no = z['np203_no']
        if no in namen and namen[no] != n:
            print(f'   WIDERSPRUCH bei {no}: {namen[no]!r} und {n!r}')
            return 1
        namen[no] = n
        if no not in beleg or (z['km'] and float(z['km'] or 99) <
                               float(beleg[no][1] or 99)):
            beleg[no] = (z['kandidat'], z['km'], z['buchhafen'], z['buchhafen_km'])

    vorhanden = collections.Counter(r['name'] for r in recs.values())
    proDatei = collections.defaultdict(list)
    for no, neu in namen.items():
        if no not in strom:
            print(f'   Station {no} nicht im Bestand')
            continue
        (datei, zeile), r = strom[no]
        if r['name'] == neu:
            continue
        if vorhanden.get(neu, 0):
            print(f'   KOLLISION, ausgelassen: {neu}')
            continue
        proDatei[datei].append((zeile, r['name'], neu, beleg.get(no, ('', '', '', ''))))

    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    heute = dt.datetime.now().strftime('%Y%m%d')
    gesetzt = []
    for datei, eintraege in sorted(proDatei.items()):
        voll = os.path.join(ROOT, datei)
        lines = open(voll, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and MERIDIAN.match(lines[k + 1]))
        print(f'\n{datei}  ({vorher} Saetze)')
        for zeile, alt, neu, (kand, kkm, hafen, hkm) in sorted(eintraege, reverse=True):
            i = zeile - 1
            if i >= len(lines) or lines[i].rstrip() != alt:
                print(f'   UEBERSPRUNGEN: Zeile {zeile} ist nicht {alt!r}')
                continue
            print(f'   {alt[:44]:46} -> {neu}')
            gesetzt.append(dict(datum=heute, np203_no='', name_alt=alt, name_neu=neu,
                                osm=kand, osm_km=kkm, buchhafen=hafen,
                                buchhafen_km=hkm))
            if schreiben:
                lines[i] = neu
                note = [f'# note: {heute} Name vergeben (vorher "{alt}"),']
                if kand:
                    note.append(f'# note: -- OSM "{kand}" in {kkm} km'
                                + (f', NP203-Hafen "{hafen}" in {hkm} km.'
                                   if hafen else '.'))
                elif hafen:
                    note.append(f'# note: -- NP203-Hafen "{hafen}" in {hkm} km.')
                note.append('# note: -- siehe harmonics/help/stroemungsnamen_gesetzt.csv')
                lines[i:i] = note
            gesamt = 0
        if schreiben:
            shutil.copy2(voll, os.path.join(
                BACKUP, os.path.basename(datei) + f'.vor_stromnamen_{stamp}'))
            sicher_schreiben.schreiben(voll, '\n'.join(lines))
            nachher = sum(1 for k, l in enumerate(lines)
                          if l and not l.startswith('#') and k + 1 < len(lines)
                          and MERIDIAN.match(lines[k + 1]))
            print(f'   geschrieben: {vorher} -> {nachher} Saetze')
            if nachher != vorher:
                print('   ACHTUNG: Satzzahl veraendert!')
                return 1
    if schreiben and gesetzt:
        neu_datei = not os.path.exists(LOG)
        with open(LOG, 'a', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(gesetzt[0].keys()))
            if neu_datei:
                w.writeheader()
            w.writerows(gesetzt)
        print(f'\n-> {LOG}')
    print(f'\n{len(gesetzt)} Namen {"gesetzt" if schreiben else "waeren zu setzen"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
