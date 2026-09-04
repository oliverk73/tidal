#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dreht die SHOM-Anpassungen um die fehlende Stunde zurueck.

py/ticon_zonen.py hat es beilaeufig gefunden: von den 78 Saetzen in
harmonics_utide_observations.txt, die eine SHOM-Quelle tragen
("# station_id_context: SHOM-3"), sind 30 gegen unabhaengige Nachbarn
fest messbar, und 26 davon liegen eine Stunde zu spaet. Brest zeigt es
am klarsten: der SHOM-Konstantensatz aus der Lavergne-Sammlung und die
Anpassung an die SHOM-Tafeln stehen beide auf 0.00, die Anpassung an
die SHOM-MESSREIHE auf +1.00.

Betroffen sind auch Papeete und Numbo Noumea, die in UTC-10 und UTC+11
liegen. Eine feste Stunde ueber drei so verschiedene Zonen ist keine
Ortszeit, sondern der Fingerabdruck eines Dienstes, der alles in
franzoesischer Normalzeit ausliefert, waehrend der Einleseweg UTC
annimmt -- in py/scrape_shom_all.py steht dazu passend 'utc': 0.

Gedreht wird deshalb um genau eine Stunde, nicht um den gemessenen
Wert. Der Fehler ist eine Uhr, keine Groesse: die Messungen streuen
zwischen 1.00 und 1.31 h, und dieser Ueberschuss ist der Abstand zum
Nachbarn, nicht der Fehler des Satzes. Die Messung entscheidet nur, OB
gedreht wird.

Entschieden wird moeglichst am ZWILLING: demselben Pegel aus einer
anderen Datei, unter einem Kilometer entfernt. Das ist der einzige
Vergleich ohne Erdkunde darin. Der Nachbar in zehn Kilometern taugt an
der offenen Kueste, aber in der Gironde und der Seine liegen die
Nachbarn flussauf und flussab, und ihre Streuung von einer Stunde ist
echt -- mit dem Nachbarschaftsmass allein fielen 40 Saetze als
"widerspruechlich" heraus, die am Zwilling glasklar auf einer Stunde
stehen. Nur wo kein Zwilling da ist, entscheidet ersatzweise die
Nachbarschaft, und dann mit zwei Nachbarn aus zwei Dateien.

Der Vergleichstopf enthaelt harmonics_utide_observations.txt nicht --
sonst bestaetigen sich die Saetze desselben Einlesewegs gegenseitig.

Pauschal gedreht wird nichts: sieben der Saetze mit Zwilling stehen auf
null -- Dunkerque, Boulogne-sur-Mer, Bourcefranc-le-Chapus, Ciboure,
Pointe de Saint-Gildas, Le Robert und Ilet la Mere. Der Einleseweg hat
also nicht alle Reihen gleich behandelt; py/download_shom_refmar.py
ersetzt HF-Dateien durch nachtraeglich gepruefte, und wo das gelang,
stimmt die Zeit.

Wo auch der Zwilling fehlt, entscheidet das Amt selbst:
py/shom_gegenprobe.py holt die SHOM-Vorhersage und misst unseren Satz
dagegen. Mit --gegenprobe werden die Saetze gedreht, deren gemessener
Versatz dort zwischen 45 und 75 Minuten liegt.

Usage: python3 py/shom_stunde_richten.py [--csv] [--schreiben]
                                         [--gegenprobe]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import re
import shutil
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT                   # noqa: E402
from transfer_zonen import zeitversatz                            # noqa: E402
from transfer_zonen_richten import speeds                         # noqa: E402
from pegel_dubletten import vermerke                              # noqa: E402

DATEI = 'harmonics/utide/harmonics_utide_observations.txt'
BACKUP = os.path.join(ROOT, 'harmonics/backup')
AUS = os.path.join(ROOT, 'harmonics/help/shom_stunde.csv')
GEGEN = os.path.join(ROOT, 'harmonics/help/shom_gegenprobe.csv')
GEGEN_MIN, GEGEN_MAX = 45, 75   # Minuten, in denen es die fehlende Stunde ist
# Liegt der SHOM-Hafen flussabwaerts, kommt zur Stunde die Laufzeit dazu.
# An der Adour zeigen die drei Saetze +70, +90 und +100 min bei 4.4, 6.4
# und 11.3 km -- ein Reststau, der monoton mit der Entfernung waechst,
# waehrend Boucau-Bayonne an der Muendung (0.01 km) genau +60 zeigte.
# Deshalb bis 105 min, aber nur wenn der Rest zur Entfernung passt.
WEIT_MAX = 105
WEIT_KM = 12.0
MIN_JE_KM = 5.0

