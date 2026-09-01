#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut TCDs nach harmonics/binary/ fuer alle Dateien, deren TCD veraltet ist.

Veraltet heisst: TCD fehlt, ist aelter als die Textdatei, oder enthaelt
eine andere Zahl von Saetzen. Die Satzzahl ist die wichtigere Probe --
build_tide_db haengt an eine vorhandene Datei an, statt sie zu ersetzen,
weshalb das Ziel vor jedem Bau geloescht wird.

Usage: python3 py/tcd_bauen.py [--alle] [--pruefen]
       --alle     auch aktuelle TCDs neu bauen
       --pruefen  nur zeigen, was veraltet ist
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import active_files, ROOT, MERIDIAN              # noqa: E402

BINARY = os.path.join(ROOT, 'harmonics/binary')

def saetze(pfad):
    l = open(pfad, encoding='iso-8859-1').read().split('\n')
    return sum(1 for k, x in enumerate(l)
               if x and not x.startswith('#') and k + 1 < len(l)
               and MERIDIAN.match(l[k + 1]))


def tcd_saetze(pfad):
    """Satzzahl aus der TCD -- ueber die Ortsliste von tide -ml."""
    out = subprocess.run(['tide', '-ml'], env=dict(os.environ, HFILE_PATH=pfad),
                         capture_output=True, encoding='iso-8859-1', errors='replace')
    return sum(1 for z in out.stdout.split('\n')
               if z.strip() and not z.startswith('Location list generated'))


def main(argv):
    alle = '--alle' in argv
    nur_pruefen = '--pruefen' in argv
    gebaut, aktuell, fehler, veraltet, leer = 0, 0, 0, 0, []
    for rel in active_files():
        txt = os.path.join(ROOT, rel)
        tcd = os.path.join(BINARY, os.path.basename(rel)[:-4] + '.tcd')
        n_txt = saetze(txt)
        if n_txt == 0:
            # Im Baum liegen auch Textdateien, die keine Harmonics sind
            # (harmonics/att_coordinates_mod.txt ist eine Laenderliste).
            leer.append(os.path.basename(rel))
            continue
        grund = None
        if not os.path.exists(tcd):
            grund = 'fehlt'
        elif os.path.getmtime(tcd) < os.path.getmtime(txt):
            grund = 'aelter als der Text'
        else:
            n_tcd = tcd_saetze(tcd)
            if n_tcd != n_txt:
                grund = f'{n_tcd} statt {n_txt} Saetze'
        if grund is None and not alle:
            aktuell += 1
            continue
        if nur_pruefen:
            print(f'  veraltet  {os.path.basename(rel):46} {grund}')
            veraltet += 1
            continue
        if os.path.exists(tcd):
            os.remove(tcd)
        r = subprocess.run(['build_tide_db', tcd, txt],
                           capture_output=True, encoding='iso-8859-1', errors='replace')
        m = re.search(r'(\d+) records written', r.stdout + r.stderr)
        n = int(m.group(1)) if m else -1
        ok = n == n_txt
        print(f'  {"ok " if ok else "FEHLER"} {os.path.basename(rel):46} '
              f'{n:5} Saetze' + ('' if ok else f'  -- Text hat {n_txt}')
              + (f'   ({grund})' if grund else ''))
        gebaut += 1
        fehler += 0 if ok else 1
    if leer:
        print(f'\nuebersprungen, keine Harmonics: {", ".join(leer)}')
    if nur_pruefen:
        print(f'\n{veraltet} veraltet, {aktuell} aktuell')
    else:
        print(f'\n{gebaut} gebaut, {aktuell} waren aktuell, {fehler} Fehler')
    return 1 if fehler else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
