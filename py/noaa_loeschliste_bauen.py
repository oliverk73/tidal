#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Macht aus dem Probelauf eine Loeschliste im Format von py/saetze_loeschen.py.

Gelesen wird harmonics/help/noaa_guete_probelauf.csv. Uebernommen werden
die Zeilen der gewuenschten Listen -- ohne die, in deren Spalte
entscheidung "behalten" steht; so kannst du einzelne Zeilen in der CSV
herausnehmen, ohne dass hier etwas geaendert werden muss.

Geschrieben wird nur die Liste. Geloescht wird erst mit
py/saetze_loeschen.py <liste> --schreiben, und das erst nach Freigabe.

Usage: python3 py/noaa_loeschliste_bauen.py <liste> [<liste> ...] --aus <datei.csv>
       Listen: neben_A, widerspruch, schlecht
"""
from __future__ import annotations

import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT                                       # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
QUELLE = os.path.join(HELP, 'noaa_guete_probelauf.csv')
NAMEN = {'neben_A': 'loeschen:neben_A', 'widerspruch': 'loeschen:widerspruch',
         'schlecht': 'loeschen:schlecht'}
ORDNER = {'harmonics_noaa_': 'harmonics/noaa/'}


def pfad(datei):
    for kopf, ordner in ORDNER.items():
        if datei.startswith(kopf):
            return ordner + datei
    return datei


def begruendung(z):
    """Der Nachweis, der im Baum stehen bleibt."""
    erst = z['a_zeugen'].split(';')[0].strip()
    m = re.search(r'([\d.]+)km\s+(\d+)%$', erst)
    nah = f"{m.group(2)} % bei {m.group(1)} km" if m else z['abw_pct'] + ' %'
    teile = [f"NOAA-Uebertragung (Table 2) neben dem Klasse-A-Satz "
             f"\"{z['naechster_a']}\" [{z['naechster_a_datei']}], {z['naechster_a_km']} km"]
    if z['liste'] == 'loeschen:neben_A':
        teile.append(f"Kurvenunterschied {nah} -- innerhalb des Grundrauschens zweier guter "
                     f"Saetze in diesem Abstand (Median {z['abw_pct']} %, 95-%-Marke "
                     f"{z['schwelle_pct']} %). Der A-Satz hat gemessene Konstanten, die "
                     f"Uebertragung nur Zeit- und Hubdifferenzen aus dem Buch")
    elif z['liste'] == 'loeschen:widerspruch':
        teile.append(f"Kurvenunterschied {nah}, deutlich ueber dem Grundrauschen "
                     f"(95-%-Marke {z['schwelle_pct']} %). Kein Zeitversatz einer glatten "
                     f"Stunde, also kein Zonenverdacht; die gemessenen Konstanten gelten")
    else:
        teile.append(f"Kurvenunterschied {nah}; {z['a_orte']} Klasse-A-Orte bis 25 km sind "
                     f"sich einig und widersprechen dem Satz alle")
    if z['zeit_min']:
        teile.append(f"Zeitversatz {z['zeit_min']} min, Amplitudenverhaeltnis {z['massstab'] or '-'}")
    if z['schiedsrichter']:
        teile.append(z['schiedsrichter'])
    if z['name_hinweis']:
        teile.append(z['name_hinweis'])
    teile.append('Probelauf py/noaa_guete_probelauf.py, 16.09.2026')
    return '; '.join(teile) + '.'


def main(argv):
    aus = argv[argv.index('--aus') + 1] if '--aus' in argv else None
    listen = {NAMEN[a] for a in argv if a in NAMEN}
    if not listen or not aus:
        print(__doc__)
        return 1
    zeilen = []
    for z in csv.DictReader(open(QUELLE, encoding='utf-8')):
        if z['liste'] not in listen:
            continue
        if (z.get('entscheidung') or '').strip().lower().startswith('behalt'):
            continue
        zeilen.append(dict(datei=pfad(z['datei']), name=z['name'],
                           fehler_prozent=z['abw_pct'], begruendung=begruendung(z)))
    zeilen.sort(key=lambda z: (z['datei'], z['name']))
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
        w.writeheader()
        w.writerows(zeilen)
    print(f'{len(zeilen)} Saetze -> {os.path.relpath(aus, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
