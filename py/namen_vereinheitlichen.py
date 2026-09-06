#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gibt zwei Saetzen desselben Pegels denselben Namen.

Ein Haufen wird nur beurteilt, wenn belegt ist, dass es derselbe Pegel
ist -- und der einfachste Beleg ist der gleiche volle Name. Wo zwei
Quellen denselben Pegel verschieden benannt haben ("Chatham Point" und
"Chatham Pt.", "Bandar Victoria (Labuan)" und "Labuan (Victoria
Harbour)"), bleibt beides stehen, obwohl einer messbar schlechter ist.

Statt den Beleg in einer Nebenliste zu fuehren, wird er hier in die
Daten geschrieben: beide Saetze bekommen den gemeinsamen Namen. Danach
greift der vorhandene Namensbeleg von allein, die Messung entscheidet,
und der ueberlebende Satz traegt den guten Namen -- beim Loeschen geht
also kein Name mehr verloren.

Der Beleg wird damit ein anderer: nicht mehr "zwei Quellen haben
unabhaengig denselben Namen vergeben", sondern "ein Mensch hat
entschieden". Deshalb wandert der alte Name als Kommentar in den Satz
selbst, nicht nur in positions_lock -- wer spaeter fragt, warum zwei
Saetze ploetzlich gleich heissen, findet die Antwort dort.

Gelesen wird die Spalte "Neuer gemeinsamer Name" aus
harmonics/help/dubletten_handbeleg_vorschlag.csv (py/handbeleg_vorschlag.py).
Der Vermerk im Satz zeigt aber nicht dorthin, sondern auf
harmonics/help/namen_vereinheitlicht.csv: die Vorschlagsliste wird nach
jeder Runde neu gerechnet und enthaelt das erledigte Paar dann nicht
mehr -- ein Nachweis, der ins Leere zeigt, ist keiner.
Ein Satz wird ueber Name UND Datei angesprochen: "Audierne, France"
steht zweimal im Bestand, und nur einer der beiden ist gemeint. Reicht
auch das nicht, entscheidet die Haufennummer: "L'Ile-d'Anticosti,
Quebec, Canada" steht dreimal in derselben Datei -- drei Pegel auf einer
Insel, 74 und 142 km auseinander --, und nur einer gehoert zum Haufen.

