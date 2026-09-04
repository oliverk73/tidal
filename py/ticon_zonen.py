#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft, ob TICON-4-Saetze gegen ihre Nachbarn um volle Stunden verschoben sind.

Anlass war Cherbourg. Dort stand ein TICON-4-Satz, der als Stroemung in
Knoten etikettiert war und in Wahrheit Meereshoehen trug. Nach der
Reparatur passte er nicht zu seiner Umgebung: gegen Barfleur 1.07 h zu
frueh, gegen Saint-Vaast 1.32 h, waehrend der uTide-Satz derselben
Stelle das bekannte Bild im Alderney Race trifft -- Goury 1.9 h vor
Cherbourg, Barfleur praktisch gleichzeitig.

Ein Blick auf die franzoesischen TICON-4-Saetze zeigte, dass Cherbourg
kein Einzelfall ist: von 22 mit nahen Nachbarn standen 11 auf null und
8 auf minus einer Stunde. Am Meridianfeld liegt es nicht -- unter den
Betroffenen sind beide Meridiane vertreten, unter den Unauffaelligen
auch.

Die Vermutung ist deshalb die Quellreihe. TICON-4 ist eine harmonische
Analyse von GESLA-4, und GESLA-4 buendelt Dutzende nationale Bestaende,
von denen einige in Ortszeit statt in UTC gefuehrt werden. Der
Datensatzname steht in jedem Satz: "cherbourg-che-fra-refmar" endet auf
die GESLA-Quelle. Gruppiert wird deshalb danach.

Gemessen wird wie in py/transfer_zonen.py: zu jedem TICON-Satz werden
die naechsten Saetze gesucht, die NICHT aus TICON stammen, und der
Zeitversatz bestimmt, der die eine Kurve auf die andere schiebt --
nicht ueber M2 allein, sondern ueber alle fuenf Hauptkonstituenten
zugleich, damit K1 und O1 die Zweideutigkeit der halbtaegigen Welle
brechen. Genommen wird der Median ueber bis zu fuenf Nachbarn.

Der Vergleich traegt nur, wo beide Kurven dieselbe Gestalt haben; die
Guete sagt das. Unter 0.97 wird der Nachbar verworfen -- sonst misst
man den Unterschied zweier Orte statt einer Verschiebung.

Die Kontrollgruppe macht den Befund erst belastbar: dieselbe Messung
laeuft ueber die uTide-Saetze, die nicht aus TICON stammen. Streut die
um null, liegt es an TICON; streut sie mit, liegt es am Verfahren.

