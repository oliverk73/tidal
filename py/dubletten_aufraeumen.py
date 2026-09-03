#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raeumt Saetze weg, die denselben Pegel doppelt fuehren.

Das Ziel des Bestandes ist ein Satz je Pegel, und zwar der genaueste.
Doppelt gefuehrt wird trotzdem viel: 1851 Namen kommen mehrfach vor.
Nicht alles davon ist eine Dublette -- "Singapore Strait Current"
steht elfmal fuer elf verschiedene Messpunkte in derselben Strasse,
und zwei gleichnamige Saetze mit verschiedenen Kurven sind ein
Widerspruch, kein Ueberfluss.

Angefasst wird deshalb nur die eindeutige Klasse: gleicher Name,
unter einem Kilometer auseinander, Kurven unter zehn Prozent
verschieden. Dort ist es derselbe Pegel, und der zweite Satz sagt
nichts, was der erste nicht schon sagt.

Wer bleibt, entscheidet die Herkunft:

  9  eigene uTide-Anpassungen an Tafeln oder Messreihen, Aemter
  8  TICON-4 (gemessene Konstanten aus GESLA)
  7  aktuelle XTide-Verteilung (NOS-Konstanten), Literatur
  6  ATT Part III (veroeffentlichte Harmonische)
  5  alte XTide-Verteilungen 1997/2004, Lavergne
  4  ATT Part II (Transfer), Table V
  3  NOAA Table-2-Transfer
  2  Modell (FES2022)

Bei gleichem Rang zaehlt zuerst das Datum: ein Satz mit Z0 ueber
null rechnet auf Kartennull, einer mit Z0 = 0 auf Mittelwasser. Der
Unterschied ist an Aalesund zu sehen -- TICON-4 fuehrt den Pegel auf
MSL mit Z0 = 0.0000, unsere Kartverket-Anpassung auf CD mit
Z0 = 1.2901. Danach entscheidet die Zahl der Konstituenten (TICON-4
gibt 42, unsere Anpassungen 66) und zuletzt das Einlesedatum.

Uebersprungen wird eine Gruppe, wenn der Sieger KEIN Kartennull hat
und ein Verlierer eins: dann wuerde das Aufraeumen Information
kosten, statt welche zu sparen.

Usage: python3 py/dubletten_aufraeumen.py [--csv] [--schreiben]
       --schreiben schreibt die Loeschliste; geloescht wird mit
       py/saetze_loeschen.py
