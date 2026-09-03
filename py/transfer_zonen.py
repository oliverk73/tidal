#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft, ob bei Table-2-Uebertragungen die Zonendifferenz fehlt.

Anlass war Anadyr. Dort standen zwei Saetze auf derselben Stelle: der
Sekundaerhafen 8369 aus NP204 Part III (gemessene Harmonische) und eine
NOAA-Table-2-Uebertragung von Busan. Beide Kurven wichen um 74 Prozent
voneinander ab, und die Gegenprobe entschied den Fall eindeutig: NP204
Part II gibt "HW Anadyr = HW Wellington +0635", der ATT-Satz trifft das
auf 5 bis 38 Minuten, der NOAA-Satz liegt rund drei Stunden spaeter.
Drei Stunden sind genau der Zonenunterschied zwischen Busan (+09) und
Anadyr (+12).

Damit war die Frage gestellt, ob das ein Einzelfall ist. NOAAs Table 2
rechnet in Ortszeit: die gedruckte Zeitdifferenz wird auf die Zeit des
Bezugsorts addiert, das Ergebnis gilt in der Zone des Nebenorts. In UTC
heisst das

    t_neben = t_bezug + dt + (Zone_bezug - Zone_neben)

Wer nur dt addiert, verschiebt jeden Satz um die Zonendifferenz.

Gemessen wird das an unabhaengigen Nachbarn: zu jedem Uebertragungssatz
wird der naechste Satz gesucht, der selbst keine Uebertragung ist
(Admiralty, TICON, uTide), und der Zeitversatz bestimmt, der die eine
Kurve auf die andere schiebt. Nicht ueber M2 allein -- eine einzelne
halbtaegige Konstituente laesst offen, ob es sechs Stunden vor oder
zurueck sind. Gesucht wird deshalb das Delta t, das ueber alle fuenf
Hauptkonstituenten zugleich passt (Summe der amplitudengewichteten
Kosinus maximal); K1 und O1 mit ihren tagesperioden brechen die
Zweideutigkeit. Die Guete daneben sagt, wie sauber die Verschiebung den
Unterschied erklaert: 1.0 heisst reine Zeitverschiebung, kleine Werte
heissen, dass die beiden Orte einfach verschiedene Gezeiten haben.

Zwei Nachbarn aus DERSELBEN Uebertragungsfamilie zu vergleichen sagt
nichts: sie sind skalierte Kopien desselben Bezugsorts. Melkaya Bay
gegen Salomatova Spit ergibt eine Guete von 1.000 -- und beide sind
gleich falsch. Verglichen wird deshalb nur gegen Saetze ohne
Transfervermerk.

Die Kontrollgruppe macht den Befund erst belastbar: die 1201 Saetze, bei
denen Bezugs- und Nebenort in derselben Zone liegen, streuen um -0.02 h.
Wo die Zonen auseinanderliegen, folgt der Median dagegen der
Zonendifferenz -- in harmonics_noaa_cptt und harmonics_noaa_eutt, nicht
aber in harmonics_noaa_amtt, wo alle Gruppen bei null bleiben. Der
Fehler steckt also im Einleseweg dieser beiden Dateien, nicht in den
Tafeln.

Was der Test nicht leistet: er beweist nichts fuer den einzelnen Satz.
Ein Nachbar in 3 km kann in einer anderen Bucht liegen, und bei
Zonendifferenzen ueber sechs Stunden wird das Bild unruhig -- dort
stehen zu wenige Paare, und der Wechsel ueber die Datumsgrenze bringt
eigene Fehler mit. Belastbar ist die Aussage ueber die Gruppe.

