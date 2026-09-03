#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raeumt doppelte Saetze weg -- entschieden an der Tafel, nicht am Rang.

Der Bestand soll je Pegel einen Satz fuehren, und zwar den genauesten.
"Der genaueste" ist eine gemessene Groesse: der Fehler gegen eine
unabhaengige Quelle, in Metern und im Verhaeltnis zum Tidenhub. Ein
erster Anlauf hat stattdessen nach Herkunft sortiert -- uTide vor
TICON-4 vor den alten Verteilungen -- und damit 1174 von 1258 Saetzen
allein ueber den Rang geloescht. Das ist die Abkuerzung, die der
Bestand nicht haben soll: die Schwelle "Kurven unter zehn Prozent
verschieden" klingt eng, sind bei vier Metern Hub aber vierzig
Zentimeter, und welcher der beiden Saetze naeher an der Tafel liegt,
sagt sie gerade nicht.

Gemessen wird deshalb aus den Guetetabellen, die die Pruefwerkzeuge
je Quelle hinterlassen (harmonics/help/*_qualitaet.csv): dort steht
zu jedem Satz der RMS gegen die Tafel des Amtes, der groesste
Einzelfehler, der Zeitversatz und der Hub. Verglichen wird nur
innerhalb derselben Tabelle -- gleiche Station, gleiches Jahr,
dieselbe Tafel.

Geloescht wird ein Satz nur, wenn er DEUTLICH schlechter ist:
mindestens drei Zentimeter mehr RMS, oder doppelt so viel bei
mindestens einem Zentimeter Unterschied. Die drei Zentimeter sind
dieselbe Untergrenze wie in py/tafel_kaputt.py -- darunter misst man
die Tafel, nicht den Satz.

Wo beide gleich gut sind, bleibt beides stehen. Das ist Absicht: die
Dublette kostet nichts als einen Eintrag in der Liste, eine falsche
Loeschung kostet den besseren Satz.

Usage: python3 py/dubletten_aufraeumen.py [--csv] [--offen]
       --offen  auch die Gruppen ohne Messung auflisten
"""
from __future__ import annotations

import collections
import csv
import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, curve_diff, ROOT       # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
NAH_KM = 1.0          # weiter auseinander ist es nicht derselbe Pegel
GLEICH = 0.10         # ab hier ist es ein Widerspruch, keine Dublette
MIND_M = 0.03         # so viel mehr RMS muss der Verlierer haben
FAKTOR = 2.0          # oder so viel mal so viel
MIND_FAKTOR_M = 0.01  # und dann immer noch diesen Abstand


def messungen():
    """-> {(Satzname, Datei): [(Station, Jahr, Quelle, rms, max, hub, blind)]}.

    "blind" heisst: dieser Satz wurde aus eben dieser Reihe gefittet und
    hat auf ihr trainiert (Spalte eigen aus py/messreihe_qualitaet.py).
    Ein solcher Satz darf verlieren, aber nicht gewinnen -- sein guter
    Wert waere nur die Erinnerung an die eigenen Trainingsdaten. Wurde
    ausserhalb des Fitfensters gemessen (Spalte ausserhalb), zaehlt er
    wieder voll.
    """
    out = collections.defaultdict(list)
    for pfad in sorted(glob.glob(os.path.join(HELP, '*qualitaet*.csv'))):
        quelle = os.path.basename(pfad).replace('_qualitaet.csv', '')
        for r in csv.DictReader(open(pfad, encoding='utf-8')):
            try:
                rms = float(r['rms_m'])
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(rms):
                continue
            hub = None
            try:
                hub = float(r['hub_m']) or None
            except (KeyError, TypeError, ValueError):
                pass
            gross = None
            try:
                gross = float(r['max_m'])
            except (KeyError, TypeError, ValueError):
                pass
            blind = (r.get('eigen') == '1' and r.get('ausserhalb', 'nein') != 'ja')
            out[(r.get('satz', ''), r.get('datei', ''))].append(
                (r.get('station', ''), r.get('jahr', ''), quelle, rms, gross, hub, blind))
    return out


def gruppen(recs):
    """-> Gruppen gleichen Namens, die wirklich derselbe Pegel sind."""
    nach = collections.defaultdict(list)
    for r in recs:
        nach[r['name']].append(r)
    out = []
    for name, alle in sorted(nach.items()):
        for menge in ([r for r in alle if not r['current']],
                      [r for r in alle if r['current']]):
            if len(menge) < 2:
                continue
            if max(km(a, b) for i, a in enumerate(menge) for b in menge[i + 1:]) >= NAH_KM:
                continue
            if max(curve_diff(a, b)[1] for i, a in enumerate(menge)
                   for b in menge[i + 1:]) >= GLEICH:
                continue
            out.append((name, menge))
    return out


def deutlich_schlechter(rms, best):
    return rms - best >= MIND_M or (rms >= FAKTOR * best and rms - best >= MIND_FAKTOR_M)


def main(argv):
    mess = messungen()
    recs = [r for r in load_records() if r['lat'] is not None]
    weg, gleichauf, ohne, zirkulaer = [], [], [], []
    for name, menge in gruppen(recs):
        # Messungen der Gruppe nach Tabelle buendeln: nur was gegen
        # dieselbe Station im selben Jahr gemessen wurde, ist vergleichbar.
        nach_tabelle = collections.defaultdict(dict)
        for r in menge:
            for station, jahr, quelle, rms, gross, hub, blind in mess.get(
                    (r['name'], os.path.basename(r['file'])), ()):
                nach_tabelle[(quelle, station, jahr)][id(r)] = (rms, gross, hub, blind)
        vergleichbar = {k: v for k, v in nach_tabelle.items() if len(v) == len(menge)}
        if not vergleichbar:
            ohne.append((name, menge))
            continue
        # Mehrere Jahre derselben Tafel: den Median je Satz nehmen.
        werte = collections.defaultdict(list)
        blind = collections.defaultdict(bool)
        hub = None
        for k, v in vergleichbar.items():
            for i, (rms, _gross, h, b) in v.items():
                werte[i].append(rms)
                blind[i] = blind[i] or b
                hub = hub or h
        med = {i: sorted(v)[len(v) // 2] for i, v in werte.items()}
        # Wer auf der Reihe trainiert hat, ist kein Massstab und wird auch
        # nicht geloescht. Verglichen wird gegen den besten der uebrigen --
        # sonst faellt eine ganze Dreiergruppe aus, nur weil einer davon
        # nicht beurteilbar ist.
        frei = [r for r in menge if not blind[id(r)]]
        if not frei:
            zirkulaer.append((name, menge))
            continue
        best = min(med[id(r)] for r in frei)
        sieger = [r for r in frei if med[id(r)] == best][0]
        if len(frei) < len(menge):
            zirkulaer.append((name, [r for r in menge if blind[id(r)]]))
        for v in frei:
            if v is sieger:
                continue
            if deutlich_schlechter(med[id(v)], best):
                weg.append((v, sieger, med[id(v)], best, hub, len(vergleichbar)))
            else:
                gleichauf.append((v, sieger, med[id(v)], best, hub))

    print(f'{len(weg)} Saetze sind an der Tafel deutlich schlechter und koennen weg')
    print(f'{len(gleichauf)} sind gleichauf -- beide bleiben')
    print(f'{len(zirkulaer)} Saetze bleiben unbeurteilt (auf der Reihe trainiert)')
    print(f'{len(ohne)} Gruppen haben keine Messung')
    d = collections.Counter(os.path.basename(v['file']) for v, *_ in weg)
    print(f'\n{"Datei":42} {"geht":>6}')
    for k, n in d.most_common():
        print(f'{k[:42]:42} {n:6}')
    print(f'\nBeispiele:')
    for v, s, rms, best, hub, n in sorted(weg, key=lambda x: -(x[2] - x[3]))[:12]:
        h = f'{(rms - best) / hub * 100:4.1f} % Hub' if hub else '   ?'
        print(f'  {v["name"][:34]:34} {rms * 100:6.1f} cm gegen {best * 100:5.1f} cm '
              f'({h})  {os.path.basename(v["file"])[:24]} raus, '
              f'{os.path.basename(s["file"])[:24]} bleibt')

    if '--offen' in argv:
        print('\nGruppen ohne Messung:')
        laender = collections.Counter(n.split(',')[-1].strip() for n, _m in ohne)
        for land, c in laender.most_common(20):
            print(f'  {c:5}  {land}')

    if '--csv' in argv:
        p = os.path.join(HELP, 'dubletten_loeschen.csv')
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
            for v, s, rms, best, hub, n in weg:
                anteil = (rms / hub * 100) if hub else 0.0
                w.writerow([v['file'], v['name'], f'{anteil:.1f}',
                            f'Dublette: {km(v, s) * 1000:.0f} m von "{s["name"]}" '
                            f'({os.path.basename(s["file"])}), Kurve '
                            f'{curve_diff(v, s)[1] * 100:.0f} % gleich. An der Tafel '
                            f'({n} Vergleich(e)) {rms * 100:.1f} cm RMS gegen '
                            f'{best * 100:.1f} cm' +
                            (f' bei {hub:.2f} m Hub' if hub else '') + '.'])
        print(f'\n-> {p}')
        q = os.path.join(HELP, 'dubletten_gleichauf.csv')
        with open(q, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['name', 'datei_a', 'rms_a_cm', 'datei_b', 'rms_b_cm', 'hub_m'])
            for v, s, rms, best, hub in gleichauf:
                w.writerow([v['name'], os.path.basename(v['file']), f'{rms * 100:.1f}',
                            os.path.basename(s['file']), f'{best * 100:.1f}',
                            f'{hub:.2f}' if hub else ''])
        print(f'-> {q}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
