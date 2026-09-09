#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Listet die Haufen, die kein Massstab entscheiden kann.

py/handbeleg_vorschlag.py zeigt nur, wo ein Identitaetsbeleg auch etwas
bewirken wuerde -- wo also eine Messung vorliegt und die Regel bei
unterstelltem Beleg loeschen wuerde. Das ist beim Abarbeiten richtig,
versteckt aber alles, was mangels Reihe unentscheidbar ist: gemessen am
07.09.2026 sind das 955 Gruppen.

Darin steckt Arbeit, die sich lohnt. Penang stand dreimal im Bestand --
"George Town, Penang, Malaysia", "Pinang (Bandar Raya Georgetown),
Malaysia" und "Pinang (Georgetown), Indonesia", derselbe Pegel unter
drei Namen, sauber als Haufen 1848 erkannt und trotzdem nie gezeigt,
weil keiner der drei je an einer Reihe gemessen wurde. Wer die Namen
jetzt vereinheitlicht, macht die Gruppe entscheidbar, sobald irgendwann
eine Messung dazukommt -- und raeumt bis dahin wenigstens die Anzeige
auf.

Sortiert wird nach Namensaehnlichkeit: oben steht, was sich am ehesten
als derselbe Ort lesen laesst.

Usage: python3 py/haufen_ohne_massstab.py
"""
from __future__ import annotations

import collections
import csv
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_aufraeumen as da                                   # noqa: E402
from handbeleg_vorschlag import ueberlappung                        # noqa: E402
from health_check import load_records, km, curve_diff               # noqa: E402
from transfer_zonen import zeitversatz                              # noqa: E402

ZIEL = os.path.join(da.HELP, 'haufen_ohne_massstab.csv')


def _flach(s):
    s = unicodedata.normalize('NFD', (s or '').lower().strip())
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')



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
    mess = da.messungen()
    abgelehnt = keine_dublette()
    zeilen = []
    for _name, menge, meta in da.haufen_gruppen(recs):
        if any(mess.get((r['name'], os.path.basename(r['file'])), []) for r in menge):
            continue                      # hat eine Messung, gehoert nicht hierher
        namen = sorted({r['name'] for r in menge})
        if len(namen) < 2:
            continue                      # gleicher Name -- da ist nichts zu tun
        satz = {r['name']: r for r in menge}
        for i in range(len(namen)):
            for j in range(i + 1, len(namen)):
                if frozenset((namen[i], namen[j])) in abgelehnt:
                    continue
                a, b = satz[namen[i]], satz[namen[j]]
                v, gu = zeitversatz(a, b)
                zeilen.append(dict(
                    aehnlichkeit=f'{ueberlappung(namen[i], namen[j]):.2f}',
                    name_a=namen[i], name_b=namen[j],
                    km=f'{km(a, b):.2f}',
                    kurve_prozent=f'{curve_diff(a, b)[1] * 100:.1f}',
                    dt_h=f'{v:+.2f}' if v is not None else '', guete=f'{gu:.3f}',
                    spur=meta['spur'], haufen=meta['nr'],
                    datei_a=os.path.basename(a['file']),
                    datei_b=os.path.basename(b['file']),
                    name_neu=''))
    # Wo sich zwei Namen bei praktisch keinem Abstand NUR durch ein
    # zusaetzliches Glied unterscheiden -- gleicher Ort, gleiches Land,
    # einmal mit Provinz oder Klammerzusatz --, ist die Sache so klar wie
    # ein Namensbeleg. Der laengere Name wird vorgeschlagen; wer die
    # Liste durchgeht, streicht nur, was nicht stimmt.
    for z in zeilen:
        if float(z['km']) > 0.5:
            continue
        a = [x.strip() for x in z['name_a'].split(',')]
        b = [x.strip() for x in z['name_b'].split(',')]
        lang, kurz = (a, b) if len(a) > len(b) else (b, a)
        ort_gleich = _flach(re.sub(r'\s*\(.*?\)', '', lang[0])) == _flach(kurz[0])
        if lang[-1] != kurz[-1]:
            continue
        if len(lang) == len(kurz) + 1 and _flach(lang[0]) == _flach(kurz[0]):
            z['name_neu'] = ', '.join(lang)
        elif len(lang) == len(kurz) and ort_gleich:
            z['name_neu'] = ', '.join(lang)
    zeilen.sort(key=lambda z: (-float(z['aehnlichkeit']), float(z['km'])))
    with open(ZIEL, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader()
        w.writerows(zeilen)
    hoch = sum(1 for z in zeilen if float(z['aehnlichkeit']) >= 0.8)
    print(f'{len(zeilen)} Namenspaare aus {len({z["haufen"] for z in zeilen})} '
          f'Haufen ohne Massstab, {hoch} davon mit Aehnlichkeit ab 0.80')
    print(f'-> {ZIEL}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
