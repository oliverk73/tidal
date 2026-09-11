#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht systematische Zeitfehler ganzer Gruppen -- gegen FES2022.

Einzelsaetze gegen FES zu beurteilen ist unsicher (Fluesse, Lagunen,
Meerengen, Landzellen). Ganze Gruppen sind es nicht: haengen alle
Uebertragungen eines Bezugshafens oder alle Saetze eines Meridians eine
Stunde daneben, steckt ein Fehler in der Rechnung oder der Beschriftung
(NP208: Stunden-Minuten und Zonenwechsel; TICON/Puertos: UTC-Phasen unter
+01:00). So wurden sie am 10./11.09.2026 gefunden.

Gezaehlt wird ein Satz nur, wenn
  * FES am Ort eine echte Amplitude hat (Landzellen liefern Unsinn --
    Observatory Bay, 11.09.2026),
  * er selbst und FES je mindestens MIND_AMP haben,
  * die Partialtiden einheitlich verschoben sind (Streuung bis STREU min).

Gruppen: (Datei, Bezugshafen) fuer Uebertragungen, (Datei, Meridian) fuer
alle. Gemeldet wird eine Gruppe mit mindestens MIND_N einheitlichen Saetzen
und |Median| ab MELDE min.

NUR ZUM FINDEN. Entschieden wird an unabhaengigen Harmonics-Nachbarn
(Zwilling bis ~3 km, sonst bis ~15 km, keine Uebertragungen), FES nur wo es
keine gibt (Oliver, 11.09.2026). FES lag schon falsch: San'in-Kueste bis
+60 min, Landzellen (Observatory Bay), Awatscha-Bucht (Petropawlowsk FES +60,
uTide-Zwilling +8).

Aufruf: venv/bin/python3 py/fes_gruppenpruefung.py [--datei <teil>] [--alle]
"""
from __future__ import annotations

import collections
import csv
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ticon_zeitpruefung as T                                  # noqa: E402
from health_check import load_records                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIND_AMP = 0.05
STREU = 30
MIND_N = 3
MELDE = 25
BEZUG = re.compile(r'(?:transfer from|Transfer von|Bezugshafen|on) ([^(.,;]+?)(?: \(| \d|,|\.|;|$)')


def main(argv):
    nur = argv[argv.index('--datei') + 1] if '--datei' in argv else None
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']
            and (not nur or nur in r['file'])]
    texte = {}
    for r in recs:
        if r['file'] not in texte:
            texte[r['file']] = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
    fes = T.fes_werte(recs)
    zeilen = []
    for r in recs:
        L = texte[r['file']]
        k = r['line'] - 1
        j, kopf = k - 1, []
        while j >= 0 and not L[j].startswith('# BEGIN HOT'):
            kopf.append(L[j])
            j -= 1
        text = ' '.join(reversed(kopf))
        d = {}
        for c in T.TEILE:
            g, a = T.phase(r, c)
            gf, af = fes[id(r)][c]
            if a >= MIND_AMP and af >= MIND_AMP and not math.isnan(gf):
                d[c] = T.versatz_min(g, gf, c)
        if len(d) < 2:
            continue
        m = statistics.mean(d.values())
        sp = max(d.values()) - min(d.values())
        uebertragung = bool(re.search(r'transfer|Transfer|Sekundaer', text))
        b = BEZUG.search(text) if uebertragung else None
        zeilen.append(dict(datei=os.path.basename(r['file']), name=r['name'],
                           meridian=L[k + 1].split()[0], bezug=b.group(1).strip() if b else '',
                           uebertragung=uebertragung, fes=m, streu=sp))
    gruppen = collections.defaultdict(list)
    for z in zeilen:
        gruppen[('Meridian', z['datei'], z['meridian'])].append(z)
        if z['uebertragung'] and z['bezug']:
            gruppen[('Bezug', z['datei'], z['bezug'])].append(z)
    datei = collections.defaultdict(list)
    for z in zeilen:
        datei[z['datei']].append(z)
    print(f'{len(zeilen)} Saetze mit FES-Vergleich in {len(datei)} Dateien\n')
    print('Je Datei (einheitliche Saetze):')
    for f, v in sorted(datei.items()):
        e = [z['fes'] for z in v if z['streu'] <= STREU]
        if e:
            print(f'  {f:44} n={len(e):4}  Median {statistics.median(e):+5.0f} min  '
                  f'|>=40|: {sum(1 for x in e if abs(x) >= 40):3}')
    print('\nAuffaellige Gruppen:')
    aus = []
    for (art, f, key), v in sorted(gruppen.items()):
        e = [z for z in v if z['streu'] <= STREU]
        if len(e) < MIND_N:
            continue
        med = statistics.median(z['fes'] for z in e)
        if abs(med) >= MELDE or '--alle' in argv:
            anteil = sum(1 for z in e if abs(z['fes'] - med) <= 20) / len(e)
            print(f'  {art:8} {f[:34]:34} {key[:28]:28} n={len(e):3}  Median {med:+5.0f} min  '
                  f'eng um Median {anteil:4.0%}  z.B. {", ".join(z["name"][:22] for z in e[:3])}')
            aus.append(dict(art=art, datei=f, schluessel=key, n=len(e), median=round(med),
                            anteil=round(anteil, 2), beispiele='; '.join(z['name'] for z in e[:6])))
    if aus:
        with open(os.path.join(ROOT, 'harmonics/help/fes_gruppenpruefung.csv'), 'w', newline='',
                  encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(aus[0].keys()))
            w.writeheader()
            w.writerows(aus)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
