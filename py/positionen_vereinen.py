#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gibt gleichnamigen Saetzen dieselbe, beste Position.

Tragen zwei Saetze denselben vollen Namen, sind sie nach unserer eigenen
Regel derselbe Pegel -- das ist der Identitaetsbeleg, auf den die
Loeschpruefung baut. Dann darf ihre Position nicht auseinandergehen.

Welche ist die bessere? Nicht die aus der "besseren Quelle": NOAA und
ATT sind zwar vier- bis fuenfmal haeufiger gerundet als uTide (12.7,
11.2 und 10.3 Prozent gegen 2.4), aber das ist ein Durchschnitt, kein
Urteil ueber den einzelnen Satz. Messbar ist die Rundung selbst:

  Stufe 0  frei stehende Position mit vier oder mehr Nachkommastellen
  Stufe 1  frei stehende Position, groeber geschrieben
  Stufe 2  auf ganze Bogenminuten gerundet -- der Buchwert

Eine auf Bogenminuten gerundete Position ist bis zu 0.93 km von der
Wahrheit entfernt; steht daneben ein Satz desselben Pegels mit
gemessener Position, ist die Wahl keine Geschmacksfrage.

Uebernommen wird nur nach unten: ein Satz bekommt die bessere Position,
nie eine schlechtere. Gruppen, deren Mitglieder weiter als GRENZE_KM
auseinanderliegen, bleiben unangetastet -- dort ist der gleiche Name
eher ein Namensproblem als ein Positionsproblem.

Der alte Wert bleibt als Kommentar im Satz stehen.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.

Usage: python3 py/positionen_vereinen.py [--schreiben] [--km 5]
"""
from __future__ import annotations

import collections
import datetime as dt
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sicher_schreiben                                             # noqa: E402
from health_check import load_records, active_files, ROOT, MERIDIAN, km, auf_raster  # noqa: E402

BACKUP = os.path.join(ROOT, 'harmonics/backup')
GRENZE_KM = 5.0


def geschrieben(path):
    """-> {Zeile: (lat_text, lon_text)} wie sie in der Datei stehen."""
    lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
    out = {}
    for k, l in enumerate(lines):
        if (not l or l.startswith('#') or k + 1 >= len(lines)
                or not MERIDIAN.match(lines[k + 1])):
            continue
        j, la, lo = k - 1, None, None
        while j >= 0 and lines[j].startswith('#'):
            m = re.match(r'#\s*!(latitude|longitude):\s*(\S+)', lines[j])
            if m:
                if m.group(1) == 'latitude':
                    la = m.group(2)
                else:
                    lo = m.group(2)
            j -= 1
        out[k + 1] = (la, lo)
    return out


def stufe(r, text):
    """0 = fein, 1 = frei aber grob geschrieben, 2 = auf Bogenminuten."""
    if auf_raster(r['lat'], r['lon']):
        return 2
    stellen = min((len(t.split('.')[1]) if t and '.' in t else 0) for t in text)
    return 0 if stellen >= 4 else 1


def main(argv):
    schreiben = '--schreiben' in argv
    grenze = float(argv[argv.index('--km') + 1]) if '--km' in argv else GRENZE_KM
    recs = [r for r in load_records() if r['lat'] is not None]
    text = {p: geschrieben(p) for p in active_files()}

    gruppen = collections.defaultdict(list)
    for r in recs:
        gruppen[r['name']].append(r)

    aendern = collections.defaultdict(list)
    weit = 0
    for name, menge in sorted(gruppen.items()):
        if len(menge) < 2:
            continue
        if max(km(a, b) for a in menge for b in menge) > grenze:
            weit += 1
            continue
        bewertet = [(stufe(r, text[r['file']].get(r['line'], (None, None))), r)
                    for r in menge]
        best = min(s for s, _r in bewertet)
        sieger = [r for s, r in bewertet if s == best][0]
        for s, r in bewertet:
            if s > best and (r['lat'], r['lon']) != (sieger['lat'], sieger['lon']):
                aendern[r['file']].append((r['line'], r, sieger, s, best))

    print(f'{sum(len(v) for v in aendern.values())} Saetze bekaemen eine bessere '
          f'Position ({weit} Gruppen liegen weiter als {grenze:.0f} km auseinander '
          f'und bleiben)')
    beispiele = [x for v in aendern.values() for x in v]
    beispiele.sort(key=lambda x: -km(x[1], x[2]))
    for _z, r, s, alt, neu in beispiele[:10]:
        print(f'   {r["name"][:38]:40} {r["lat"]:8.4f}{r["lon"]:10.4f} (Stufe {alt}) '
              f'-> {s["lat"]:8.4f}{s["lon"]:10.4f} (Stufe {neu})  {km(r, s)*1000:5.0f} m'
              f'  {r["file"].split("/")[-1][:22]}')
    if not schreiben:
        return 0

    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    heute = dt.datetime.now().strftime('%Y%m%d')
    gesamt = 0
    for datei, eintraege in sorted(aendern.items()):
        voll = os.path.join(ROOT, datei)
        lines = open(voll, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and MERIDIAN.match(lines[k + 1]))
        for zeile, r, sieger, _a, _b in sorted(eintraege, reverse=True):
            i = zeile - 1
            j = i - 1
            gefunden = 0
            while j >= 0 and lines[j].startswith('#'):
                m = re.match(r'#\s*!(latitude|longitude):', lines[j])
                if m:
                    wert = sieger['lat'] if m.group(1) == 'latitude' else sieger['lon']
                    lines[j] = f'# !{m.group(1)}: {wert:.6f}'
                    gefunden += 1
                j -= 1
            if gefunden == 2:
                lines[i:i] = [f'# note: {heute} Position vom gleichnamigen Satz '
                              f'uebernommen (vorher {r["lat"]:.4f}/{r["lon"]:.4f},',
                              '# note: -- auf Bogenminuten gerundet oder groeber '
                              'geschrieben als der andere).']
                gesamt += 1
        shutil.copy2(voll, os.path.join(
            BACKUP, os.path.basename(datei) + f'.vor_position_{stamp}'))
        sicher_schreiben.schreiben(voll, '\n'.join(lines))
        nachher = sum(1 for k, l in enumerate(lines)
                      if l and not l.startswith('#') and k + 1 < len(lines)
                      and MERIDIAN.match(lines[k + 1]))
        print(f'   {os.path.basename(datei):46} {len(eintraege):4} Positionen, '
              f'{vorher} -> {nachher} Saetze')
        if nachher != vorher:
            print('   ACHTUNG: Satzzahl veraendert!')
            return 1
    print(f'\n{gesamt} Positionen uebernommen')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
