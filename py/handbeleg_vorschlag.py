#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schlaegt Namenspaare fuer den Handbeleg vor -- und urteilt nicht.

py/dubletten_aufraeumen.py verlangt fuer eine Loeschung den Beleg, dass
es derselbe Pegel ist: gleicher voller Name, eine passende Altlage, oder
eine reine Rechnung neben einem gemessenen Satz. Wo nur ein Namenszusatz
dazwischensteht, faellt die Gruppe durch -- gemessen am 05.09.2026 sind
das 228 Saetze, die an der Tafel deutlich schlechter sind und trotzdem
stehen bleiben. Der Zusatz ist meist eine Bucht, ein Fluss oder ein
generisches Wort: "Belan Point, Menai Strait" neben "Fort Belan" auf
derselben Position, "Bach Long Vi Island" neben "Bach Long Vi".

Automatisch aufloesen laesst sich das nicht. Derselbe Zusatz, der hier
ueberfluessig ist, unterscheidet anderswo zwei Pegel -- "Elsfleth
(Weser)" und "Elsfleth Ohrt (Hunte)" liegen an zwei Fluessen. Deshalb
entscheidet ein Mensch, einmal je Paar.

Geschrieben wird ein Vorschlag mit denselben Spalten, die der Handbeleg
liest (name_a, name_b, begruendung), dahinter die Belege zum Nachsehen:
Abstand, Kurvenabweichung, Zeitversatz, die gemessenen RMS beider Saetze
und die Dateien. Oben steht, was am ehesten derselbe Pegel ist -- nach
Abstand, dann Kurve, dann Namensueberlappung. Wer die Liste durchgeht,
streicht die Zeilen, die er nicht verantwortet, und benennt die Datei in
dubletten_handbeleg.csv um.

Aufgenommen werden nur Gruppen, in denen der Beleg auch etwas bewirkt:
wo eine Messung vorliegt und die Regel bei unterstelltem Beleg wirklich
loeschen wuerde. Bach Long Vi und Mys Menaputsy stehen deshalb NICHT
drin -- dort fehlt der Massstab, und ein Beleg allein loescht nichts.

Usage: python3 py/handbeleg_vorschlag.py
"""
from __future__ import annotations

import csv
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_aufraeumen as da                                 # noqa: E402
from health_check import load_records, km, curve_diff             # noqa: E402
from transfer_zonen import zeitversatz                            # noqa: E402

ZIEL = os.path.join(da.HELP, 'dubletten_handbeleg_vorschlag.csv')


def worte(n):
    n = n.rsplit(', ', 1)[0].lower()
    n = ''.join(c for c in unicodedata.normalize('NFD', n)
                if unicodedata.category(c) != 'Mn')
    return {t for t in re.split(r"[^a-z0-9']+", n) if t}


def ueberlappung(a, b):
    """Anteil gemeinsamer Woerter am kleineren Namen."""
    wa, wb = worte(a), worte(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def main(argv):
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    echt = da.haufen_gruppen
    # Einmal mit unterstelltem Beleg rechnen lassen: nur so steht fest,
    # in welchen Gruppen der Beleg ueberhaupt etwas aendert.
    def unterstellt(rr):
        out = echt(rr)
        for _n, _m, meta in out:
            if meta['beleg'] is None:
                meta['beleg'] = 'Hand (unterstellt)'
        return out
    da.haufen_gruppen = unterstellt
    stumm = open(os.devnull, 'w')
    echt_out, sys.stdout = sys.stdout, stumm
    try:
        da.main(['--haufen', '--csv'])
    finally:
        sys.stdout = echt_out
    da.haufen_gruppen = echt

    wirksam = set()
    for r in csv.DictReader(open(os.path.join(da.HELP, 'dubletten_loeschen.csv'),
                                 encoding='utf-8')):
        wirksam.add((r['datei'], r['name']))

    zeilen = []
    for _name, menge, meta in echt(recs):
        if meta['beleg'] is not None:
            continue
        if not any((r['file'], r['name']) in wirksam for r in menge):
            continue
        namen = sorted({r['name'] for r in menge})
        satz = {r['name']: r for r in menge}
        for i in range(len(namen)):
            for j in range(i + 1, len(namen)):
                a, b = satz[namen[i]], satz[namen[j]]
                d = km(a, b)
                v, gu = zeitversatz(a, b)
                zeilen.append(dict(
                    name_a=namen[i], name_b=namen[j], begruendung='',
                    km=f'{d:.2f}', kurve_prozent=f'{curve_diff(a, b)[1] * 100:.1f}',
                    dt_h=f'{v:+.2f}' if v is not None else '', guete=f'{gu:.3f}',
                    namensueberlappung=f'{ueberlappung(namen[i], namen[j]):.2f}',
                    spur=meta['spur'], haufen=meta['nr'],
                    datei_a=os.path.basename(a['file']),
                    datei_b=os.path.basename(b['file'])))
    zeilen.sort(key=lambda z: (float(z['km']), float(z['kurve_prozent']),
                               -float(z['namensueberlappung'])))
    with open(ZIEL, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader()
        w.writerows(zeilen)
    gleich = sum(1 for z in zeilen if float(z['km']) < 0.05)
    print(f'{len(zeilen)} Namenspaare aus {len({z["haufen"] for z in zeilen})} '
          f'Haufen, davon {gleich} auf derselben Position')
    print(f'-> {ZIEL}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
