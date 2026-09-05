#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gibt Stromstationen die NP203-Nummer zurueck, die ihr Name verloren hat.

py/build_np203_currents.py vergibt beim Import eindeutige Namen: die
Gebietsueberschrift des Buches plus die Stationsnummer, also "Off Borneo
(NP203 514a) Current". Ein spaeterer Aufraeumschritt hat die Klammer
entfernt -- gut gemeint, denn sie ist haesslich, aber danach hiessen elf
Saetze "Singapore Strait Current", vier "Philippine Islands Current" und
drei "Off Borneo Current".

Das ist kein Schoenheitsfehler. XTide loest Stationen ueber den Namen
auf: von elf gleichnamigen Saetzen ist einer erreichbar und zehn sind es
nicht. Sie stehen in der TCD und niemand kommt an sie heran. Und die
Strom-Saetze fallen durch jede Dublettenpruefung, weil pegel_dubletten
und dubletten_aufraeumen sie ausschliessen -- gemeldet hat es deshalb
nie jemand.

Wiederhergestellt wird ausschliesslich aus harmonics/help/positions_locked.csv,
also aus dem Namen, den der Import selbst vergeben hat. Nichts wird
erfunden. Angefasst werden nur Saetze, deren heutiger Name mehrfach im
Bestand vorkommt: wo die Klammer nur "(NP203)" ohne Nummer enthielt und
der Name eindeutig ist, war das Entfernen richtig und bleibt so.

Zugeordnet wird ueber Datei UND Position, nicht ueber den Namen -- der
ist ja gerade nicht eindeutig, das ist der ganze Punkt.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.

Usage: python3 py/stroemungsnamen_nummern.py [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, MERIDIAN, ROOT                # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
SPERRE = os.path.join(HELP, 'positions_locked.csv')
NUMMER = re.compile(r'\s*\((NP\d{3}\s+\S+?)\)')
GENAU = 1e-4


def kandidaten(recs):
    """-> [(Satz, alter Name, neuer Name)] fuer jeden betroffenen Satz."""
    haeufig = collections.Counter(r['name'] for r in recs)
    out = []
    for z in csv.DictReader(open(SPERRE, encoding='utf-8')):
        orig = z.get('orig_name') or ''
        if not NUMMER.search(orig):
            continue
        if NUMMER.sub('', orig).strip() != z['name']:
            continue
        if haeufig.get(z['name'], 0) < 2:
            continue
        try:
            la, lo = float(z['lat']), float(z['lon'])
        except (TypeError, ValueError):
            continue
        treffer = [r for r in recs
                   if r['file'] == z['file'] and r['name'] == z['name']
                   and r['lat'] is not None
                   and abs(r['lat'] - la) < GENAU and abs(r['lon'] - lo) < GENAU]
        if len(treffer) != 1:
            print(f'   uebersprungen ({len(treffer)} Treffer): {z["name"]} '
                  f'{la} {lo}')
            continue
        out.append((treffer[0], z['name'], orig))
    return out


def main(argv):
    schreiben = '--schreiben' in argv
    recs = load_records()
    faelle = kandidaten(recs)
    vorhanden = collections.Counter(r['name'] for r in recs)
    proDatei = collections.defaultdict(list)
    for r, alt, neu in faelle:
        if vorhanden.get(neu, 0):
            print(f'   KOLLISION, ausgelassen: {neu}')
            continue
        proDatei[r['file']].append((r['line'], alt, neu))

    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    heute = dt.datetime.now().strftime('%Y%m%d')
    gesamt = 0
    for datei, eintraege in sorted(proDatei.items()):
        voll = os.path.join(ROOT, datei)
        lines = open(voll, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and MERIDIAN.match(lines[k + 1]))
        print(f'\n{datei}  ({vorher} Saetze)')
        for zeile, alt, neu in sorted(eintraege, reverse=True):
            i = zeile - 1
            if i >= len(lines) or lines[i].rstrip() != alt:
                print(f'   UEBERSPRUNGEN: Zeile {zeile} ist nicht {alt!r}')
                continue
            print(f'   {alt[:44]:46} -> {neu}')
            if schreiben:
                lines[i] = neu
                lines[i:i] = [f'# note: {heute} Stationsnummer im Namen '
                              f'wiederhergestellt (vorher "{alt}"),',
                              '# note: -- der Name war sonst mehrfach vergeben '
                              'und der Satz fuer XTide nicht erreichbar.']
            gesamt += 1
        if schreiben:
            shutil.copy2(voll, os.path.join(
                BACKUP, os.path.basename(datei) + f'.vor_nummern_{stamp}'))
            open(voll, 'w', encoding='iso-8859-1').write('\n'.join(lines))
            nachher = sum(1 for k, l in enumerate(lines)
                          if l and not l.startswith('#') and k + 1 < len(lines)
                          and MERIDIAN.match(lines[k + 1]))
            print(f'   geschrieben: {vorher} -> {nachher} Saetze')
            if nachher != vorher:
                print('   ACHTUNG: Satzzahl veraendert!')
                return 1
    print(f'\n{gesamt} Namen {"wiederhergestellt" if schreiben else "waeren wiederherzustellen"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
