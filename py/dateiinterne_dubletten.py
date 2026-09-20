#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loescht dateiinterne Dubletten automatisch (Oliver 17.09.2026).

Dublette = zwei oder mehr Gezeitensaetze in DERSELBEN Datei mit demselben
Namen (eine angehaengte Nummer wie "(2)" zaehlt nicht) und hoechstens
MAX_KM auseinander. Gleichnamige Saetze weiter auseinander ("Davis Strait",
188 km) sind verschiedene Orte und bleiben.

Welcher bleibt, in dieser Reihenfolge:
  1. Schiedsrichter: Klasse-A-Satz oder NOAA CO-OPS aus einer ANDEREN Datei
     bis 3 km -- es bleibt der Satz mit dem kleinsten Kurvenunterschied.
  2. Beide mit utide-Kopfzeile (eigene Fits aus Reihen): der mit den
     meisten Stuetzstellen, bei Gleichstand die juengere Reihe.
  3. Kurven identisch (unter 0.1 %): der erste in der Datei.
  sonst: nicht entscheidbar, bleibt stehen und wird gemeldet.

Geschuetzt wie in py/bestand_aufraeumen.py (behalten.csv, Vermerk von
Oliver). Geloescht wird zeilengenau (gleichnamige Saetze lassen sich ueber
den Namen nicht unterscheiden), jeder Satz ins Archiv
harmonics/backup/geloescht/ (py/satz_zurueckholen.py holt ihn zurueck),
Protokoll harmonics/help/automatisch_geloescht.csv. Traegt der bleibende
Satz eine Nummer und gibt es den Kernnamen in der Datei nicht mehr, wird
die Nummer entfernt.

