#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loescht die in einer Loeschliste aufgefuehrten Saetze.

Die Liste ist eine CSV mit den Spalten datei, name, fehler_prozent und
begruendung -- so bleibt der Nachweis im Baum, statt im Code zu stehen.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.
Jede Datei wird vorher nach harmonics/backup/ gesichert.

Usage: python3 py/saetze_loeschen.py <liste.csv> [--schreiben]
"""
from __future__ import annotations

import collections
import datetime as dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Eine gemeinsame Definition wie in positions_lock und id_match. Hier
# stand bis zuletzt noch die Handpruefung lines[k+1][:1] in '+-' und
# [3:4] == ':' -- dieselbe Annahme (Vorzeichen, zweistellige Stunde), die
# die 124 Lavergne-Saetze mit "0:00 :Europe/London" jahrelang unsichtbar
# gemacht hat. Sie diente hier nur der Zaehlprobe, haette also eine
# falsche Satzzahl gemeldet.
from health_check import MERIDIAN                                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP = os.path.join(ROOT, 'harmonics/backup')

def liste(pfad):
    """Zu loeschende Saetze aus der CSV."""
    import csv
    with open(pfad, encoding='utf-8') as fh:
        return [(r['datei'], r['name'],
                 f"{r['fehler_prozent']} % Hub -- {r['begruendung']}")
                for r in csv.DictReader(fh)]


def block(lines, i):
    """Grenzen des Satzes, dessen Namenszeile bei i steht.

    Nach oben wird ueber Kommentar- und Leerzeilen gelaufen -- ausser
    beim ERSTEN Satz einer Datei. Ueber ihm stehen keine Kommentare, die
    ihm gehoeren, sondern der Dateikopf: nach dem congen-Vorspann und
    dessen "*END*" folgen zwanzig Zeilen, die das Format erklaeren, und
    die sehen aus wie der Kopf eines Satzes.

    Wird der erste Satz mitsamt diesen Zeilen entfernt, laesst sich die
    Datei nicht mehr uebersetzen: build_tide_db bricht mit "Assertion
    `string[0] == \'#\'\' failed" ab und sagt nicht, was fehlt. So
    geschehen mit harmonics_noaa_censam, als Matamoros als erster Satz
    der Datei geloescht wurde.

    Beim ersten Satz bleibt deshalb alles ueber der Namenszeile stehen.
    Gehoerten ein paar Kommentarzeilen wirklich ihm, bleiben sie als
    Kommentar zurueck -- das stoert niemanden, ein zerstoerter Dateikopf
    schon.
    """
    a = i
    if not _hat_satz_davor(lines, i):
        return a, _ende(lines, i)
    while a > 0 and (lines[a - 1].startswith('#') or not lines[a - 1].strip()):
        a -= 1
    return a, _ende(lines, i)


def _ende(lines, i):
    b = i + 3                                   # Name, Meridian, Z0
    while b < len(lines) and lines[b].strip() and not lines[b].startswith('#'):
        b += 1
    return b


def _hat_satz_davor(lines, i):
    """Steht vor Zeile i schon ein Datensatz in dieser Datei?"""
    for k in range(i):
        z = lines[k]
        if (z and not z.startswith('#') and k + 1 < len(lines)
                and MERIDIAN.match(lines[k + 1])):
            return True
    return False


def main(argv):
    schreiben = '--schreiben' in argv
    rest = [a for a in argv if not a.startswith('--')]
    if not rest:
        print(__doc__.strip().split('Usage:')[-1].strip())
        return 2
    csvpfad = rest[0]
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    kurz = os.path.basename(csvpfad).replace('_loeschen.csv', '')
    proDatei = {}
    for datei, name, warum in liste(csvpfad):
        proDatei.setdefault(datei, []).append((name, warum))

    gesamt, schon, mehrdeutig = 0, [], []
    for datei, faelle in sorted(proDatei.items()):
        pfad = os.path.join(ROOT, datei)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and MERIDIAN.match(lines[k + 1]))
        # Wie oft nennt die Liste denselben Namen in dieser Datei? Steht er
        # dort mehrfach und die Liste fuehrt ihn genauso oft auf, sind alle
        # Vorkommen gemeint -- sonst waere ein Satz nicht zu loeschen, der
        # zweimal mit demselben Namen im selben Bestand steht.
        wieoft = collections.Counter(n for n, _w in faelle)
        erledigt = set()
        raus = []
        for name, warum in faelle:
            treffer = [k for k, l in enumerate(lines) if l.rstrip() == name]
            if len(treffer) > 1 and wieoft[name] == len(treffer):
                if name in erledigt:
                    continue
                erledigt.add(name)
                for t in treffer:
                    a, b = block(lines, t)
                    raus.append((a, b, name, warum))
                continue
            if len(treffer) > 1:
                # Der Name bezeichnet den Satz nicht eindeutig -- in
                # harmonics-2004-06-14_mod steht "Sullivan Bay" zweimal,
                # 52 km auseinander. Hier zu raten waere schlimmer als
                # stehenzulassen, und die Liste soll deswegen nicht die
                # uebrigen Dateien mitreissen.
                mehrdeutig.append((datei, name, len(treffer)))
                continue
            if not treffer:
                # Schon entfernt. Die Liste ist ein dauerhafter Nachweis und
                # waechst mit; ein zweiter Lauf darf daran nicht scheitern.
                schon.append((datei, name))
                continue
            a, b = block(lines, treffer[0])
            raus.append((a, b, name, warum))
        raus.sort(reverse=True)
        if not raus:
            continue
        print(f'\n{datei}  ({vorher} Saetze)')
        for a, b, name, warum in sorted(raus):
            print(f'   -{b - a:3} Zeilen  {name[:46]:46}\n                     {warum}')
        if schreiben:
            shutil.copy2(pfad, os.path.join(
                BACKUP, os.path.basename(datei) + f'.vor_{kurz}_dedup_{stamp}'))
            for a, b, _n, _w in raus:
                del lines[a:b]
            open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(lines))
            nach = sum(1 for k, l in enumerate(lines)
                       if l and not l.startswith('#') and k + 1 < len(lines)
                       and MERIDIAN.match(lines[k + 1]))
            print(f'   geschrieben: {vorher} -> {nach} Saetze '
                  f'(erwartet {vorher - len(raus)})')
            if nach != vorher - len(raus):
                print('   ACHTUNG: Satzzahl passt nicht!')
                return 1
        gesamt += len(raus)
    if mehrdeutig:
        print(f'\n{len(mehrdeutig)} Eintraege uebersprungen -- der Name kommt in '
              f'seiner Datei mehrfach vor und bezeichnet den Satz nicht:')
        for d, n, c in mehrdeutig:
            print(f'   {c}x  {n[:52]:54s} {os.path.basename(d)}')
    if schon:
        print(f'\n{len(schon)} Eintraege der Liste waren bereits entfernt')
    print(f'\n{gesamt} Saetze {"geloescht" if schreiben else "waeren zu loeschen"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
