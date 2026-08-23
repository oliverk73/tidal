#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loescht die von bom_dubletten.py bestaetigten schlechteren Saetze.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.
Jede Datei wird vorher nach harmonics/backup/ gesichert.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP = os.path.join(ROOT, 'harmonics/backup')

# (Datei, zu loeschender Name, Begruendung: RMS weg -> RMS bleibt)
WEG = [
 ('harmonics/noaa/harmonics_noaa_cptt.txt', 'Christmas Island, Kiribati',
  '0.1789 -> 0.0075 m, Kiritimati (Christmas Island), ticon4'),
 ('harmonics/noaa/harmonics_noaa_cptt.txt', 'Burnett Heads, Queensland, Australia',
  '0.1881 -> 0.0101 m, Bundaberg (Burnett Heads), utide_observations'),
 ('harmonics/noaa/harmonics_noaa_cptt.txt', 'Majuro Atoll, Marshall Islands',
  '0.0864 -> 0.0068 m, Majuro, utide_tidetables'),
 ('harmonics/noaa/harmonics_noaa_cptt.txt', 'Green Island, Queensland, Australia',
  '0.1618 -> 0.0432 m, Green Island, 2004_mod'),
 ('harmonics/noaa/harmonics_noaa_cptt.txt', 'Hook Island, Queensland, Australia',
  '0.1793 -> 0.0652 m, Hook Island, 2004_mod'),
 ('harmonics/classic/harmonics-1997-05-25_mod.txt', 'Nathan Reef, Queensland, Australia',
  '0.0481 -> 0.0102 m, Nathan Reef, utide_tidetables'),
 ('harmonics/classic/harmonics-1997-05-25_mod.txt', 'Peart Reef, Queensland, Australia',
  '0.0289 -> 0.0123 m, Peart Reef, utide_tidetables'),
 ('harmonics/classic/harmonics-2004-06-14_mod.txt', 'Sharp Island, Papua New Guinea',
  '0.0842 -> 0.0224 m, Sharp Island, utide_tidetables'),
 ('harmonics/classic/harmonics-2004-06-14_mod.txt',
  'St. Francis Island, South Australia, Australia',
  '0.0713 -> 0.0278 m, St Francis Island, utide_tidetables'),
 ('harmonics/ticon/harmonics_ticon4_worldwide.txt', 'Alotau, Papua New Guinea',
  '0.0248 -> 0.0070 m, Alotau, utide_observations'),
 ('harmonics/ticon/harmonics_ticon4_worldwide.txt',
  'Batemans Bay, New South Wales, Australia',
  '0.0159 -> 0.0055 m, Princess Jetty (Batemans Bay), utide_tidetables'),
 ('harmonics/ticon/harmonics_ticon4_worldwide.txt',
  'Stony Point (Westernport), Victoria, Australia',
  '0.0313 -> 0.0123 m, Stony Point (Westernport), utide_observations'),
]


def block(lines, i):
    """Grenzen des Satzes, dessen Namenszeile bei i steht."""
    a = i
    while a > 0 and (lines[a - 1].startswith('#') or not lines[a - 1].strip()):
        a -= 1
    b = i + 3                                   # Name, Meridian, Z0
    while b < len(lines) and lines[b].strip() and not lines[b].startswith('#'):
        b += 1
    return a, b


def main(argv):
    schreiben = '--schreiben' in argv
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    proDatei = {}
    for datei, name, warum in WEG:
        proDatei.setdefault(datei, []).append((name, warum))

    gesamt = 0
    for datei, faelle in sorted(proDatei.items()):
        pfad = os.path.join(ROOT, datei)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and lines[k + 1][:1] in '+-' and lines[k + 1][3:4] == ':')
        raus = []
        for name, warum in faelle:
            treffer = [k for k, l in enumerate(lines) if l.rstrip() == name]
            if len(treffer) != 1:
                print(f'  ABBRUCH {datei}: "{name}" {len(treffer)}x gefunden')
                return 1
            a, b = block(lines, treffer[0])
            raus.append((a, b, name, warum))
        raus.sort(reverse=True)
        print(f'\n{datei}  ({vorher} Saetze)')
        for a, b, name, warum in sorted(raus):
            print(f'   -{b - a:3} Zeilen  {name:48} {warum}')
        if schreiben:
            shutil.copy2(pfad, os.path.join(
                BACKUP, os.path.basename(datei) + f'.vor_bom_dedup_{stamp}'))
            for a, b, _n, _w in raus:
                del lines[a:b]
            open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(lines))
            nach = sum(1 for k, l in enumerate(lines)
                       if l and not l.startswith('#') and k + 1 < len(lines)
                       and lines[k + 1][:1] in '+-' and lines[k + 1][3:4] == ':')
            print(f'   geschrieben: {vorher} -> {nach} Saetze '
                  f'(erwartet {vorher - len(raus)})')
            if nach != vorher - len(raus):
                print('   ACHTUNG: Satzzahl passt nicht!')
                return 1
        gesamt += len(raus)
    print(f'\n{gesamt} Saetze {"geloescht" if schreiben else "waeren zu loeschen"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