Usage: python3 py/dateiinterne_dubletten.py [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_guete_probelauf as G                                    # noqa: E402
import noaa_pruefstand as P                                         # noqa: E402
import saetze_loeschen as SL                                        # noqa: E402
import sicher_schreiben                                             # noqa: E402
from bestand_aufraeumen import HAND, PROTOKOLL, geschuetzt          # noqa: E402
from health_check import MERIDIAN, ROOT, curve_diff, km, load_records  # noqa: E402

MAX_KM = 1.0
REF_KM = 3.0


def kern(name):
    return re.sub(r'\s*\(\d+\)\s*(?=,|$)', '', name).strip()


def kopf(r):
    m = re.search(r'pts=(\d+) period=(\S+)\.\.(\S+)', P.vermerk(r))
    return (int(m.group(1)), m.group(3)) if m else None


def entscheiden(gruppe, recs):
    refs = [x for x in recs if x['file'] != gruppe[0]['file'] and km(x, gruppe[0]) <= REF_KM
            and (P.klasse(x) == 'A' or 'CO-OPS' in G.quelle_kurz(x))]
    if refs:
        wert = {id(x): min(curve_diff(x, y)[1] for y in refs) for x in gruppe}
        best = min(gruppe, key=lambda x: wert[id(x)])
        ref = min(refs, key=lambda y: curve_diff(best, y)[1])
        return best, (f'naeher am Referenzsatz "{ref["name"]}" ({G.quelle_kurz(ref)}): '
                      + ', '.join(f'{100 * wert[id(x)]:.1f} %' for x in gruppe))
    kk = [kopf(x) for x in gruppe]
    if all(kk):
        best = max(gruppe, key=lambda x: kopf(x))
        return best, 'laengere Reihe: ' + ', '.join(f'{k[0]} Werte bis {k[1]}' for k in kk)
    if max(curve_diff(gruppe[0], x)[1] for x in gruppe[1:]) < 0.001:
        return gruppe[0], 'Kurven identisch'
    return None, 'kein Schiedsrichter, keine Reihenangaben'


def main(argv):
    schreiben = '--schreiben' in argv
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    schutz = geschuetzt(recs)
    gruppen = collections.defaultdict(list)
    for r in recs:
        gruppen[(r['file'], kern(r['name']))].append(r)
    raus, umbenennen, offen = [], [], []
    for (datei, k), g in sorted(gruppen.items()):
        if len(g) < 2 or max(km(a, b) for a in g for b in g) > MAX_KM:
            continue
        best, grund = entscheiden(g, recs)
        if best is None:
            offen.append((datei, k, grund))
            continue
        weg = [x for x in g if x is not best]
        if any((x['file'], x['name']) in schutz or HAND.search(P.vermerk(x)) for x in weg):
            offen.append((datei, k, 'geschuetzt'))
            continue
        for x in weg:
            raus.append((x, best, grund))
        if best['name'] != k:
            umbenennen.append((best, k))
    for x, best, grund in raus:
        print(f"  weg  {os.path.basename(x['file'])[:28]:28} Zeile {x['line']:6} {x['name'][:48]:48} ({grund[:90]})")
    for best, k in umbenennen:
        print(f"  Name {best['name']} -> {k}")
    for datei, k, grund in offen:
        print(f"  offen {os.path.basename(datei)[:28]:28} {k} -- {grund}")
    print(f'\n{len(raus)} zu loeschen, {len(umbenennen)} Umbenennungen, {len(offen)} offen')
    if not schreiben or not raus:
        return 0

    heute = f'{dt.date.today():%Y%m%d}'
    nach_datei = collections.defaultdict(list)
    for x, best, grund in raus:
        nach_datei[x['file']].append((x, best, grund))
    for datei, liste in nach_datei.items():
        pfad = os.path.join(ROOT, datei)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        bloecke = []
        for x, best, grund in liste:
            i = x['line']
            if lines[i].rstrip() != x['name'] or not MERIDIAN.match(lines[i + 1]):
                i = next(j for j, l in enumerate(lines) if l.rstrip() == x['name'] and j + 1 < len(lines)
                         and MERIDIAN.match(lines[j + 1]) and abs(j - x['line']) < 50)
            a, b = SL.block(lines, i)
            bloecke.append((a, b, x['name'], f'REGEL D0 dateiinterne Dublette von "{best["name"]}": {grund}'))
        SL.archivieren(datei, lines, bloecke, 'dateiinterne_dubletten')
        for a, b, _n, _g in sorted(bloecke, reverse=True):
            del lines[a:b]
        for best, k in umbenennen:
            if best['file'] != datei:
                continue
            if any(l == k for l in lines):
                continue
            for j, l in enumerate(lines):
                if l == best['name'] and j + 1 < len(lines) and MERIDIAN.match(lines[j + 1]):
                    lines[j] = k
                    s = j - 1
                    while s >= 0 and lines[s].startswith('#'):
                        if lines[s].strip() == f"# {best['name']}":
                            lines[s] = f'# {k}'
                        s -= 1
                    einf = max(t for t in range(max(0, j - 40), j) if lines[t].startswith('# !units:'))
                    lines.insert(einf, f'# note: {heute} Nummer entfernt ("{best["name"]}"), die gleichnamigen '
                                       f'Dubletten sind geloescht (py/dateiinterne_dubletten.py).')
                    break
        sicher_schreiben.schreiben(pfad, '\n'.join(lines))
        print(f'geschrieben: {datei} (-{len(bloecke)})')
    neu = not os.path.exists(PROTOKOLL)
    felder = ['datum', 'regel', 'datei', 'name', 'fehler_prozent', 'rang', 'quelle', 'bleibt', 'bleibt_datei',
              'bleibt_rang', 'bleibt_quelle', 'km', 'begruendung']
    with open(PROTOKOLL, 'a', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        if neu:
            w.writeheader()
        for x, best, grund in raus:
            w.writerow(dict(datum=heute, regel='D0', datei=x['file'], name=x['name'],
                            fehler_prozent=f'{100 * curve_diff(x, best)[1]:.1f}', rang='', quelle=G.quelle_kurz(x),
                            bleibt=best['name'], bleibt_datei=best['file'], bleibt_rang='',
                            bleibt_quelle=G.quelle_kurz(best), km=f'{km(x, best):.2f}',
                            begruendung=f'REGEL D0 dateiinterne Dublette: {grund}. Auftrag Oliver {dt.date.today():%d.%m.%Y}.'))
    print(f'Protokoll: {os.path.relpath(PROTOKOLL, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
