#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die gespeicherten Gezeitenseiten von ÇaBaigne.net (Tunesien).

Unter tide_tables/Tunisia/ liegen 17 tunesische Orte mit je zwoelf
Monatsseiten fuer 2026 -- ein voller Jahrgang je Ort.

Diese Quelle hat einen anderen Rang als alle uebrigen im Projekt, und
das muss beim Gebrauch bedacht werden:

  Sie nennt keine Quelle. Alle anderen Tafeln stammen von einem
  benannten hydrographischen Amt (SHN, CHS, SEMAR, CICESE, HIDRONAV,
  SHOA, Chittagong Port Authority). Hier steht nur ein Impressum:
  "Des Clics Nomades/ÇaBaigne.net, tous droits réservés".

  Sie widerspricht sich selbst zur Brauchbarkeit: "Ces données de marées
  ne sont pas adaptées à des fins de navigation."

  Sie trifft nicht ueberall. In Gabes stimmt sie ausgezeichnet mit
  unseren Saetzen ueberein (mittlerer Hub 1.099 m gegen 1.088 und
  1.058 m, RMS 5.9 cm, Zeitversatz +4 Minuten). In Sfax weicht sie
  dagegen stark ab: 0.571 m mittlerer Hub gegen uebereinstimmend 0.902
  und 0.913 m aus der Admiralty NP208 und der XTide-Datenbank von 1997.
  In Bizerte liegt sie 150 Minuten daneben.

Daraus folgt der Gebrauch: **Gegenprobe, nicht Massstab.** Wo sie
abweicht, ist ein zweiter Blick angezeigt; entscheiden darf sie nichts.
Insbesondere wird kein Satz aus einer amtlichen Quelle geloescht, weil
diese Seite ihm widerspricht. Fuer Tunesien haben wir mit NP208 eine
hydrographische Quelle, die hoeher steht.

Die Zeiten sind Ortszeit. Tunesien steht ganzjaehrig auf UTC+1 und hat
seit 2009 keine Sommerzeit.

Usage: python3 py/cabaigne_referenz.py            Uebersicht
       python3 py/cabaigne_referenz.py <ort>      einen Ort zeigen
"""
from __future__ import annotations

import collections
import datetime as dt
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'tide_tables/Tunisia')
TZ = 1                       # ganzjaehrig, keine Sommerzeit

MONAT = {'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5,
         'juin': 6, 'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10,
         'novembre': 11, 'décembre': 12}
TAG = re.compile(r'<h3>[^<]*?(\d{1,2})\s+([a-zéûôA-Z]+)\s+(20\d\d)</h3>')
EREIG = re.compile(r'marée (haute|basse)</span></td>\s*<td><b>(\d{1,2}):(\d{2})'
                   r'</b></td>\s*<td>([\d.]+)\s*m', re.I)

VON = dt.datetime(2026, 7, 1)
BIS = dt.datetime(2026, 8, 1)


def _seite(pfad):
    """-> [(datetime UTC, hoehe_m, 'High'|'Low')]

    Jeder Tag steht als <h3>-Ueberschrift ueber seiner Tabelle. Der
    Abschnitt zwischen zwei Ueberschriften gehoert dem oberen Tag --
    ueber den Textfluss allein waere das nicht zu trennen, weil zwischen
    den Tabellen die Skripte der Kurvenbilder stehen.
    """
    h = open(pfad, encoding='utf-8', errors='replace').read()
    stellen = [(m.start(), int(m.group(1)), MONAT.get(m.group(2).lower()),
                int(m.group(3))) for m in TAG.finditer(h)]
    aus = []
    for k, (pos, tag, mon, jahr) in enumerate(stellen):
        if not mon:
            continue
        ende = stellen[k + 1][0] if k + 1 < len(stellen) else len(h)
        for m in EREIG.finditer(h[pos:ende]):
            try:
                z = dt.datetime(jahr, mon, tag, int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            aus.append((z - dt.timedelta(hours=TZ), float(m.group(4)),
                        'High' if m.group(1).lower() == 'haute' else 'Low'))
    return aus


def _ortsname(pfad):
    n = os.path.basename(pfad)
    n = re.sub(r'\s*_\s*Horaires.*$', '', n)
    n = re.sub(r'^Marée à\s+', '', n)
    return n.strip()


_PUFFER = {}


def stationen():
    """-> [{'code', 'dateien'}] -- Position kommt aus dem Bestand."""
    nach = collections.defaultdict(list)
    for p in sorted(glob.glob(os.path.join(ORDNER, '*.htm'))):
        nach[_ortsname(p)].append(p)
    return [{'code': k, 'dateien': v} for k, v in sorted(nach.items())]


def ereignisse(st, von=None, bis=None):
    aus = []
    for p in st['dateien']:
        if p not in _PUFFER:
            _PUFFER[p] = _seite(p)
        aus += [e for e in _PUFFER[p]
                if (not von or e[0] >= von) and (not bis or e[0] < bis)]
    return sorted(set(aus))


def vorhersage(st):
    return ereignisse(st, VON, BIS)


def jahresreihe(st):
    return [(z, h) for z, h, _a in ereignisse(st)]


def main(argv):
    nur = next((a for a in argv if not a.startswith('--')), None)
    st = stationen()
    if not nur:
        print(f'{len(st)} Orte')
        for s in st:
            j = ereignisse(s)
            tage = len({z.date() for z, _h, _a in j})
            print(f'  {s["code"][:24]:24} {len(s["dateien"]):3} Seiten  '
                  f'{len(j):5} Ereignisse an {tage:3} Tagen')
        return 0
    for s in st:
        if nur.lower() not in s['code'].lower():
            continue
        v = vorhersage(s)
        print(f'{s["code"]}  {len(v)} Ereignisse im Juli')
        for z, h, a in v[:4]:
            print(f'   {z:%Y-%m-%d %H:%M} UTC  {h:5.2f} m  {a}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