Usage: python3 py/ticon_zonen.py [--km 15] [--csv] [--kontrolle]
"""
from __future__ import annotations

import collections
import csv
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT                  # noqa: E402
from transfer_zonen import zeitversatz                           # noqa: E402

AUS = os.path.join(ROOT, 'harmonics/help/ticon_zonen.csv')
NAH_KM = 15.0        # weiter weg wird der Vergleich unruhig
MIND_GUETE = 0.97    # darunter sind es zwei verschiedene Gezeiten
MIND_M2 = 0.05       # unter 5 cm M2 traegt der Vergleich nichts
MAX_NACHBARN = 5
AUFFAELLIG = 0.35    # ab hier gilt der Satz als verschoben
FEST_N = 3           # so viele Nachbarn muessen es sagen
FEST_SPANNE = 0.30   # und sie muessen sich einig sein


def gitter(recs, grad=1):
    g = collections.defaultdict(list)
    for r in recs:
        g[(round(r['lat'] / grad), round(r['lon'] / grad))].append(r)
    return g


def versatz(r, g, verboten):
    """-> (Median-Zeitversatz, Zahl der Nachbarn, Streuung) oder None."""
    cz, cm = round(r['lat']), round(r['lon'])
    nah = [o for dz in (-1, 0, 1) for dm in (-1, 0, 1)
           for o in g.get((cz + dz, cm + dm), ())]
    nah = [o for o in nah if o is not r and verboten(o) is False and km(r, o) <= NAH_KM]
    nah.sort(key=lambda o: km(r, o))
    werte = []
    for o in nah:
        if abs(r['z']['M2']) < MIND_M2 or abs(o['z']['M2']) < MIND_M2:
            continue
        dt, guete = zeitversatz(r, o)
        if dt is None or guete < MIND_GUETE:
            continue
        werte.append(dt)
        if len(werte) >= MAX_NACHBARN:
            break
    if not werte:
        return None
    spanne = max(werte) - min(werte) if len(werte) > 1 else 0.0
    return statistics.median(werte), len(werte), spanne


def quelle(r, komm):
    """-> GESLA-4-Bestand aus station_id_context, z.B. 'refmar'."""
    c = komm.get((r['file'], r['line']), '')
    for zeile in c.split('\n'):
        if zeile.startswith('# station_id_context:'):
            return zeile.split(':', 1)[1].strip().rsplit('-', 1)[-1]
    return '?'


def kontexte():
    """-> {(Datei, Zeile des Namens): Kommentarblock}."""
    from pegel_dubletten import vermerke
    return vermerke()


def main(argv):
    global NAH_KM
    if '--km' in argv:
        NAH_KM = float(argv[argv.index('--km') + 1])
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    komm = kontexte()
    tic = [r for r in recs if 'ticon4' in r['file']]
    rest = [r for r in recs if 'ticon4' not in r['file']]
    g_rest = gitter(rest)
    print(f'{len(tic)} TICON-4-Saetze gegen {len(rest)} fremde Saetze, '
          f'Umkreis {NAH_KM:.0f} km\n')

    zeilen = []
    for r in tic:
        e = versatz(r, g_rest, lambda o: False)
        if e:
            zeilen.append((e[0], e[1], e[2], r, quelle(r, komm)))
    print(f'{len(zeilen)} davon haben brauchbare Nachbarn')

    nach_quelle = collections.defaultdict(list)
    for m, _n, _s, _r, q in zeilen:
        nach_quelle[q].append(m)
    print(f'\n{"GESLA-Bestand":16s} {"n":>4} {"Median":>8} {"auf -1 h":>9} '
          f'{"auf 0 h":>8}  Laender')
    for q, werte in sorted(nach_quelle.items(), key=lambda t: -len(t[1])):
        eins = sum(1 for x in werte if -1.35 < x < -0.65)
        null = sum(1 for x in werte if abs(x) <= AUFFAELLIG)
        laender = collections.Counter(
            r['name'].rsplit(',', 1)[-1].strip()
            for _m, _n, _s, r, qq in zeilen if qq == q)
        top = ', '.join(k for k, _ in laender.most_common(3))
        print(f'{q:16s} {len(werte):4} {statistics.median(werte):+8.2f} '
              f'{eins:9} {null:8}  {top[:38]}')

    # Der blosse Ausreisser sagt nichts: die Kontrollgruppe hat davon
    # genauso viele. Belastbar ist erst, wenn mehrere Nachbarn dasselbe
    # sagen -- dann ist es keine Eigenheit des einen Nachbarorts mehr.
    def fest(z):
        return z[1] >= FEST_N and z[2] <= FEST_SPANNE

    def histogramm(werte, titel):
        b = collections.Counter(round(x * 4) / 4 for x in werte)
        print(f'\n{titel}: {len(werte)} feste Messungen')
        for k in sorted(b):
            if b[k]:
                print(f'   {k:+5.2f} h  {"#" * min(60, b[k])} {b[k]}')

    histogramm([z[0] for z in zeilen if fest(z)], 'TICON-4')
    auff = [z for z in zeilen if abs(z[0]) > AUFFAELLIG and fest(z)]
    print(f'\n{len(auff)} feste Messungen weichen um mehr als {AUFFAELLIG:.2f} h ab:')
    for m, n, s, r, q in sorted(auff, key=lambda z: z[0])[:30]:
        print(f'  {m:+6.2f} h  ({n} Nachbarn, Streuung {s:.2f})  {q:12s} '
              f'{r["name"][:44]}')
    if len(auff) > 30:
        print(f'  ... und {len(auff) - 30} weitere')

    if '--kontrolle' in argv:
        # Dieselbe Messung fuer die uTide-Beobachtungen: streut die um null,
        # liegt der Befund an TICON und nicht am Verfahren.
        # Der Vergleichstopf der Kontrolle darf TICON nicht enthalten: sonst
        # sieht sie genau die Saetze, die hier zur Debatte stehen, und ein
        # TICON-Satz, der eine Stunde zu frueh liegt, laesst seinen uTide-
        # Nachbarn eine Stunde zu spaet erscheinen. Beim ersten Lauf standen
        # so 13 Kontrollsaetze auf +1.00 h -- dieselben Paare von der
        # anderen Seite.
        ut = [r for r in rest if 'utide_observations' in r['file']]
        andere = [r for r in recs if 'utide_observations' not in r['file']
                  and 'ticon4' not in r['file']]
        g_a = gitter(andere)
        k = [x for x in (versatz(r, g_a, lambda o: False) for r in ut) if x]
        fk = [x[0] for x in k if x[1] >= FEST_N and x[2] <= FEST_SPANNE]
        print(f'\nKontrollgruppe uTide-Beobachtungen: {len(k)} Saetze, davon '
              f'{len(fk)} feste Messungen, '
              f'{sum(1 for x in fk if abs(x) > AUFFAELLIG)} auffaellig '
              f'({100 * sum(1 for x in fk if abs(x) > AUFFAELLIG) / max(1, len(fk)):.1f} %)')
        histogramm(fk, 'Kontrolle uTide')

    if '--csv' in argv:
        with open(AUS, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['versatz_h', 'nachbarn', 'streuung_h', 'gesla', 'name',
                        'datei', 'zeile', 'lat', 'lon'])
            for m, n, s, r, q in sorted(zeilen, key=lambda z: z[0]):
                w.writerow([f'{m:+.2f}', n, f'{s:.2f}', q, r['name'], r['file'],
                            r['line'], f'{r["lat"]:.4f}', f'{r["lon"]:.4f}'])
        print(f'\n-> {os.path.relpath(AUS, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