Die Guetetabellen (harmonics/help/*qualitaet*.csv) sind auf den Namen
verschluesselt. Wird ein Satz umbenannt, findet dubletten_aufraeumen
seine Messungen nicht mehr und haelt ihn fuer unvermessen -- er waere
dann weder Massstab noch loeschbar. --tabellen schreibt die Namen dort
nach; das gehoert unmittelbar hinter --schreiben, und beides zusammen
ersetzt keinen neuen Guetelauf, sondern haelt nur den vorhandenen gueltig.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.

Usage: python3 py/namen_vereinheitlichen.py [liste.csv] [--schreiben] [--tabellen]
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sicher_schreiben                                             # noqa: E402
from health_check import load_records, MERIDIAN, ROOT                # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
QUELLE = os.path.join(HELP, 'dubletten_handbeleg_vorschlag.csv')
SPALTE = 'Neuer gemeinsamer Name'


def faelle(pfad):
    """-> [(alter Name, Dateibasis, neuer Name)] aus der Liste."""
    out = []
    for r in csv.DictReader(open(pfad, encoding='utf-8')):
        neu = (r.get(SPALTE) or '').strip()
        if not neu:
            continue
        for seite in ('a', 'b'):
            alt = r[f'name_{seite}'].strip()
            if alt != neu:
                out.append((alt, r[f'datei_{seite}'].strip(), neu,
                            r.get('haufen', '')))
    return out


def haufenmitglieder():
    """-> {(Haufennummer, Name, Dateibasis): Zeile} aus pegel_dubletten.csv."""
    pfad = os.path.join(HELP, 'pegel_dubletten.csv')
    if not os.path.exists(pfad):
        return {}
    out = {}
    for r in csv.DictReader(open(pfad, encoding='utf-8')):
        out[(r['haufen'], r['name'], os.path.basename(r['datei']))] = int(r['zeile'])
    return out


def tabellen(pfad, schreiben):
    """Schreibt die neuen Namen in die Guetetabellen nach."""
    import glob
    karte = {(alt, basis): neu for alt, basis, neu, _h in faelle(pfad)}
    gesamt = 0
    for csvpfad in sorted(glob.glob(os.path.join(HELP, '*qualitaet*.csv'))):
        rows = list(csv.DictReader(open(csvpfad, encoding='utf-8')))
        if not rows or 'satz' not in rows[0]:
            continue
        n = 0
        for r in rows:
            neu = karte.get((r.get('satz', ''), r.get('datei', '')))
            if neu:
                r['satz'] = neu
                n += 1
        if n and schreiben:
            with open(csvpfad, 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        if n:
            print(f'   {os.path.basename(csvpfad):40} {n:5} Zeilen')
        gesamt += n
    print(f'{gesamt} Tabellenzeilen {"nachgezogen" if schreiben else "waeren nachzuziehen"}')
    return 0


def main(argv):
    schreiben = '--schreiben' in argv
    rest = [a for a in argv if not a.startswith('--')]
    pfad = rest[0] if rest else QUELLE
    if '--tabellen' in argv:
        rest = [a for a in argv if not a.startswith('--')]
        return tabellen(rest[0] if rest else QUELLE, schreiben)
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    heute = dt.datetime.now().strftime('%Y%m%d')

    recs = load_records()
    nach = {}
    for r in recs:
        nach.setdefault((r['name'], os.path.basename(r['file'])), []).append(r)

    mitglied = haufenmitglieder()
    proDatei, fehlt, mehrdeutig = {}, [], []
    for alt, basis, neu, haufen in faelle(pfad):
        treffer = nach.get((alt, basis), [])
        if not treffer:
            fehlt.append((alt, basis))
            continue
        if len(treffer) > 1:
            zeile = mitglied.get((haufen, alt, basis))
            treffer = [x for x in treffer if x['line'] == zeile]
            if len(treffer) != 1:
                mehrdeutig.append((alt, basis, len(nach[(alt, basis)])))
                continue
        r = treffer[0]
        proDatei.setdefault(r['file'], []).append((r['line'], alt, neu))

    gesamt = 0
    for datei, eintraege in sorted(proDatei.items()):
        voll = os.path.join(ROOT, datei)
        lines = open(voll, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and MERIDIAN.match(lines[k + 1]))
        print(f'\n{datei}')
        # Von hinten nach vorn, damit die eingefuegten Kommentarzeilen die
        # noch offenen Zeilennummern nicht verschieben.
        for zeile, alt, neu in sorted(eintraege, reverse=True):
            i = zeile - 1
            if i >= len(lines) or lines[i].rstrip() != alt:
                print(f'   UEBERSPRUNGEN: Zeile {zeile} ist nicht {alt!r}')
                continue
            print(f'   {alt[:50]:52}\n       -> {neu}')
            if schreiben:
                lines[i] = neu
                lines[i:i] = [f'# note: {heute} Name vereinheitlicht, vorher '
                              f'"{alt}"',
                              '# note: -- selber Pegel, siehe '
                              'harmonics/help/namen_vereinheitlicht.csv']
            gesamt += 1
        if schreiben:
            shutil.copy2(voll, os.path.join(
                BACKUP, os.path.basename(datei) + f'.vor_namen_{stamp}'))
            sicher_schreiben.schreiben(voll, '\n'.join(lines))
            nachher = sum(1 for k, l in enumerate(lines)
                          if l and not l.startswith('#') and k + 1 < len(lines)
                          and MERIDIAN.match(lines[k + 1]))
            print(f'   geschrieben: {vorher} -> {nachher} Saetze')
            if nachher != vorher:
                print('   ACHTUNG: Satzzahl veraendert!')
                return 1
    for alt, basis in fehlt:
        print(f'\nnicht gefunden: {alt!r} in {basis}')
    for alt, basis, n in mehrdeutig:
        print(f'\n{n}x vorhanden, nicht eindeutig: {alt!r} in {basis}')
    print(f'\n{gesamt} Namen {"geaendert" if schreiben else "waeren zu aendern"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
