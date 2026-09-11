#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erkennt veraltete Zeilen in den Qualitaetstabellen.

Die Qualitaetstabellen (harmonics/help/*qualitaet*.csv) haengen am Namen
des Satzes, nicht an seinem Inhalt. Wird ein Satz neu gerechnet oder
gedreht, bleibt seine alte Messung stehen -- und dubletten_aufraeumen.py
entscheidet womoeglich nach einem Fehler, den der Satz nicht mehr hat.
Zwischen dem 09. und 11.09.2026 ist das viermal passiert (Active Pass mit
84 statt 22 cm, Benodet, Laayoune, Baie de l'Oiseau).

Deshalb fuehrt diese Datei neben jeder Messzeile den Fingerabdruck des
Satzes (health_check.fp, md5 der Konstantenzeilen), wie er zur Messung war:

    harmonics/help/messung_fingerabdruck.csv

Regeln, ohne dass die Messwerkzeuge etwas davon wissen muessen:
  * Zeile neu (noch nicht erfasst)          -> Fingerabdruck von jetzt
  * Messwerte der Zeile haben sich geaendert -> neu gemessen, Fingerabdruck
                                                von jetzt
  * Messwerte gleich, Satz geaendert         -> VERALTET

Veraltete Zeilen verwirft dubletten_aufraeumen.py; nachmessen mit
py/qualitaet_nachmessen.py bzw. dem Werkzeug der Tabelle.

Aufruf: python3 py/messung_fingerabdruck.py      (zeigt veraltete Zeilen)
"""
from __future__ import annotations

import csv
import glob
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
SEITE = os.path.join(HELP, 'messung_fingerabdruck.csv')
FELDER = ('tabelle', 'station', 'reihe', 'jahr', 'datei', 'satz', 'fp', 'zeile')
WERTE = ('n', 'rms_m', 'max_m', 'zeit_min', 'hoehe_off_m', 'hub_m')


def _schluessel(tab, r):
    return (tab, r.get('station', ''), r.get('reihe', ''), r.get('jahr', ''),
            r.get('datei', ''), r.get('satz', ''))


def _zeile(r):
    return hashlib.md5('|'.join(str(r.get(w, '')) for w in WERTE).encode()).hexdigest()[:12]


def stand(schreiben=True, recs=None):
    """-> Menge der veralteten Schluessel; pflegt die Beiblatt-Datei."""
    fp = {(os.path.basename(r['file']), r['name']): r['fp'] for r in (recs or load_records())}
    alt = {}
    if os.path.exists(SEITE):
        for r in csv.DictReader(open(SEITE, encoding='utf-8')):
            alt[tuple(r[f] for f in FELDER[:6])] = (r['fp'], r['zeile'])
    neu, veraltet = {}, set()
    for pfad in sorted(glob.glob(os.path.join(HELP, '*qualitaet*.csv'))):
        tab = os.path.basename(pfad)
        for r in csv.DictReader(open(pfad, encoding='utf-8')):
            if 'satz' not in r:
                continue
            k = _schluessel(tab, r)
            jetzt = fp.get((r.get('datei', ''), r.get('satz', '')))
            if jetzt is None:
                continue                      # Satz geloescht oder umbenannt
            z = _zeile(r)
            if k not in alt or alt[k][1] != z:
                neu[k] = (jetzt, z)           # neu erfasst oder neu gemessen
            else:
                neu[k] = alt[k]
                if alt[k][0] != jetzt:
                    veraltet.add(k)
    if schreiben:
        with open(SEITE + '.neu', 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(FELDER)
            for k, (f, z) in sorted(neu.items()):
                w.writerow(list(k) + [f, z])
        os.replace(SEITE + '.neu', SEITE)
    return veraltet


def main():
    v = stand()
    print(f'{len(v)} veraltete Messzeilen')
    for k in sorted(v):
        print(f'  {k[0][:28]:28} {k[5][:40]:40} [{k[4][:26]}] gegen {k[1][:28]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
