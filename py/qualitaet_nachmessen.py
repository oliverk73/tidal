#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst einzelne Zeilen der Qualitaetstabellen neu, nachdem Saetze sich geaendert haben.

Die Qualitaetstabellen haengen am Namen, nicht am Inhalt des Satzes. Wird
ein Satz neu gerechnet -- etwa die 60 NOAA-Uebertragungen mit berichtigtem
Bezugsort am 10.09.2026 --, bleibt seine alte Messung stehen, und
dubletten_aufraeumen.py loescht ihn womoeglich fuer einen Fehler, den er
nicht mehr hat ("Active Pass" stand mit 84 cm drin, gemessen an der
Fassung mit dem Columbia-River-Bezug).

Nachgemessen werden nur die betroffenen Zeilen, gegen dieselbe Reihe und im
selben Fenster (die letzten --tage Tage der Reihe) wie in
messreihe_qualitaet.py. Tabellen ohne Spalte "reihe" (SHN, CHS, ...) muessen
mit ihrem eigenen Werkzeug neu erzeugt werden; sie werden nur gemeldet.

Usage: python3 py/qualitaet_nachmessen.py <liste.csv> [--tage 365] [--schreiben]
       liste.csv braucht die Spalten datei und name (ggf. ergebnis=neu)
"""
from __future__ import annotations

import csv
import glob
import os
import shutil
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import messreihe_qualitaet as M                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')


def main(argv):
    liste = argv[0]
    tage = int(argv[argv.index('--tage') + 1]) if '--tage' in argv else 365
    ziel = set()
    for r in csv.DictReader(open(liste, encoding='utf-8')):
        if r.get('ergebnis', 'neu') == 'neu':
            ziel.add((os.path.basename(r['datei']), r['name']))
    import numpy as np
    reihen = {}
    for pfad in sorted(glob.glob(os.path.join(HELP, '*qualitaet*.csv'))):
        rows = list(csv.DictReader(open(pfad, encoding='utf-8')))
        if not rows:
            continue
        felder = list(rows[0].keys())
        betroffen = [r for r in rows if (r.get('datei'), r.get('satz')) in ziel]
        if not betroffen:
            continue
        if 'reihe' not in felder:
            print(f'  {os.path.basename(pfad)}: {len(betroffen)} Zeilen -- eigenes Werkzeug noetig')
            continue
        for r in betroffen:
            q = os.path.join(M.REIHEN, r['reihe'], r['station'])
            if not os.path.exists(q):
                print(f'  Reihe nicht mehr vorhanden, Zeile bleibt: {os.path.relpath(q, M.REIHEN)}')
                continue
            if q not in reihen:
                reihen[q] = M.lies(q)
            obs = reihen[q]
            if not obs:
                print(f'  Reihe fehlt: {q}')
                continue
            ende = obs[-1][0]
            start = ende - tage * 86400
            paare = [(t, h) for t, h in obs if start <= t <= ende]
            ot = np.array([p[0] for p in paare]); oh = np.array([p[1] for p in paare])
            von = dt.datetime.fromtimestamp(start - 7200, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
            bis = dt.datetime.fromtimestamp(ende + 7200, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
            tcd = r['datei'][:-4] + '.tcd'
            vt, vh = M.vorhersage(tcd, r['satz'], von, bis)
            mind = M.MIND_PUNKTE_TAFEL if any(t in q for t in M.TAFELREIHEN) else M.MIND_PUNKTE
            g = M.messe(ot, oh, vt, vh, mind)
            if not g:
                print(f'  keine Messung: {r["satz"]} gegen {r["station"]}')
                continue
            n, rms, gross, versatz, off, hub = g
            print(f'  {os.path.basename(pfad)[:26]:26} {r["satz"][:36]:36} gegen {r["station"][:26]:26} '
                  f'rms {float(r["rms_m"])*100:5.1f} -> {rms*100:5.1f} cm, Zeit {r["zeit_min"]:>4} -> {versatz:+4d} min')
            r.update(n=n, rms_m=round(rms, 4), max_m=round(gross, 3), zeit_min=versatz,
                     hoehe_off_m=round(off, 3), hub_m=round(hub, 3))
        if '--schreiben' in argv:
            shutil.copy2(pfad, os.path.join(ROOT, 'harmonics/backup',
                                            os.path.basename(pfad) + '.vor_nachmessen_'
                                            + dt.datetime.now().strftime('%Y%m%d_%H%M')))
            with open(pfad + '.neu', 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=felder)
                w.writeheader()
                w.writerows(rows)
            os.replace(pfad + '.neu', pfad)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