STUNDE = 1.00        # so viel wird abgezogen
NAH_KM = 15.0
MIND_GUETE = 0.97
MIND_M2 = 0.05
MAX_NACHBARN = 5
MIND_NACHBARN = 2
MIND_DATEIEN = 2     # aus so vielen verschiedenen Quellen
MAX_SPANNE = 0.40
ZWILLING_KM = 1.0    # so nah ist es derselbe Pegel, nicht der Nachbar
FENSTER = (0.70, 1.40)   # so weit darf die Messung von der Stunde abweichen
NULL = 0.35              # bis hierhin gilt der Satz als in Ordnung


def shom_saetze(recs, komm):
    out = []
    for r in recs:
        if DATEI not in r['file']:
            continue
        c = komm.get((r['file'], r['line']), '')
        m = re.search(r'# station_id_context: (SHOM-\S+)', c)
        if m:
            out.append((r, m.group(1)))
    return out


def messen(r, pool):
    """-> (Median, n, Streuung, Dateien, Werte, 'Zwilling'|'Nachbarn')."""
    zw = [o for o in pool if km(r, o) <= ZWILLING_KM]
    if zw:
        e = _messen(r, zw)
        if e:
            return e + ('Zwilling',)
    e = _messen(r, [o for o in pool if km(r, o) <= NAH_KM])
    return (e + ('Nachbarn',)) if e else None


def _messen(r, kandidaten):
    nah = sorted(kandidaten, key=lambda o: km(r, o))
    werte, dateien = [], set()
    for o in nah:
        if abs(r['z']['M2']) < MIND_M2 or abs(o['z']['M2']) < MIND_M2:
            continue
        d, guete = zeitversatz(r, o)
        if d is None or guete < MIND_GUETE:
            continue
        werte.append((d, o))
        dateien.add(os.path.basename(o['file']))
        if len(werte) >= MAX_NACHBARN:
            break
    if not werte:
        return None
    m = [w[0] for w in werte]
    return (statistics.median(m), len(m), max(m) - min(m), len(dateien), werte)


def gegenprobe(recs):  # noqa: C901
    """-> Saetze, die die SHOM-Vorhersage um rund eine Stunde verfehlen."""
    if not os.path.exists(GEGEN):
        sys.exit(f'{GEGEN} fehlt -- erst python3 py/shom_gegenprobe.py --csv')
    # Bei doppeltem Namen den SHOM-Satz nehmen, nicht irgendeinen: in
    # Fort-de-France und Pointe-a-Pitre steht neben dem SHOM-Satz noch
    # einer aus UHSLC an derselben Stelle, und die beiden liegen genau
    # eine Stunde auseinander.
    komm = vermerke()
    nach_name = {}
    for r in recs:
        alt = nach_name.get(r['name'])
        if alt is None or ('SHOM' in komm.get((r['file'], r['line']), '')
                           and 'SHOM' not in komm.get((alt['file'], alt['line']), '')):
            nach_name[r['name']] = r
    out = []
    for row in csv.DictReader(open(GEGEN, encoding='utf-8')):
        try:
            v = float(row['versatz_min'])
        except (TypeError, ValueError):
            continue
        r = nach_name.get(row['name'])
        if r is None or DATEI not in r['file']:
            continue
        try:
            d = float(row['abstand_km'])
        except (TypeError, ValueError):
            d = 0.0
        passt = GEGEN_MIN <= v <= GEGEN_MAX or (
            GEGEN_MAX < v <= WEIT_MAX and d <= WEIT_KM
            and (v - 60) <= MIN_JE_KM * d)
        if passt:
            out.append((r, row['shom_hafen'],
                        (v / 60.0, 1, 0.0, 1, [],
                         f'SHOM {row["shom_hafen"]} in {d:.1f} km')))
    return out


