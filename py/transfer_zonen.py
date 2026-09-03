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
wird der naechste Satz unter 3 km gesucht, der selbst keine Uebertragung
ist (Admiralty, TICON, uTide), und die M2-Phasendifferenz in Stunden
umgerechnet. Ueber viele Saetze mittelt sich die oertliche Streuung
heraus, der systematische Anteil bleibt stehen.

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

Usage: python3 py/transfer_zonen.py [--km 3] [--csv]
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
from health_check import load_records, km, active_files, MERIDIAN     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAH_KM = 3.0
M2 = 28.984104
VERMERK = re.compile(r'transfer from (.+?) \(no\.')


def zonenstunden(name):
    """-> Normalzeit-Versatz der IANA-Zone in Stunden (ohne Sommerzeit)."""
    try:
        z = ZoneInfo(name)
    except Exception:
        return None
    for monat in (1, 7):
        d = dt.datetime(2026, monat, 15, tzinfo=z)
        if d.dst() == dt.timedelta(0):
            return d.utcoffset().total_seconds() / 3600
    return None


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
            d = km(r, x)
            if d < nah and (best is None or d < best[0]):
                best = (d, x)
        versatz = None
        if best and abs(r['z']['M2']) > 0.05 and abs(best[1]['z']['M2']) > 0.05:
            dg = (math.degrees(-cmath.phase(r['z']['M2']))
                  - math.degrees(-cmath.phase(best[1]['z']['M2']))) % 360
            versatz = (dg - 360 if dg > 180 else dg) / M2
            gruppen[(os.path.basename(r['file']), round(zd, 1))].append(versatz)
        zeilen.append((r, ref, zd, best, versatz))

    print(f'{len(faelle)} Uebertragungen mit auffindbarem Bezugsort, '
          f'{sum(len(v) for v in gruppen.values())} davon mit unabhaengigem '
          f'Nachbarn unter {nah:.0f} km\n')
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
            w.writerow(['datei', 'name', 'bezugsort', 'zonendiff_h',
                        'nachbar', 'nachbar_km', 'versatz_h'])
            for r, ref, zd, best, versatz in zeilen:
                w.writerow([os.path.basename(r['file']), r['name'], ref, f'{zd:+.1f}',
                            best[1]['name'] if best else '',
                            f'{best[0]:.1f}' if best else '',
                            f'{versatz:+.2f}' if versatz is not None else ''])
        print(f'\n-> {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