Usage: python3 py/transfer_zonen.py [--km 5] [--guete 0.80] [--csv]
"""
from __future__ import annotations

import cmath
import collections
import csv
import datetime as dt
import math
import os
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, active_files, MERIDIAN, SPEED, MAIN  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAH_KM = 5.0
MIND_M2 = 0.05       # unter 5 cm M2 traegt der Vergleich nichts
VERMERK = re.compile(r'transfer from (.+?) \(no\.')
# Dieselbe Epoche wie in build_noaa_eutt.py: die Baende bilden alte
# C&GS-Bestaende ab, massgeblich ist die Zone der Tafel-Aera. Marokko
# etwa rechnet dort mit UTC+0 und steht heute auf UTC+1.
EPOCHE = dt.datetime(1980, 1, 15, 12)


def zonenstunden(name):
    """-> Normalzeit-Versatz der IANA-Zone in Stunden zur Tafel-Epoche."""
    try:
        return ZoneInfo(name).utcoffset(EPOCHE).total_seconds() / 3600
    except Exception:
        return None


def passung(a, b, versatz):
    """Wie gut erklaert eine Verschiebung um `versatz` Stunden den
    Unterschied zwischen a und b? 1.0 = vollstaendig, 0 = gar nicht."""
    teile = _teile(a, b)
    if len(teile) < 3:
        return None
    gewicht = sum(w for _s, _d, w in teile)
    return sum(w * math.cos(d - math.radians(s * versatz))
               for s, d, w in teile) / gewicht


def _teile(a, b):
    out = []
    for x in MAIN:
        za, zb = a['z'][x], b['z'][x]
        w = min(abs(za), abs(zb))
        if w >= 0.01:
            out.append((SPEED[x], (-cmath.phase(za)) - (-cmath.phase(zb)), w))
    return out


def zeitversatz(a, b, spanne=12.0, schritt=1 / 60):
    """-> (Stunden, um die a spaeter liegt als b; Guete 0..1)."""
    teile = _teile(a, b)
    if len(teile) < 3:
        return None, 0.0
    gewicht = sum(w for _s, _d, w in teile)
    best = (-2.0, 0.0)
    for i in range(int(2 * spanne / schritt) + 1):
        t = -spanne + i * schritt
        f = sum(w * math.cos(d - math.radians(s * t)) for s, d, w in teile) / gewicht
        if f > best[0]:
            best = (f, t)
    return best[1], best[0]


def vermerke():
    """-> {(datei, zeile): (zonenname, transfervermerk)} fuer alle Saetze."""
    out = {}
    for path in active_files():
        lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
        for k, line in enumerate(lines):
            if (not line or line.startswith('#') or k + 1 >= len(lines)
                    or not MERIDIAN.match(lines[k + 1])):
                continue
            m = re.search(r':\s*(\S+)$', lines[k + 1])
            note, j = '', k - 1
            while j >= 0 and lines[j].startswith('#'):
                if 'transfer from' in lines[j]:
                    note = lines[j]
                j -= 1
            out[(path, k + 1)] = (m.group(1) if m else '', note)
    return out


def main(argv):
    nah = float(argv[argv.index('--km') + 1]) if '--km' in argv else NAH_KM
    mind_guete = float(argv[argv.index('--guete') + 1]) if '--guete' in argv else 0.80
    info = vermerke()
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    zone = {}
    for r in recs:
        zone.setdefault(r['name'], info.get((r['file'], r['line']), ('', ''))[0])

    faelle = []
    for r in recs:
        tz, note = info.get((r['file'], r['line']), ('', ''))
        m = VERMERK.search(note) if note else None
        if not m:
            continue
        ref = m.group(1).strip()
        rtz = zone.get(ref)
        if rtz is None:
            # Der Vermerk nennt den Bezugsort ohne Landeszusatz.
            treffer = [n for n in zone if n.startswith(ref)]
            rtz = zone[treffer[0]] if treffer else None
        a, b = zonenstunden(tz), (zonenstunden(rtz) if rtz else None)
        if a is None or b is None:
            continue
        faelle.append((r, ref, a - b))

    # Unabhaengiger Nachbar: selbst keine Uebertragung, unter nah km.
    frei = [x for x in recs if not info.get((x['file'], x['line']), ('', ''))[1]]
    gruppen = collections.defaultdict(list)
    zeilen = []
    for r, ref, zd in faelle:
        best = None
        for x in frei:
            if abs(x['z']['M2']) < MIND_M2:
                continue
            d = km(r, x)
            if d < nah and (best is None or d < best[0]):
                best = (d, x)
        versatz = guete = None
        if best and abs(r['z']['M2']) > MIND_M2:
            versatz, guete = zeitversatz(r, best[1])
            if versatz is not None and guete >= mind_guete:
                gruppen[(os.path.basename(r['file']), round(zd, 1))].append(versatz)
        zeilen.append((r, ref, zd, best, versatz, guete))

    print(f'{len(faelle)} Uebertragungen mit auffindbarem Bezugsort, '
          f'{sum(len(v) for v in gruppen.values())} davon mit unabhaengigem '
          f'Nachbarn unter {nah:.0f} km und Guete ueber {mind_guete:.2f}\n')
    print(f'{"Datei":32} {"Zonendiff":>9} {"n":>5} {"Median":>8}  Befund')
    for (f, zd), v in sorted(gruppen.items()):
        v = sorted(v)
        med = v[len(v) // 2]
        if abs(zd) < 0.01:
            befund = 'Kontrollgruppe' if abs(med) < 0.2 else 'Kontrollgruppe AUFFAELLIG'
        elif abs(med) < 0.3:
            befund = 'sauber'
        elif abs(med - zd) < 0.5 * max(1.0, abs(zd)):
            befund = 'Zonendifferenz fehlt'
        else:
            befund = 'unklar'
        print(f'{f[:32]:32} {zd:+9.1f} {len(v):5} {med:+7.2f} h  {befund}')

    if '--csv' in argv:
        p = os.path.join(ROOT, 'harmonics/help/transfer_zonen.csv')
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['datei', 'name', 'lat', 'lon', 'bezugsort', 'zonendiff_h',
                        'nachbar', 'nachbar_km', 'versatz_h', 'guete'])
            for r, ref, zd, best, versatz, guete in zeilen:
                w.writerow([os.path.basename(r['file']), r['name'],
                            f'{r["lat"]:.4f}', f'{r["lon"]:.4f}', ref, f'{zd:+.1f}',
                            best[1]['name'] if best else '',
                            f'{best[0]:.1f}' if best else '',
                            f'{versatz:+.2f}' if versatz is not None else '',
                            f'{guete:.2f}' if guete is not None else ''])
        print(f'\n-> {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