"""
from __future__ import annotations

import collections
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, curve_diff, active_files, ROOT, MERIDIAN  # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
NAH_KM = 1.0
GLEICH = 0.10


def kopfdaten():
    """-> {(datei, zeile): (quelle, datum, z0, importdatum)} fuer alle Saetze."""
    out = {}
    for path in active_files():
        lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
        src = dat = imp = None
        for k, line in enumerate(lines):
            if line.startswith('# source:'):
                src = line.split(':', 1)[1].strip()
            elif line.startswith('# datum:'):
                dat = line.split(':', 1)[1].strip()
            elif line.startswith('# date_imported:'):
                imp = line.split(':', 1)[1].strip()
            elif (line and not line.startswith('#') and k + 1 < len(lines)
                  and MERIDIAN.match(lines[k + 1])):
                z0 = 0.0
                try:
                    z0 = abs(float(lines[k + 2].split()[0]))
                except (IndexError, ValueError):
                    pass
                out[(path, k + 1)] = (src or '', dat or '', z0, imp or '')
                src = dat = imp = None
    return out


def rang(datei, quelle):
    """-> Herkunftsrang, gross ist besser."""
    d = os.path.basename(datei)
    if d.startswith('harmonics_utide') or d in ('harmonics_puertos_spain.txt',
                                                'harmonics_mascaret_peniche.txt'):
        return 9
    if d == 'harmonics_ticon4_worldwide.txt':
        return 8
    if d.startswith('harmonics-dwf-2025') or d in ('harmonics_literature.txt',
                                                   'harmonics_noaa_refs.txt'):
        return 7
    if d.startswith('harmonics_att'):
        # Part III druckt die Harmonischen selbst, Part II nur Differenzen.
        return 6 if 'Harmonic Constants' in quelle or 'Part III' in quelle else 4
    if d.startswith('harmonics-'):
        return 5                       # 1997, 2004, Lavergne, alte dwf
    if d == 'harmonics_fes2022.txt':
        return 2
    return 3                           # NOAA-Table-2-Transfers und Verwandte


def main(argv):
    kopf = kopfdaten()
    recs = [r for r in load_records() if r['lat'] is not None]
    nach_name = collections.defaultdict(list)
    for r in recs:
        nach_name[r['name']].append(r)

    weg, gehalten, uebersprungen = [], [], []
    for name, gruppe in sorted(nach_name.items()):
        tide = [r for r in gruppe if not r['current']]
        strom = [r for r in gruppe if r['current']]
        for menge in (tide, strom):
            if len(menge) < 2:
                continue
            if max(km(a, b) for i, a in enumerate(menge) for b in menge[i + 1:]) >= NAH_KM:
                continue
            if max(curve_diff(a, b)[1] for i, a in enumerate(menge)
                   for b in menge[i + 1:]) >= GLEICH:
                continue
            bewertet = []
            for r in menge:
                q, dat, z0, imp = kopf.get((r['file'], r['line']), ('', '', 0.0, ''))
                bewertet.append((rang(r['file'], q), 1 if z0 > 0 else 0,
                                 len(r['amp']), imp, r, dat, z0))
            bewertet.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3]))
            sieger = bewertet[0]
            verlierer = bewertet[1:]
            if sieger[1] == 0 and any(v[1] == 1 for v in verlierer):
                # Der Sieger rechnet auf Mittelwasser, ein Verlierer auf
                # Kartennull: hier wuerde das Aufraeumen etwas kosten.
                uebersprungen.append((name, sieger, verlierer))
                continue
            gehalten.append(sieger)
            for v in verlierer:
                weg.append((v, sieger))

    print(f'{len(weg)} Saetze koennen weg, {len(gehalten)} bleiben als Sieger stehen, '
          f'{len(uebersprungen)} Gruppen uebersprungen (Datum)')
    verlust = collections.Counter(os.path.basename(v[4]['file']) for v, _s in weg)
    sieg = collections.Counter(os.path.basename(s[4]['file']) for s in gehalten)
    print(f'\n{"Datei":42} {"bleibt":>7} {"geht":>7}')
    for d in sorted(set(verlust) | set(sieg), key=lambda x: -(verlust[x] + sieg[x])):
        print(f'{d[:42]:42} {sieg[d]:7} {verlust[d]:7}')
    if uebersprungen:
        print('\nuebersprungen, weil der Sieger kein Kartennull hat:')
        for name, s, vs in uebersprungen[:15]:
            print(f'  {name[:44]:44} bleibt {os.path.basename(s[4]["file"])[:24]:24} '
                  f'(Z0 {s[6]:.2f}) gegen ' +
                  ', '.join(f'{os.path.basename(v[4]["file"])[:20]} (Z0 {v[6]:.2f})' for v in vs))
        if len(uebersprungen) > 15:
            print(f'  ... und {len(uebersprungen) - 15} weitere')

    if '--csv' in argv or '--schreiben' in argv:
        p = os.path.join(HELP, 'dubletten_loeschen.csv')
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
            for v, s in weg:
                rel = curve_diff(v[4], s[4])[1] * 100
                w.writerow([v[4]['file'], v[4]['name'], f'{rel:.1f}',
                            f'Dublette: {km(v[4], s[4]) * 1000:.0f} m von "{s[4]["name"]}" '
                            f'({os.path.basename(s[4]["file"])}), Kurve {rel:.0f} % gleich. '
                            f'Dort Herkunftsrang {s[0]} gegen {v[0]}, Z0 {s[6]:.2f} gegen '
                            f'{v[6]:.2f} m, {s[2]} gegen {v[2]} Konstituenten.'])
        print(f'\n-> {p}')
        if '--schreiben' in argv:
            print('   jetzt: python3 py/saetze_loeschen.py harmonics/help/'
                  'dubletten_loeschen.csv --schreiben')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
