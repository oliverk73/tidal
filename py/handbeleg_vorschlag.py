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
import difflib
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_aufraeumen as da                                 # noqa: E402
from health_check import load_records, km, curve_diff             # noqa: E402
from transfer_zonen import zeitversatz                            # noqa: E402

ZIEL = os.path.join(da.HELP, 'dubletten_handbeleg_vorschlag.csv')
SPALTE = 'Neuer gemeinsamer Name'


def bisherige():
    """-> {(name_a, name_b): gemeinsamer Name} aus einer vorhandenen Liste.

    Die Liste wird nach jeder Regelaenderung neu erzeugt, und dabei
    duerfen die von Hand eingetragenen Namen nicht verlorengehen -- sie
    sind das eigentliche Urteil, alles andere ist nachrechenbar.
    """
    if not os.path.exists(ZIEL):
        return {}
    out = {}
    for r in csv.DictReader(open(ZIEL, encoding='utf-8')):
        v = (r.get(SPALTE) or '').strip()
        if v:
            out[frozenset((r['name_a'], r['name_b']))] = v
    return out


def worte(n):
    n = n.rsplit(', ', 1)[0].lower()
    n = ''.join(c for c in unicodedata.normalize('NFD', n)
                if unicodedata.category(c) != 'Mn')
    return {t for t in re.split(r"[^a-z0-9']+", n) if t}


def ueberlappung(a, b):
    """Wie aehnlich sind zwei Namen? 0 bis 1.

    Der einfache Wortvergleich reicht nicht. "George Town, Penang,
    Malaysia" und "Pinang (Bandar Raya Georgetown), Malaysia" sind
    derselbe Pegel, haben aber KEIN gemeinsames Wort: einmal steht eine
    Wortgrenze mitten in Georgetown, und Penang und Pinang sind zwei
    Umschriften desselben Namens. Nach dem alten Mass war das Paar 0.00
    aehnlich und stand damit ganz unten in der Liste -- deshalb hat es
    Oliver nie zu Gesicht bekommen.

    Zusaetzlich wird deshalb ohne Wortgrenzen verglichen (der eine Name
    steckt zusammengezogen im anderen) und mit Unschaerfe (penang ~
    pinang). Genommen wird der bessere der beiden Werte, damit die
    Aenderung nichts verschlechtert.
    """
    wa, wb = worte(a), worte(b)
    if not wa or not wb:
        return 0.0
    einfach = len(wa & wb) / min(len(wa), len(wb))
    ca, cb = ''.join(sorted(wa)), ''.join(sorted(wb))
    if ''.join(wa) in ''.join(wb) or ''.join(wb) in ''.join(wa):
        return 1.0
    lang = [w for w in wa if len(w) >= 4]
    if not lang:
        return einfach
    treffer = sum(1 for w in lang
                  if w in ''.join(wb)
                  or difflib.get_close_matches(w, list(wb), 1, 0.8))
    return max(einfach, treffer / len(lang))



def keine_dublette():
    """-> Menge der Namenspaare, die Oliver als VERSCHIEDENE Pegel bestaetigt hat.

    Ohne dieses Gegenstueck zum Handbeleg taucht jede abgelehnte Paarung
    in der naechsten Vorschlagsliste wieder auf, und dieselbe
    Entscheidung waere jedes Mal neu zu treffen. Die Liste steht in
    harmonics/help/keine_dublette.csv und haelt neben den Namen den
    Grund fest -- IJmuiden Zuidelijk Havenhoofd gegen IJmuiden
    buitenhaven, Hoek van Holland Maeslantkering gegen Scheurhaven,
    Brentwood Bay gegen Tod Inlet: nah beieinander, aehnliche Kurve, und
    doch zwei Pegel.
    """
    pfad = os.path.join(da.HELP, 'keine_dublette.csv')
    if not os.path.exists(pfad):
        return set()
    out = set()
    for r in csv.DictReader(open(pfad, encoding='utf-8')):
        a, b = (r.get('name_a') or '').strip(), (r.get('name_b') or '').strip()
        if a and b:
            out.add(frozenset((a, b)))
    return out

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

    alt = bisherige()
    abgelehnt = keine_dublette()
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
                if frozenset((namen[i], namen[j])) in abgelehnt:
                    continue
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
                    datei_b=os.path.basename(b['file']),
                    **{SPALTE: alt.get(frozenset((namen[i], namen[j])), '')}))
    # Vorschlag, wo die Entscheidung erfahrungsgemaess feststeht: gemessen
    # an den 102 von Hand entschiedenen Paaren traf "alle Woerter des
    # kuerzeren Namens stecken im laengeren UND unter 1 km" 31 mal zu und
    # lag dabei 29 mal richtig -- 94 Prozent. Fuer eine Loeschung ist das
    # zu wenig, zum Vorausfuellen genug: es nimmt vierzig Prozent der
    # Tipparbeit ab, und was nicht stimmt, wird gestrichen statt getippt.
    for z in zeilen:
        if z[SPALTE]:
            continue
        if float(z['namensueberlappung']) >= 1.0 and float(z['km']) < 1.0:
            a, b = z['name_a'], z['name_b']
            z[SPALTE] = a if len(a) >= len(b) else b
            z['begruendung'] = 'Vorschlag: Wortueberlappung 1.0, unter 1 km'
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