def main(argv):
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    komm = vermerke()
    saetze = shom_saetze(recs, komm)
    pool = [r for r in recs if DATEI not in r['file']]
    print(f'{len(saetze)} Saetze mit SHOM-Quelle in {os.path.basename(DATEI)}')

    richten, null, widerspruch, ohne = [], [], [], []
    for r, ctx in saetze:
        e = messen(r, pool)
        if e is None:
            ohne.append((r, ctx, None))
            continue
        med, n, spanne, nd, werte, art = e
        fest = (art == 'Zwilling'
                or (n >= MIND_NACHBARN and nd >= MIND_DATEIEN
                    and spanne <= MAX_SPANNE))
        if fest and FENSTER[0] <= med <= FENSTER[1]:
            richten.append((r, ctx, e))
        elif fest and abs(med) <= NULL:
            null.append((r, ctx, e))
        else:
            widerspruch.append((r, ctx, e))

    print(f'  {len(richten):3} werden um {STUNDE:.2f} h zurueckgedreht')
    print(f'  {len(null):3} stehen richtig und bleiben')
    print(f'  {len(widerspruch):3} messen etwas anderes -- nicht angefasst')
    print(f'  {len(ohne):3} haben keinen brauchbaren Nachbarn\n')

    for titel, menge in (('zu drehen', richten), ('widerspruechlich', widerspruch)):
        if not menge:
            continue
        print(f'{titel}:')
        for r, ctx, e in sorted(menge, key=lambda x: -x[2][0])[:40]:
            print(f'  {e[0]:+6.2f} h  ({e[5]}: {e[1]} aus {e[3]} Dateien, '
                  f'Streuung {e[2]:.2f})  {r["name"][:44]}')
        if len(menge) > 40:
            print(f'  ... und {len(menge) - 40} weitere')
        print()

    if '--csv' in argv:
        with open(AUS, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['urteil', 'art', 'name', 'zeile', 'ctx', 'versatz_h',
                        'nachbarn', 'dateien', 'streuung_h', 'bester_nachbar'])
            for urteil, menge in (('richten', richten), ('null', null),
                                  ('widerspruch', widerspruch), ('ohne', ohne)):
                for r, ctx, e in menge:
                    w.writerow([urteil, e[5] if e else '', r['name'], r['line'], ctx,
                                f'{e[0]:+.2f}' if e else '', e[1] if e else '',
                                e[3] if e else '', f'{e[2]:.2f}' if e else '',
                                e[4][0][1]['name'] if e else ''])
        print(f'-> {os.path.relpath(AUS, ROOT)}')

    if '--gegenprobe' in argv:
        richten = gegenprobe(recs)
        print(f'\nGegenprobe am Amt: {len(richten)} Saetze verfehlen die '
              f'SHOM-Vorhersage um {GEGEN_MIN}-{GEGEN_MAX} min')
        for r, hafen, e in sorted(richten, key=lambda x: x[0]['name']):
            print(f'  {e[0] * 60:+4.0f} min  {r["name"][:44]:44s} gegen {hafen}')

    if '--schreiben' in argv:
        schreiben(richten)
    return 0


def schreiben(richten):
    heute = dt.date.today().strftime('%Y%m%d')
    pfad = os.path.join(ROOT, DATEI)
    os.makedirs(BACKUP, exist_ok=True)
    shutil.copy2(pfad, os.path.join(
        BACKUP, f'{os.path.basename(DATEI)[:-4]}_{heute}_shom.txt'))
    sp = speeds(pfad)
    if not sp:
        sys.exit('keine Konstituentengeschwindigkeiten im Dateikopf gefunden')
    lines = open(pfad, encoding='iso-8859-1').read().split('\n')
    # Von hinten nach vorne, damit die Zeilennummern gueltig bleiben.
    for r, ctx, e in sorted(richten, key=lambda x: -x[0]['line']):
        k = r['line'] - 1
        j, n = k + 3, 0
        while j < len(lines) and n < 175:
            p = lines[j].split()
            if not p or p[0].startswith('#'):
                break
            if p[0] != 'x' and p[0] in sp:
                amp, g = float(p[1]), float(p[2])
                lines[j] = (f'{p[0]:<16}{amp:.4f}  '
                            f'{(g - sp[p[0]] * STUNDE) % 360:.2f}')
            n += 1
            j += 1
        lines[k:k] = [
            f'# note: {heute} Phasen um -{STUNDE:.2f} h gedreht: die SHOM-Messreihe',
            '# note: kam in franzoesischer Normalzeit, der Einleseweg hat sie als UTC',
            f'# note: gelesen. Gegen {e[1]} Nachbarn aus {e[3]} Dateien gemessen:',
            f'# note: {e[0]:+.2f} h. Siehe py/shom_stunde_richten.py.']
    open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(lines))
    print(f'{os.path.basename(DATEI)}: {len(richten)} Saetze gedreht')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
